"""学习档案（AI 第二大脑）维护。"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import prompts
from ..models import StudyProfile, User, WrongQuestion
from .context import get_ai_client


def get_profile_text(db: Session, user: User, subject: str) -> str:
    row = (db.query(StudyProfile)
           .filter(StudyProfile.user_id == user.id, StudyProfile.subject == subject)
           .first())
    return row.content if row else ""


def get_all_profiles(db: Session, user: User) -> list[StudyProfile]:
    return (db.query(StudyProfile)
            .filter(StudyProfile.user_id == user.id)
            .order_by(StudyProfile.subject)
            .all())


async def update_profile_with_analysis(db: Session, user: User, subject: str,
                                       analysis_text: str) -> str:
    client = get_ai_client(db, user)
    current = get_profile_text(db, user, subject)
    system = prompts.profile_update_system_prompt(subject)
    user_msg = f"【现有档案】\n{current or '（暂无）'}\n\n【最近错题分析摘要】\n{analysis_text}"
    new_content = await client.complete([
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ], temperature=0.3)

    row = (db.query(StudyProfile)
           .filter(StudyProfile.user_id == user.id, StudyProfile.subject == subject)
           .first())
    if not row:
        row = StudyProfile(user_id=user.id, subject=subject)
        db.add(row)
    row.content = new_content.strip()
    row.updated_at = datetime.utcnow()
    db.commit()
    return row.content


def summarize_recent(db: Session, user: User, subject: str, limit: int = 5) -> str:
    rows = (db.query(WrongQuestion)
            .filter(WrongQuestion.user_id == user.id, WrongQuestion.subject == subject)
            .order_by(WrongQuestion.created_at.desc())
            .limit(limit)
            .all())
    lines = []
    for w in rows:
        lines.append(
            f"- 知识点{w.knowledge_points} | 错因：{(w.wrong_reason or '')[:120]} | "
            f"难度：{w.difficulty}"
        )
    return "\n".join(lines)
