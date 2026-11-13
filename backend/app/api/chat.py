import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import prompts
from ..database import get_db
from ..deps import get_current_user
from ..models import Conversation, KnowledgeNode, Message, User, WrongQuestion
from ..schemas import ChatMessageIn, ConversationCreate
from ..services.ai_client import build_user_content
from ..services.context import get_ai_client, resolve_ai_config
from ..services import retrieval

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_CONTEXT_MESSAGES = 16


def _conv_dict(c: Conversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "subject": c.subject,
        "grade": c.grade,
        "context_kind": c.context_kind,
        "context_ref": c.context_ref,
        "model_name": c.model_name,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "images": m.images or [],
        "meta": m.meta or {},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Conversation)
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
            .all())
    return [_conv_dict(c) for c in rows]


@router.post("/conversations")
def create_conversation(payload: ConversationCreate, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    c = Conversation(
        user_id=user.id,
        title=payload.title or "新对话",
        subject=payload.subject,
        grade=payload.grade or user.grade,
        context_kind=payload.context_kind,
        context_ref=payload.context_ref,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _conv_dict(c)


@router.get("/conversations/{cid}")
def get_conversation(cid: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    c = db.query(Conversation).filter(Conversation.id == cid,
                                      Conversation.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = (db.query(Message)
            .filter(Message.conversation_id == cid)
            .order_by(Message.id)
            .all())
    return {"conversation": _conv_dict(c), "messages": [_msg_dict(m) for m in msgs]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    c = db.query(Conversation).filter(Conversation.id == cid,
                                      Conversation.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.query(Message).filter(Message.conversation_id == cid).delete()
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.put("/conversations/{cid}")
def update_conversation(cid: int, payload: dict, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    c = db.query(Conversation).filter(Conversation.id == cid,
                                      Conversation.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="对话不存在")
    if "model_name" in payload:
        c.model_name = str(payload["model_name"] or "")[:128]
    if "title" in payload and payload["title"]:
        c.title = str(payload["title"])[:64]
    db.commit()
    return _conv_dict(c)


@router.post("/conversations/{cid}/summarize")
async def summarize_conversation(cid: int, user: User = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
    """把对话内容总结成知识图谱节点变更提议（用户勾选后应用）。"""
    conv = db.query(Conversation).filter(Conversation.id == cid,
                                         Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = (db.query(Message)
            .filter(Message.conversation_id == cid)
            .order_by(Message.id)
            .all())
    if not msgs:
        raise HTTPException(status_code=400, detail="对话还没有内容")
    dialogue = "\n".join(
        f"{'学生' if m.role == 'user' else '导师'}：{(m.content or '')[:400]}"
        for m in msgs)[-6000:]
    existing = (db.query(KnowledgeNode)
                .filter(KnowledgeNode.user_id == user.id)
                .order_by(KnowledgeNode.updated_at.desc())
                .limit(40)
                .all())
    existing_txt = "\n".join(
        f"- [{n.id}] {n.subject}/{n.name}（{'弱点' if n.node_type == 'weakness' else '知识点'}，{n.confidence}）"
        for n in existing)
    client = get_ai_client(db, user)
    try:
        data = await client.complete_json([
            {"role": "system", "content": prompts.summarize_chat_system_prompt(
                conv.subject or "", conv.grade or user.grade, existing_txt)},
            {"role": "user", "content": f"【对话记录】\n{dialogue}\n\n请提炼知识点/弱点提议。"},
        ], temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 总结失败：{e}")
    proposals = data.get("proposals", []) if isinstance(data, dict) else []
    for p in proposals:
        p.setdefault("subject", conv.subject or "综合")
    return {"proposals": proposals[:10]}


def _build_system(db: Session, user: User, conv: Conversation) -> str:
    cfg = resolve_ai_config(db, user)
    extra = cfg["system_extra_prompt"]
    if conv.context_kind == "knowledge":
        kp_name = conv.context_ref
        kp = (db.query(KnowledgeNode)
              .filter(KnowledgeNode.name == kp_name, KnowledgeNode.user_id == user.id)
              .first())
        subject = conv.subject or (kp.subject if kp else "")
        rows = [w for w in db.query(WrongQuestion)
                .filter(WrongQuestion.user_id == user.id, WrongQuestion.subject == subject)
                .all() if kp_name in (w.knowledge_points or [])]
        ctx_lines = [f"- 错题：{(w.question_text or '')[:120]}｜错因：{(w.wrong_reason or '')[:100]}"
                     for w in rows[:5]]
        if kp and kp.parent_id:
            parent = db.query(KnowledgeNode).filter(KnowledgeNode.id == kp.parent_id).first()
            if parent:
                ctx_lines.insert(0, f"上级分类：{parent.name}")
        if kp:
            kids = db.query(KnowledgeNode).filter(KnowledgeNode.parent_id == kp.id).all()
            if kids:
                ctx_lines.insert(0, f"已知子方向：{'、'.join(k.name for k in kids)}")
            if kp.description:
                ctx_lines.insert(0, f"知识点简介：{kp.description[:120]}")
        ctx_lines.append(f"历史错题数量：{len(rows)}")
        return prompts.knowledge_chat_system_prompt(
            kp_name, subject, conv.grade or user.grade,
            retrieval.format_profiles(db, user, subject),
            "\n".join(ctx_lines),
        ) + "\n\n" + prompts.skill_protocol_system_prompt()
    subject = conv.subject
    query = ""
    if conv.context_kind == "wrong_question":
        w = db.query(WrongQuestion).filter(WrongQuestion.id == int(conv.context_ref or 0),
                                           WrongQuestion.user_id == user.id).first()
        if w:
            subject = subject or w.subject
            query = w.question_text or ""
    return prompts.chat_system_prompt(
        subject, conv.grade or user.grade,
        retrieval.format_profiles(db, user, subject),
        retrieval.format_progress(db, user),
        retrieval.format_methods(db, user, subject),
        retrieval.format_wrong_context(retrieval.retrieve_wrong_questions(db, user, query, subject)),
        extra,
    ) + "\n\n" + prompts.skill_protocol_system_prompt()


@router.post("/conversations/{cid}/summary")
async def make_summary(cid: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """独立 Agent 生成对话摘要（不进入消息流）。"""
    conv = db.query(Conversation).filter(Conversation.id == cid,
                                         Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    msgs = db.query(Message).filter(Message.conversation_id == cid).order_by(Message.id).all()
    if not msgs:
        raise HTTPException(status_code=400, detail="对话还没有内容")
    dialogue = "\n".join(
        f"{'学生' if m.role == 'user' else '导师'}：{(m.content or '')[:300]}" for m in msgs)[-5000:]
    client = get_ai_client(db, user)
    try:
        text = await client.complete([
            {"role": "system", "content":
             "你是学习记录整理员。用简洁中文条目总结这段学习对话：讨论的知识点、学生的疑问点、"
             "达成的结论、后续行动。不复述寒暄。Markdown 条目。"},
            {"role": "user", "content": dialogue},
        ], temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 总结失败：{e}")
    from ..models import ConversationSummary
    s = ConversationSummary(user_id=user.id, conversation_id=cid, content=text)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "content": text, "created_at": s.created_at.isoformat()}


@router.get("/conversations/{cid}/summaries")
def list_summaries(cid: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    from ..models import ConversationSummary
    rows = (db.query(ConversationSummary)
            .filter(ConversationSummary.conversation_id == cid,
                    ConversationSummary.user_id == user.id)
            .order_by(ConversationSummary.created_at.desc()).all())
    return [{"id": s.id, "content": s.content,
             "created_at": s.created_at.isoformat() if s.created_at else None} for s in rows]


@router.post("/conversations/{cid}/messages")
def send_message(cid: int, payload: ChatMessageIn,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == cid,
                                         Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    user_msg = Message(conversation_id=cid, role="user", content=payload.content,
                       images=payload.image_ids or [])
    db.add(user_msg)
    conv.updated_at = datetime.utcnow()
    if payload.model:
        conv.model_name = payload.model[:128]
    if conv.title == "新对话" and payload.content:
        conv.title = payload.content.strip()[:24] or conv.title
    db.commit()
    db.refresh(user_msg)

    history = (db.query(Message)
               .filter(Message.conversation_id == cid)
               .order_by(Message.id.desc())
               .limit(MAX_CONTEXT_MESSAGES)
               .all())[::-1]

    client = get_ai_client(db, user, conv.model_name)
    max_imgs = getattr(client, "max_images", 10)
    messages = [{"role": "system", "content": _build_system(db, user, conv)}]
    for m in history:
        if m.role == "user":
            messages.append({
                "role": "user",
                "content": build_user_content(m.content, m.images or [], user.id,
                                              max_images=max_imgs),
            })
        else:
            messages.append({"role": "assistant", "content": m.content})

    async def event_stream():
        collected = []
        skill_events = []
        change_ids = []
        change_cards = []
        try:
            yield _sse("meta", {"conversation_id": cid, "user_message_id": user_msg.id})
            from ..services.skill_loop import skill_chat_stream
            async for kind, payload in skill_chat_stream(
                    client, db, user, {"conversation_id": cid}, messages):
                if kind == "delta":
                    collected.append(payload)
                    yield _sse("delta", {"content": payload})
                elif kind == "skill":
                    skill_events.append(payload)
                    yield _sse("skill", payload)
                elif kind == "change":
                    if payload.get("change_id"):
                        change_ids.append(payload["change_id"])
                    change_cards.append({
                        "change_id": payload.get("change_id"),
                        "action": payload.get("action", ""),
                        "description": payload.get("description", ""),
                        "reason": payload.get("reason", ""),
                    })
                    yield _sse("change", payload)
                elif kind == "final":
                    collected = [payload]
            full = "".join(collected)
            meta = {"skills": skill_events, "change_ids": change_ids, "changes": change_cards}
            assistant = Message(conversation_id=cid, role="assistant", content=full, meta=meta)
            db.add(assistant)
            db.commit()
            db.refresh(assistant)
            yield _sse("done", {"message_id": assistant.id,
                                "change_ids": change_ids})
        except Exception as e:
            meta = {"skills": skill_events, "change_ids": change_ids, "changes": change_cards}
            if collected:
                assistant = Message(conversation_id=cid, role="assistant",
                                    content="".join(collected), meta=meta)
                db.add(assistant)
                db.commit()
            yield _sse("error", {"message": str(e)[:400]})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
