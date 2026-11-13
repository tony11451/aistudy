"""夜间整理（需求 21/22）：OCR → 归档整理 → 进度识别 → 简报。

- 时间由用户在设置里自定义（nightly_time，默认 23:00）
- 启动后台任务每分钟检查；每天最多跑一次（nightly_last_run 记录）
- 也支持手动触发「立即整理」
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import AppSettings, LibraryItem, Report, User, WrongQuestion
from .context import get_ai_client
from .knowledge import set_learning_items
from .ocr import process_pending


def _get_row(db: Session) -> AppSettings:
    row = db.query(AppSettings).filter(AppSettings.id == 1).first()
    if not row:
        row = AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


async def run_nightly_for_user(db: Session, user: User) -> dict:
    result = {"ocr": {}, "progress": False, "report": False}
    # 1) OCR 待提取的图片（课本/错题/资料）
    try:
        result["ocr"] = await process_pending(db, user, limit=30)
    except Exception:
        result["ocr"] = {"done": 0, "failed": 0}

    # 2) 从新内容识别学习进度（基于最近 OCR 文字/错题）
    try:
        recent = (db.query(LibraryItem)
                  .filter(LibraryItem.user_id == user.id,
                          LibraryItem.ocr_status == "done",
                          LibraryItem.ocr_text != "")
                  .order_by(LibraryItem.created_at.desc()).limit(10).all())
        snippets = "\n".join(f"- [{it.subject}] {(it.ocr_text or '')[:120]}" for it in recent)
        wqs = (db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
               .order_by(WrongQuestion.created_at.desc()).limit(10).all())
        wq_txt = "\n".join(f"- [{w.subject}] {w.knowledge_points}" for w in wqs)
        if snippets or wq_txt:
            client = get_ai_client(db, user)
            import json as _json
            data = await client.complete_json([
                {"role": "system", "content":
                 "你是学习进度分析员。根据材料识别学生正在学习的知识点。"
                 "知识点用「大方向」命名（章节级），不要精细到单词/词组/单个公式。\n"
                 "严格输出 JSON：{\"learning_items\": [{\"knowledge_point\": \"..\", \"unit\": \"..\", "
                 "\"learning_state\": \"learning|learned\", \"evidence\": \"..\"}]}"},
                {"role": "user", "content": f"【新资料】\n{snippets}\n【近期错题】\n{wq_txt}"},
            ], temperature=0.2)
            items = (data or {}).get("learning_items") or []
            if items:
                for it in items:
                    it.setdefault("subject", user.grade and "" or "")
                set_learning_items(db, user, items)
                result["progress"] = True
    except Exception:
        pass

    # 3) 生成当晚简报
    try:
        client = get_ai_client(db, user)
        brief = await client.complete([
            {"role": "system", "content":
             "你是学习助理。写一份简短的当日学习简报（3-5 条要点）：今天整理了什么、发现了什么薄弱点、"
             "明天建议做什么。语气鼓励，Markdown 列表。"},
            {"role": "user", "content": "请生成今日简报。"},
        ], temperature=0.5)
        rep = Report(user_id=user.id, kind="nightly",
                     title=f"学习简报 · {datetime.utcnow().strftime('%m-%d')}",
                     content=brief)
        db.add(rep)
        db.commit()
        result["report"] = True
    except Exception:
        pass
    return result


async def run_nightly_all(db_factory) -> None:
    """给所有用户跑夜间整理（后台调度用）。"""
    db = db_factory()
    try:
        users = db.query(User).filter(User.is_active.is_(True)).all()
        for u in users:
            try:
                await run_nightly_for_user(db, u)
            except Exception:
                continue
    finally:
        db.close()


def nightly_due(db: Session) -> bool:
    row = _get_row(db)
    if not row.nightly_enabled:
        return False
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if row.nightly_last_run == today:
        return False
    try:
        hh, mm = (row.nightly_time or "23:00").split(":")
        target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        target = now.replace(hour=23, minute=0, second=0, microsecond=0)
    return now >= target


def mark_nightly_ran(db: Session) -> None:
    row = _get_row(db)
    row.nightly_last_run = datetime.now().strftime("%Y-%m-%d")
    db.commit()
