"""全局搜索（需求 23）：普通搜索（错题+档案+图谱+对话统一）+ AI 高级搜索。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (Conversation, KnowledgeNode, LibraryItem, User,
                      WrongQuestion)
from ..services.context import get_ai_client

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def global_search(q: str = Query(""),
                  subject: str = Query(""),
                  source: str = Query(""),
                  limit: int = Query(20, le=60),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """普通搜索：错题 / 档案 / 图谱节点 / 对话，统一分组返回。"""
    kw = (q or "").strip()
    like = f"%{kw}%"

    wq_q = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if subject:
        wq_q = wq_q.filter(WrongQuestion.subject == subject)
    if source in ("wrong_question", "错题"):
        pass
    if kw:
        wq_q = wq_q.filter(or_(WrongQuestion.question_text.like(like),
                               WrongQuestion.wrong_reason.like(like),
                               WrongQuestion.correct_solution.like(like)))
    wrong = wq_q.order_by(WrongQuestion.created_at.desc()).limit(limit).all()

    lib_q = db.query(LibraryItem).filter(LibraryItem.user_id == user.id)
    if subject:
        lib_q = lib_q.filter(LibraryItem.subject == subject)
    if source in ("image", "text", "attachment", "review", "wrong_question"):
        lib_q = lib_q.filter(LibraryItem.kind == source)
    if kw:
        lib_q = lib_q.filter(or_(LibraryItem.title.like(like),
                                 LibraryItem.content.like(like),
                                 LibraryItem.ocr_text.like(like),
                                 LibraryItem.file_name.like(like)))
    lib = lib_q.order_by(LibraryItem.created_at.desc()).limit(limit).all()

    node_q = db.query(KnowledgeNode).filter(KnowledgeNode.user_id == user.id,
                                            KnowledgeNode.archived.is_(False))
    if subject:
        node_q = node_q.filter(KnowledgeNode.subject == subject)
    if kw:
        node_q = node_q.filter(or_(KnowledgeNode.name.like(like),
                                   KnowledgeNode.description.like(like),
                                   KnowledgeNode.note.like(like)))
    nodes = node_q.order_by(KnowledgeNode.updated_at.desc()).limit(limit).all()

    conv_q = db.query(Conversation).filter(Conversation.user_id == user.id)
    if kw:
        conv_q = conv_q.filter(or_(Conversation.title.like(like)))
    convs = conv_q.order_by(Conversation.updated_at.desc()).limit(limit).all()

    return {
        "wrong_questions": [{
            "id": w.id, "type": "wrong_question", "title": (w.question_text or f"错题 #{w.id}")[:120],
            "subject": w.subject, "extra": (w.wrong_reason or "")[:100],
            "date": w.created_at.isoformat() if w.created_at else None,
        } for w in wrong],
        "library": [{
            "id": it.id, "type": "library", "title": it.title, "subject": it.subject,
            "kind": it.kind, "extra": (it.ocr_preview if False else (it.ocr_text or it.content or ""))[:100],
            "date": it.created_at.isoformat() if it.created_at else None,
        } for it in lib],
        "nodes": [{
            "id": n.id, "type": "node", "title": n.name, "subject": n.subject,
            "kind": n.node_type, "extra": (n.description or n.note or "")[:100],
        } for n in nodes],
        "conversations": [{
            "id": c.id, "type": "conversation", "title": c.title, "subject": c.subject,
            "extra": "", "date": c.updated_at.isoformat() if c.updated_at else None,
        } for c in convs],
    }


@router.post("/ai")
async def ai_search(payload: dict, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """AI 高级搜索（需求 23）：调用 Skill 全局查找"是否出现过"，可筛学科/来源。"""
    question = str(payload.get("q") or "").strip()
    subject = str(payload.get("subject") or "")
    source = str(payload.get("source") or "")
    if not question:
        raise HTTPException(status_code=400, detail="请输入搜索内容")

    from ..services.skill_loop import skill_chat_stream
    from ..services.skills import skills_catalog_prompt

    client = get_ai_client(db, user)
    system = (
        "你是学习资料检索助手。请用技能搜索学生的历史，回答「这个题目/知识点以前出现过吗、出现在哪里」。\n"
        "建议流程：先 search_library 和 read_wrong_questions 搜索关键词（可加 subject 筛选），"
        "必要时 read_mindmap、read_conversations 补充。最后给出结论（Markdown）：\n"
        "- 【出现记录】列出来源（错题/档案/图谱/对话）、时间、位置\n"
        "- 【相关度】说明与当前问题的关联\n"
        "- 【建议】基于历史给出的下一步建议\n"
        f"筛选条件：学科={subject or '不限'}；来源={source or '不限'}。\n\n"
        "可用技能：\n" + skills_catalog_prompt() +
        "\n\n技能调用 JSON 必须单独成行，不要与正文混排。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    answer_parts: list[str] = []
    skills_used: list[str] = []
    try:
        async for kind, data in skill_chat_stream(
                client, db, user, {"conversation_id": None}, messages):
            if kind == "delta":
                answer_parts.append(data)
            elif kind == "final":
                answer_parts = [data]
            elif kind == "skill" and data.get("status") == "done":
                skills_used.append(data.get("name", ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 搜索失败：{e}")
    return {"answer": "".join(answer_parts), "skills_used": skills_used}
