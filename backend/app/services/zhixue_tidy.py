"""智学网数据整理（需求：校方无效数据清理 / 坏图修复 / 去重，全部可撤销）。"""
import hashlib
import io
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..models import LibraryItem, User, WrongQuestion
from .skills import record_change

ZXW = "zhixuewang"


def _log(db, user, ctx, action, target_type, target_id, description, before=None, after=None):
    c = record_change(db, user, ctx, skill="zhixue_tidy", action=action,
                      target_type=target_type, target_id=target_id,
                      description=description, reason="智学网数据整理", before=before, after=after)
    return c


def _item_snapshot(it: LibraryItem) -> dict:
    return {"id": it.id, "subject": it.subject, "kind": it.kind, "title": it.title,
            "content": (it.content or "")[:500], "file_path": it.file_path,
            "external_id": it.external_id, "item_date": it.item_date,
            "board_id": it.board_id, "source": it.source}


async def tidy_zhixue_data(db: Session, user: User, cookie: str = "") -> dict:
    """
    1) 坏图修复：文件缺失的图片条目用 source_url 重下（带 Cookie）；失败则清理坏引用
    2) 无效数据清理：空内容无文件的智学网条目 / 无效错题 → 删除（记录变更可撤销）
    3) 去重：同标题+同学科+同日期+同内容的重复条目保留最新
    """
    from .zhixue import _download

    stats = {"images_fixed": 0, "images_dropped": 0, "junk_removed": 0, "dup_removed": 0}
    changes = []
    zxw_items = (db.query(LibraryItem)
                 .filter(LibraryItem.user_id == user.id, LibraryItem.source == ZXW)
                 .all())

    for it in zxw_items:
        # 1) 坏图修复
        if it.file_path:
            fpath = IMAGES_DIR / it.file_path.split("/")[-1]
            if not fpath.exists():
                blob = _download(it.source_url, cookie) if it.source_url else None
                if blob:
                    try:
                        from PIL import Image
                        img = Image.open(io.BytesIO(blob)).convert("RGB")
                        img.save(fpath, format="JPEG", quality=88)
                        it.ocr_status = "pending"
                        stats["images_fixed"] += 1
                        continue
                    except Exception:
                        pass
                # 修不好：清掉坏引用（条目本身保留文字信息）
                before = _item_snapshot(it)
                it.file_path = ""
                it.title = (it.title + "（图缺失）")[:256]
                stats["images_dropped"] += 1
                changes.append(_log(db, user, {}, "update", "library", it.id,
                                    f"清理坏图引用：{it.title[:30]}", before=before,
                                    after=_item_snapshot(it)))

    db.commit()

    # 2) 无效数据：空内容 + 无文件
    for it in (db.query(LibraryItem)
               .filter(LibraryItem.user_id == user.id, LibraryItem.source == ZXW).all()):
        empty = not (it.content or "").strip() and not it.file_path
        junk_title = it.title.strip() in ("", "无", "暂无", "无标题", "None")
        if empty or junk_title:
            before = _item_snapshot(it)
            changes.append(_log(db, user, {}, "delete", "library", it.id,
                                f"删除无效条目：{(it.title or '空条目')[:30]}", before=before))
            db.delete(it)
            stats["junk_removed"] += 1
    db.commit()

    # 3) 去重（标题+学科+日期+内容）
    seen: dict[tuple, LibraryItem] = {}
    for it in (db.query(LibraryItem)
               .filter(LibraryItem.user_id == user.id, LibraryItem.source == ZXW)
               .order_by(LibraryItem.id.desc()).all()):
        key = (it.title[:80], it.subject, it.item_date, (it.content or "")[:120], it.kind)
        if key in seen:
            before = _item_snapshot(it)
            changes.append(_log(db, user, {}, "delete", "library", it.id,
                                f"去重：{it.title[:30]}", before=before))
            db.delete(it)
            stats["dup_removed"] += 1
        else:
            seen[key] = it
    db.commit()

    # 4) 无效错题：题干空且无图
    for wq in (db.query(WrongQuestion)
               .filter(WrongQuestion.user_id == user.id).all()):
        if not (wq.question_text or "").strip() and not (wq.images or []):
            changes.append(_log(db, user, {}, "delete", "wrong_question", wq.id,
                                f"删除空错题 #{wq.id}", before={"id": wq.id}))
            db.delete(wq)
            stats["junk_removed"] += 1
    db.commit()

    stats["change_ids"] = [c.get("change_id") for c in changes if c.get("change_id")]
    return stats


NEEDS_FIX_RE = __import__("re").compile(r"(&[a-z]+;|<[^>]+>|略|暂无|无)")


def _needs_ai_fix(*texts: str) -> bool:
    joined = " ".join(t or "" for t in texts)
    return bool(NEEDS_FIX_RE.search(joined)) or not joined.strip()


