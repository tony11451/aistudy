"""错题分析与入库。"""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import prompts
from ..models import MethodCard, User, WrongQuestion
from .ai_client import build_user_content
from .context import get_vision_client
from .knowledge import touch_error


def _normalize(item: dict, subject: str, grade: str) -> dict:
    method = item.get("method") or {}
    if isinstance(method, str):
        method = {"specific": method, "general": ""}
    kps = item.get("knowledge_points") or []
    if isinstance(kps, str):
        kps = [kps]
    return {
        "subject": item.get("subject") or subject or "综合",
        "grade": grade,
        "unit": str(item.get("unit") or "")[:64],
        "knowledge_points": [str(k)[:64] for k in kps][:8],
        "difficulty": str(item.get("difficulty") or "中等")[:16],
        "question_text": str(item.get("question_text") or ""),
        "wrong_reason": str(item.get("wrong_reason") or ""),
        "correct_solution": str(item.get("correct_solution") or ""),
        "key_points": [str(k) for k in (item.get("key_points") or [])][:10],
        "extensions": str(item.get("extensions") or ""),
        "learning_content": str(item.get("learning_content") or "")[:128],
        "method_specific": str(method.get("specific") or "")[:4000],
        "method_general": str(method.get("general") or "")[:4000],
        "analysis_raw": item,
    }


async def analyze_and_save(db: Session, user: User, *, subject: str, grade: str,
                           mode: str, text: str, my_question: str,
                           image_ids: list[int]) -> list[WrongQuestion]:
    client = get_vision_client(db, user)
    grade = grade or user.grade or ""
    auto_subject = (not subject) or subject == "自动识别"
    subject = "" if auto_subject else subject
    instruct = text or ""
    if my_question:
        instruct = (instruct + "\n\n【我的问题】" + my_question).strip() if instruct else "【我的问题】" + my_question
    if auto_subject:
        instruct = (instruct + "\n\n请自动识别每道题所属学科，在输出 JSON 的 subject 字段给出（语文/数学/英语/物理/化学/生物/历史/地理/道德与法治）。").strip()

    if mode == "batch":
        system = prompts.batch_question_system_prompt(subject or "自动识别", grade)
        instruct = instruct or "请识别并分析这页作业中的所有错题。"
    else:
        system = prompts.wrong_question_system_prompt(subject or "自动识别", grade)
        instruct = instruct or "请识别并分析这道错题。"

    content = build_user_content(instruct, image_ids, user.id,
                                 max_images=getattr(client, "max_images", 10))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    data = await client.complete_json(messages, temperature=0.3)

    image_urls = [f"/api/images/u{user.id}_{iid}.jpg" for iid in image_ids]
    items = data if isinstance(data, list) else [data]
    saved: list[WrongQuestion] = []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        norm = _normalize(item, subject, grade)
        if not norm["question_text"] and not norm["correct_solution"]:
            continue
        wq = WrongQuestion(
            user_id=user.id,
            source="batch" if mode == "batch" else ("photo" if image_ids else "text"),
            my_question=my_question,
            images=image_urls if len(items) == 1 else image_urls[:1],
            original_images=image_urls,
            created_at=datetime.utcnow(),
            **norm,
        )
        db.add(wq)
        saved.append(wq)
    db.flush()

    for wq in saved:
        if wq.knowledge_points:
            touch_error(db, user, wq.subject, wq.knowledge_points, unit=wq.unit)
        if wq.method_specific or wq.method_general:
            db.add(MethodCard(
                user_id=user.id,
                subject=wq.subject,
                knowledge_point=(wq.knowledge_points or [""])[0],
                question_type=wq.difficulty or "",
                specific_method=wq.method_specific,
                general_method=wq.method_general,
                source_question_id=wq.id,
            ))
    # 错题照片自动归档进档案库（需求 12：图片库，可手动归入书本/板块）
    from ..models import LibraryItem
    for wq in saved:
        for img in (wq.images or []):
            fname = img.split("/")[-1]
            db.add(LibraryItem(
                user_id=user.id, subject=wq.subject, kind="wrong_question",
                title=(wq.question_text or "错题照片")[:256],
                content=(wq.wrong_reason or "")[:2000],
                file_path=fname, file_name=fname, file_type="image/jpeg",
                source="wrong_question",
                ocr_text=(wq.question_text or "")[:2000],
                ocr_status="pending"))
    db.commit()
    for wq in saved:
        db.refresh(wq)
    return saved
