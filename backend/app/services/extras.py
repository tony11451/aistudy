"""刷题目标、答题方法总结、学习报告、作业扫描识别。"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import prompts
from ..models import (PracticeGoal, Report, User, UserKnowledgeStatus,
                      KnowledgePoint, WrongQuestion)
from .ai_client import build_user_content, extract_json
from .context import get_ai_client, get_vision_client
from .knowledge import set_learning_state
from .retrieval import format_progress


def _weakness_text(db: Session, user: User) -> str:
    parts = [format_progress(db, user)]
    recent = (db.query(WrongQuestion)
              .filter(WrongQuestion.user_id == user.id)
              .order_by(WrongQuestion.created_at.desc())
              .limit(8)
              .all())
    lines = [f"- 《{w.subject}》{w.knowledge_points}：{(w.wrong_reason or '')[:100]}" for w in recent]
    parts.append("【最近错题】\n" + ("\n".join(lines) or "（无）"))
    return "\n".join(parts)


async def generate_goals(db: Session, user: User, subject: str = "") -> list[PracticeGoal]:
    client = get_ai_client(db, user)
    subject = subject or user.grade and subject or subject
    system = prompts.goal_planning_system_prompt(subject or "综合", user.grade, _weakness_text(db, user))
    data = await client.complete_json([
        {"role": "system", "content": system},
        {"role": "user", "content": "请为我制定刷题目标。"},
    ], temperature=0.5)
    items = data if isinstance(data, list) else [data]
    goals = []
    for it in items[:5]:
        if not isinstance(it, dict):
            continue
        g = PracticeGoal(
            user_id=user.id,
            subject=it.get("subject") or subject or "综合",
            title=str(it.get("title") or "刷题目标")[:128],
            question_type=str(it.get("question_type") or "")[:64],
            description=str(it.get("description") or "")[:2000],
            reason=str(it.get("reason") or "")[:1000],
            due_date=str(it.get("due_date") or "")[:32],
        )
        db.add(g)
        goals.append(g)
    db.commit()
    for g in goals:
        db.refresh(g)
    return goals


async def summarize_method(db: Session, user: User, subject: str, question: str,
                           ask: str = "") -> dict:
    client = get_ai_client(db, user)
    system = prompts.method_summary_system_prompt(subject, user.grade)
    data = await client.complete_json([
        {"role": "system", "content": system},
        {"role": "user", "content": f"【题目】\n{question}\n\n【学生提问】\n{ask or '请总结答题方法'}"},
    ], temperature=0.3)
    return data if isinstance(data, dict) else {}


async def generate_report(db: Session, user: User, subject: str = "") -> Report:
    client = get_ai_client(db, user)
    system = prompts.report_system_prompt(subject or "综合", user.grade)
    material = _weakness_text(db, user)
    goals = (db.query(PracticeGoal)
             .filter(PracticeGoal.user_id == user.id, PracticeGoal.status == "active")
             .all())
    goal_txt = "\n".join(f"- [{g.subject}] {g.title}: {g.description[:80]}" for g in goals)
    content = await client.complete([
        {"role": "system", "content": system},
        {"role": "user", "content": f"{material}\n\n【进行中的刷题目标】\n{goal_txt or '（无）'}\n\n请生成学习报告。"},
    ], temperature=0.5)
    report = Report(user_id=user.id, kind="manual",
                    title=f"学习报告 · {datetime.utcnow().strftime('%Y-%m-%d')}",
                    content=content)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


async def scan_homework(db: Session, user: User, subject: str, grade: str,
                        image_ids: list[int]) -> dict:
    client = get_vision_client(db, user)
    grade = grade or user.grade or ""
    system = prompts.progress_identify_system_prompt(subject, grade)
    content = build_user_content("请识别这些作业/试卷照片中我正在学习的内容。", image_ids, user.id)
    data = await client.complete_json([
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ], temperature=0.2)
    items = data.get("learning_items", []) if isinstance(data, dict) else []
    for it in items:
        it.setdefault("subject", subject or "综合")
    if items:
        set_learning_state(db, user, items)
    return data if isinstance(data, dict) else {"learning_items": [], "summary": ""}