async def ai_tidy_items(db: Session, user: User, cookie: str = "", limit: int = 12) -> dict:
    """AI 深度整理：清洗实体/伪内容、补全真实解法、判定无效（全部记变更可撤销）。"""
    from .. import prompts as prompts_mod
    from ..config import IMAGES_DIR as _IMD
    from .context import get_ai_client, get_vision_client
    from .zhixue import _download, _meaningless

    stats = {"cleaned": 0, "solutions_filled": 0, "junk_removed": 0, "failed": 0, "change_ids": []}
    ctx: dict = {}

    # ---- 错题：题干实体残留 / 解法为空或“略” ----
    wqs = (db.query(WrongQuestion)
           .filter(WrongQuestion.user_id == user.id)
           .order_by(WrongQuestion.created_at.desc()).limit(60).all())
    for wq in wqs[:limit]:
        needs = (_needs_ai_fix(wq.question_text, wq.correct_solution)
                 or not (wq.correct_solution or "").strip()
                 or (wq.wrong_reason or "").startswith("来自智学网错题本"))
        if not needs:
            continue
        img_path = ""
        if wq.images:
            cand = _IMD / wq.images[0].split("/")[-1]
            if cand.exists():
                img_path = cand.name
        try:
            if img_path:
                from .ai_client import image_to_data_uri
                uri = image_to_data_uri(int(img_path.split("_")[-1].split(".")[0]), user.id)
                client = get_vision_client(db, user)
                content = [{"type": "text", "text": "请清洗并补全这道错题的资料。"},
                           {"type": "image_url", "image_url": {"url": uri}}]
            else:
                client = get_ai_client(db, user)
                content = (f"【题干】\n{wq.question_text}\n【现有解法】\n{wq.correct_solution or '（空）'}"
                           f"\n【现有错因】\n{wq.wrong_reason or '（空）'}")
            data = await client.complete_json([
                {"role": "system", "content": prompts_mod.tidy_item_system_prompt()},
                {"role": "user", "content": content},
            ], temperature=0.2)
        except Exception:
            stats["failed"] += 1
            continue
        if not isinstance(data, dict):
            continue
        if data.get("is_junk"):
            before = {"id": wq.id, "question_text": wq.question_text[:200],
                      "correct_solution": (wq.correct_solution or "")[:200],
                      "wrong_reason": wq.wrong_reason, "images": wq.images}
            ch = record_change(db, user, ctx, skill="zhixue_ai_tidy", action="delete",
                               target_type="wrong_question", target_id=wq.id,
                               description=f"AI 判定无效错题并删除 #{wq.id}",
                               reason="AI 深度整理", before=before)
            stats["change_ids"].append(ch.get("change_id"))
            db.delete(wq)
            stats["junk_removed"] += 1
            db.commit()
            continue
        before = {"id": wq.id, "question_text": wq.question_text,
                  "correct_solution": wq.correct_solution, "wrong_reason": wq.wrong_reason,
                  "images": wq.images}
        changed = False
        if data.get("question_text") and data["question_text"] != wq.question_text:
            wq.question_text = str(data["question_text"])[:4000]
            changed = True
        if data.get("correct_solution") and not _meaningless(str(data["correct_solution"])):
            if wq.correct_solution != data["correct_solution"]:
                wq.correct_solution = str(data["correct_solution"])[:4000]
                stats["solutions_filled"] += 1
                changed = True
        if data.get("wrong_reason"):
            wq.wrong_reason = str(data["wrong_reason"])[:2000]
            changed = True
        if changed:
            ch = record_change(db, user, ctx, skill="zhixue_ai_tidy", action="update",
                               target_type="wrong_question", target_id=wq.id,
                               description=f"AI 清洗错题 #{wq.id}（题干/解法/错因）",
                               reason="AI 深度整理", before=before,
                               after={"id": wq.id, "question_text": wq.question_text[:200],
                                      "correct_solution": wq.correct_solution[:200]})
            stats["change_ids"].append(ch.get("change_id"))
            stats["cleaned"] += 1
            db.commit()

    # ---- 档案条目：实体残留 / 伪内容 ----
    items = (db.query(LibraryItem)
             .filter(LibraryItem.user_id == user.id, LibraryItem.source == ZXW)
             .order_by(LibraryItem.created_at.desc()).limit(60).all())
    for it in items[:limit]:
        if not _needs_ai_fix(it.title, it.content):
            continue
        img_name = ""
        if it.file_path:
            cand = _IMD / it.file_path.split("/")[-1]
            if cand.exists():
                img_name = cand.name
        try:
            if img_name:
                from .ai_client import image_to_data_uri
                uri = image_to_data_uri(int(img_name.split("_")[-1].split(".")[0]), user.id)
                client = get_vision_client(db, user)
                content = [{"type": "text", "text": "请清洗并补全这份学习资料。"},
                           {"type": "image_url", "image_url": {"url": uri}}]
            else:
                client = get_ai_client(db, user)
                content = f"【标题】\n{it.title}\n【内容】\n{it.content or '（空）'}"
            data = await client.complete_json([
                {"role": "system", "content": prompts_mod.tidy_item_system_prompt()},
                {"role": "user", "content": content},
            ], temperature=0.2)
        except Exception:
            stats["failed"] += 1
            continue
        if not isinstance(data, dict):
            continue
        if data.get("is_junk"):
            before = _item_snapshot(it)
            ch = record_change(db, user, ctx, skill="zhixue_ai_tidy", action="delete",
                               target_type="library", target_id=it.id,
                               description=f"AI 判定无效资料并删除：{it.title[:30]}",
                               reason="AI 深度整理", before=before)
            stats["change_ids"].append(ch.get("change_id"))
            db.delete(it)
            stats["junk_removed"] += 1
            db.commit()
            continue
        before = _item_snapshot(it)
        changed = False
        if data.get("title") and data["title"] != it.title:
            it.title = str(data["title"])[:256]
            changed = True
        if data.get("content"):
            it.content = str(data["content"])[:20000]
            changed = True
        if changed:
            ch = record_change(db, user, ctx, skill="zhixue_ai_tidy", action="update",
                               target_type="library", target_id=it.id,
                               description=f"AI 清洗资料：{it.title[:30]}",
                               reason="AI 深度整理", before=before, after=_item_snapshot(it))
            stats["change_ids"].append(ch.get("change_id"))
            stats["cleaned"] += 1
            db.commit()

    return stats
