"""教研组（v6）：每科老师常驻流 + 总AI + 教研组记录 + 滚动压缩。

- 每科一条常驻对话（kind='teacher', context_ref=学科），错题分析等汇入
- 上下文用尽：超过阈值的旧消息压缩成摘要（ConversationSummary kind='compacted'），
  消息标记 compacted 不再进上下文；图谱/档案/教研记录始终在场，学习判断不丢
- 教研组记录 teacher_notes：各科老师/总AI/夜间写入的共享观察
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (Conversation, ConversationSummary, KnowledgeNode,
                      Message, StudyProfile, TeacherNote, User)

COMPACT_THRESHOLD = 32   # 消息数超过后触发压缩
COMPACT_KEEP = 12        # 压缩后保留的近期消息数


def get_teacher_thread(db: Session, user: User, subject: str) -> Conversation:
    conv = (db.query(Conversation)
            .filter(Conversation.user_id == user.id,
                    Conversation.kind == "teacher",
                    Conversation.context_ref == subject)
            .first())
    if not conv:
        conv = Conversation(user_id=user.id, kind="teacher", context_ref=subject,
                            subject=subject, grade=user.grade or "",
                            title=f"{subject}老师")
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def get_coordinator_thread(db: Session, user: User) -> Conversation:
    conv = (db.query(Conversation)
            .filter(Conversation.user_id == user.id,
                    Conversation.kind == "coordinator")
            .first())
    if not conv:
        conv = Conversation(user_id=user.id, kind="coordinator",
                            subject="", grade=user.grade or "",
                            title="班主任 · 总AI")
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def maybe_compact(db: Session, user: User, conv: Conversation) -> bool:
    """滚动压缩：把最旧消息压成摘要，原消息标记 compacted。"""
    msgs = (db.query(Message)
            .filter(Message.conversation_id == conv.id,
                    Message.meta["compacted"].is_(None) | Message.meta["compacted"].is_(False))
            .order_by(Message.id).all())
    # 上面 JSON 过滤在部分 SQLite 下不可靠，改用 Python 过滤
    msgs = [m for m in (db.query(Message)
                        .filter(Message.conversation_id == conv.id)
                        .order_by(Message.id).all())
            if not (m.meta or {}).get("compacted")]
    if len(msgs) <= COMPACT_THRESHOLD:
        return False
    to_compact = msgs[: len(msgs) - COMPACT_KEEP]
    dialogue = "\n".join(
        f"{'学生' if m.role == 'user' else '导师'}：{(m.content or '')[:200]}" for m in to_compact)
    summary = f"（对话记录摘要 {datetime.utcnow().strftime('%m-%d')}）\n" + dialogue[-4000:]
    s = ConversationSummary(user_id=user.id, conversation_id=conv.id,
                            content=summary)
    db.add(s)
    for m in to_compact:
        meta = m.meta or {}
        meta["compacted"] = True
        m.meta = meta
    db.commit()
    return True


def compaction_summaries(db: Session, conv: Conversation, limit: int = 3) -> str:
    rows = (db.query(ConversationSummary)
            .filter(ConversationSummary.conversation_id == conv.id)
            .order_by(ConversationSummary.id.desc())
            .limit(limit).all())
    return "\n\n".join(r.content for r in reversed(rows))


def history_messages(db: Session, conv: Conversation, limit: int = 16) -> list[dict]:
    """构建进上下文的消息（跳过已压缩）。"""
    msgs = (db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(60)
            .all())[::-1]
    msgs = [m for m in msgs if not (m.meta or {}).get("compacted")]
    return [{"role": m.role, "content": m.content, "images": m.images or []} for m in msgs[-limit:]]


def teacher_system_prompt(db: Session, user: User, subject: str,
                          conv: Conversation, is_coordinator: bool = False) -> str:
    """老师的完整"记忆"：身份 + 图谱 + 档案 + 教研记录 + 压缩摘要。"""
    from ..prompts import PERSONA_BASE, GRADE_DEPTH, SUBJECT_STYLE

    parts = [PERSONA_BASE]
    if is_coordinator:
        parts.append(
            "你担任「班主任·总AI」，统筹学生的全部学习。你可以看到各科老师的观察记录（教研组记录）、"
            "各学科的图谱与档案。负责跨学科的时间分配、复习优先级、学习节奏建议。")
    else:
        parts.append(f"你担任「{subject}老师」，长期陪伴这位学生学习{subject}。"
                     "你是他最了解这门课的学习伙伴，记得他所有的薄弱点和进步。")
        parts.append(SUBJECT_STYLE.get(subject, ""))
    parts.append(GRADE_DEPTH.get(user.grade or "", ""))

    # 图谱（该科 + 全部薄弱）
    nodes = (db.query(KnowledgeNode)
             .filter(KnowledgeNode.user_id == user.id, KnowledgeNode.archived.is_(False))
             .all())
    if not is_coordinator:
        nodes = [n for n in nodes if n.subject == subject]
    node_lines = "\n".join(
        f"- [{n.subject}] {n.name}（{n.mastery}/{n.confidence}，错{int(n.error_count or 0)}次）"
        for n in nodes[:30])
    if node_lines:
        parts.append(f"【知识图谱记忆】\n{node_lines}")

    # 档案
    if is_coordinator:
        profs = db.query(StudyProfile).filter(StudyProfile.user_id == user.id).all()
    else:
        profs = db.query(StudyProfile).filter(
            StudyProfile.user_id == user.id, StudyProfile.subject == subject).all()
    prof_lines = "\n\n".join(p.content for p in profs if p.content)
    if prof_lines:
        parts.append(f"【学习档案记忆】\n{prof_lines[-2500:]}")

    # 教研组记录
    notes = (db.query(TeacherNote)
             .filter(TeacherNote.user_id == user.id)
             .order_by(TeacherNote.created_at.desc())
             .limit(12).all())
    if not is_coordinator:
        notes = [n for n in notes if n.subject in ("", subject)] or notes
    note_lines = "\n".join(
        f"- [{n.author}] {n.content[:120]}（{n.confidence}）" for n in notes)
    if note_lines:
        parts.append(f"【教研组记录（老师们共享的观察）】\n{note_lines}")

    # 压缩摘要（上下文用尽时的历史）
    comp = compaction_summaries(db, conv)
    if comp:
        parts.append(f"【此前对话的历史摘要】\n{comp[-2500:]}")

    parts.append(
        "对话要求：语气亲切鼓励，Markdown 排版（## 板块自由组织），公式用 LaTeX。"
        "重要发现请调用 post_teacher_note 技能写入教研组记录（如：新的薄弱模式、跨学科影响）。")
    from .skills import skills_catalog_prompt
    parts.append("【可用技能】\n" + skills_catalog_prompt())
    return "\n\n".join(parts)


def post_note(db: Session, user: User, author: str, subject: str,
              content: str, confidence: str = "observed") -> dict:
    n = TeacherNote(user_id=user.id, author=author[:32], subject=subject[:32],
                    content=content[:2000],
                    confidence=confidence if confidence in ("observed", "likely", "confirmed") else "observed")
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"id": n.id, "author": n.author, "subject": n.subject,
            "content": n.content, "confidence": n.confidence}


def post_to_teacher_thread(db: Session, user: User, subject: str,
                           content: str) -> int:
    """把错题分析等成果汇入该科老师的常驻对话流，返回会话 ID。"""
    conv = get_teacher_thread(db, user, subject or "综合")
    msg = Message(conversation_id=conv.id, role="assistant", content=content,
                  meta={"source": "analysis"})
    db.add(msg)
    conv.updated_at = datetime.utcnow()
    db.commit()
    return conv.id
