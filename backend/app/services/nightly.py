"""夜间整理（v6）：OCR/归档/进度/简报 + 审核批次 + 双模式。

- nightly_mode：fast_ocr（仅文字）/ ai_smart（提取+归类+标签+图谱）
- 改动记 ChangeLog(source='nightly')；auto_approve 开关决定 status=approved/pending
- 每批次生成 NightlyRun 供「昨晚整理审核」页逐条允许/撤销
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (AppSettings, ChangeLog, LibraryItem, NightlyRun, Report,
                      User, WrongQuestion)
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


def _record_change(db: Session, user: User, description: str, reason: str,
                   status: str, target_type: str = "nightly",
                   target_id: int | None = None, before=None, after=None) -> int:
    c = ChangeLog(user_id=user.id, skill="nightly", action="update",
                  target_type=target_type, target_id=target_id,
                  description=description[:500], reason=reason[:500],
                  before=before, after=after, status=status, source="nightly")
    db.add(c)
    db.flush()
    return c.id


async def run_nightly_for_user(db: Session, user: User) -> dict:
    row = _get_row(db)
    mode = row.nightly_mode or "ai_smart"
    auto = bool(row.auto_approve_nightly)
    status = "approved" if auto else "pending"
    change_ids: list[int] = []
    result = {"ocr": {}, "progress": False, "report": False, "mode": mode}

    # 1) OCR 待提取图片（双模式都做文字提取；ai_smart 额外做语义整理）
    try:
        result["ocr"] = await process_pending(db, user, limit=30)
        if result["ocr"].get("done"):
            change_ids.append(_record_change(
                db, user, f"批量提取 {result['ocr']['done']} 条内容文字",
                "夜间自动整理", status, "nightly"))
    except Exception:
        result["ocr"] = {"done": 0, "failed": 0}

    # 2) 从新内容识别学习进度（仅 ai_smart）
    if mode == "ai_smart":
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
                        it.setdefault("subject", "")
                    set_learning_items(db, user, items)
                    result["progress"] = True
                    change_ids.append(_record_change(
                        db, user,
                        f"更新学习进度：识别 {len(items)} 个知识点",
                        "根据新增资料自动识别", status, "learning_items",
                        after={"items": [i.get("knowledge_point") for i in items]}))
        except Exception:
            pass

    # 3) 当晚简报
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
        change_ids.append(_record_change(
            db, user, "生成当晚学习简报", "夜间自动整理", status, "report"))
    except Exception:
        pass

    # 4) 批次记录（审核页用）
    summary = (f"模式：{mode}；OCR {result['ocr'].get('done', 0)} 条；"
               f"进度更新：{'是' if result['progress'] else '否'}；简报：{'是' if result['report'] else '否'}")
    run = NightlyRun(user_id=user.id, run_date=datetime.now().strftime("%Y-%m-%d"),
                     mode=mode, summary=summary, change_ids=change_ids,
                     status="approved" if auto else "pending")
    db.add(run)
    db.commit()
    result["change_ids"] = change_ids
    result["auto_approved"] = auto
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