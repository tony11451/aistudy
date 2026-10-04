import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import prompts
from ..database import get_db
from ..deps import get_current_user
from ..models import Conversation, KnowledgePoint, Message, User, WrongQuestion
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
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "images": m.images or [],
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


def _build_system(db: Session, user: User, conv: Conversation) -> str:
    cfg = resolve_ai_config(db, user)
    extra = cfg["system_extra_prompt"]
    if conv.context_kind == "knowledge":
        kp_name = conv.context_ref
        kp = (db.query(KnowledgePoint)
              .filter(KnowledgePoint.name == kp_name)
              .first())
        subject = conv.subject or (kp.subject if kp else "")
        rows = [w for w in db.query(WrongQuestion)
                .filter(WrongQuestion.user_id == user.id, WrongQuestion.subject == subject)
                .all() if kp_name in (w.knowledge_points or [])]
        ctx_lines = [f"- 错题：{(w.question_text or '')[:120]}｜错因：{(w.wrong_reason or '')[:100]}"
                     for w in rows[:5]]
        if kp and kp.unit:
            ctx_lines.insert(0, f"所属单元：{kp.unit}")
        ctx_lines.append(f"历史错题数量：{len(rows)}")
        return prompts.knowledge_chat_system_prompt(
            kp_name, subject, conv.grade or user.grade,
            retrieval.format_profiles(db, user, subject),
            "\n".join(ctx_lines),
        )
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
    )


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
    if conv.title == "新对话" and payload.content:
        conv.title = payload.content.strip()[:24] or conv.title
    db.commit()
    db.refresh(user_msg)

    history = (db.query(Message)
               .filter(Message.conversation_id == cid)
               .order_by(Message.id.desc())
               .limit(MAX_CONTEXT_MESSAGES)
               .all())[::-1]

    messages = [{"role": "system", "content": _build_system(db, user, conv)}]
    for m in history:
        if m.role == "user":
            messages.append({
                "role": "user",
                "content": build_user_content(m.content, m.images or [], user.id),
            })
        else:
            messages.append({"role": "assistant", "content": m.content})

    async def event_stream():
        collected = []
        try:
            client = get_ai_client(db, user)
            yield _sse("meta", {"conversation_id": cid, "user_message_id": user_msg.id})
            async for delta in client.stream_chat(messages):
                collected.append(delta)
                yield _sse("delta", {"content": delta})
            full = "".join(collected)
            assistant = Message(conversation_id=cid, role="assistant", content=full)
            db.add(assistant)
            db.commit()
            db.refresh(assistant)
            yield _sse("done", {"message_id": assistant.id})
        except Exception as e:
            if collected:
                assistant = Message(conversation_id=cid, role="assistant",
                                    content="".join(collected))
                db.add(assistant)
                db.commit()
            yield _sse("error", {"message": str(e)[:400]})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
