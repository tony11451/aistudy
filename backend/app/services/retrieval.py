"""对话上下文检索：相关历史错题 / 方法卡片 / 进度。"""
from sqlalchemy.orm import Session

from ..models import (KnowledgeNode, MethodCard, User, WrongQuestion)
from .profile import get_all_profiles


def retrieve_wrong_questions(db: Session, user: User, query: str, subject: str = "",
                             limit: int = 4) -> list[WrongQuestion]:
    q = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if subject:
        q = q.filter(WrongQuestion.subject == subject)
    rows = q.order_by(WrongQuestion.created_at.desc()).limit(200).all()
    if not rows:
        return []
    tokens = [t for t in (query or "").replace("\n", " ").split() if len(t) >= 2][:12]
    scored = []
    for w in rows:
        score = 0.0
        hay = f"{w.question_text} {w.wrong_reason} {' '.join(w.knowledge_points or [])} {w.unit}"
        for t in tokens:
            if t in hay:
                score += 2
        for kp in (w.knowledge_points or []):
            if kp and query and kp in query:
                score += 3
        if w.is_reviewed:
            score -= 0.5
        scored.append((score, w))
    scored.sort(key=lambda x: (-x[0], -(x[1].created_at.timestamp() if x[1].created_at else 0)))
    top = [w for s, w in scored[:limit * 2] if s > 0]
    if not top:
        top = [w for _, w in scored[:limit]]
    return top[:limit]


def format_wrong_context(rows: list[WrongQuestion]) -> str:
    lines = []
    for w in rows:
        lines.append(
            f"* 《{w.subject}》{(w.knowledge_points or [''])[0]}：{(w.question_text or '')[:150]}\n"
            f"  错因：{(w.wrong_reason or '')[:120]}；解法要点：{(w.correct_solution or '')[:120]}"
        )
    return "\n".join(lines)


def format_methods(db: Session, user: User, subject: str = "") -> str:
    q = db.query(MethodCard).filter(MethodCard.user_id == user.id)
    if subject:
        q = q.filter(MethodCard.subject == subject)
    rows = q.order_by(MethodCard.created_at.desc()).limit(3).all()
    lines = []
    for m in rows:
        lines.append(f"* [{m.subject}]{m.knowledge_point} 具体：{(m.specific_method or '')[:100]}")
    return "\n".join(lines)


def format_progress(db: Session, user: User) -> str:
    rows = (db.query(KnowledgeNode)
            .filter(KnowledgeNode.user_id == user.id)
            .order_by(KnowledgeNode.updated_at.desc())
            .limit(20)
            .all())
    lines = []
    for s in rows:
        lines.append(
            f"- {s.subject}/{s.name}（{'弱点' if s.node_type == 'weakness' else '知识点'}）："
            f"掌握度={s.mastery}，置信度={s.confidence}，学习状态={s.learning_state}，错题数={s.error_count}"
        )
    return "\n".join(lines)


def format_profiles(db: Session, user: User, subject: str = "") -> str:
    rows = get_all_profiles(db, user)
    if subject:
        rows = [r for r in rows if r.subject == subject]
    return "\n\n".join(f"【{r.subject}】\n{r.content}" for r in rows if r.content)
