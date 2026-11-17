import io
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import String, or_
from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..database import SessionLocal, get_db
from ..deps import get_current_user
from ..models import User, WrongQuestion
from ..schemas import AnalyzeIn, WrongQuestionUpdate
from ..services import profile as profile_svc
from ..services.ai_client import build_user_content
from ..services.context import get_vision_client
from ..services.wrong_question import analyze_and_save

router = APIRouter(prefix="/api/wrong-questions", tags=["wrong-questions"])


def _background_profile_update(user_id: int, subject: str, summary: str) -> None:
    """档案更新走后台任务，避免阻塞分析响应（修「思考中」卡住问题）。"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            import asyncio
            asyncio.run(profile_svc.update_profile_with_analysis(db, user, subject, summary))
    except Exception:
        pass
    finally:
        db.close()


def _serialize(w: WrongQuestion) -> dict:
    return {
        "id": w.id,
        "subject": w.subject,
        "grade": w.grade,
        "unit": w.unit,
        "knowledge_points": w.knowledge_points or [],
        "difficulty": w.difficulty,
        "question_text": w.question_text,
        "wrong_reason": w.wrong_reason,
        "correct_solution": w.correct_solution,
        "key_points": w.key_points or [],
        "extensions": w.extensions,
        "method_specific": w.method_specific,
        "method_general": w.method_general,
        "learning_content": w.learning_content,
        "images": w.images or [],
        "original_images": w.original_images or w.images or [],
        "source": w.source,
        "my_question": w.my_question,
        "is_reviewed": w.is_reviewed,
        "mastery": w.mastery,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.post("/upload")
async def upload_images(user: User = Depends(get_current_user),
                        files: list[UploadFile] = File(...)):
    ids = []
    for f in files[:12]:
        data = await f.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="单张图片不能超过 15MB")
        try:
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status_code=400, detail="请上传有效的图片文件（JPG/PNG/WebP）")
        iid = int(uuid.uuid4().int % 1_000_000_000)
        path = IMAGES_DIR / f"u{user.id}_{iid}.jpg"
        img.save(path, format="JPEG", quality=88)
        ids.append(iid)
    return {"image_ids": ids}


def _image_url(user_id: int, image_id: int) -> str:
    return f"/api/images/u{user_id}_{image_id}.jpg"


@router.post("/analyze")
async def analyze(payload: AnalyzeIn, background: BackgroundTasks,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        rows = await analyze_and_save(
            db, user,
            subject=payload.subject or "数学",
            grade=payload.grade or user.grade,
            mode=payload.mode,
            text=payload.text,
            my_question=payload.my_question,
            image_ids=payload.image_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 分析失败：{e}")
    if not rows:
        raise HTTPException(status_code=502, detail="AI 未能识别出有效题目，请换更清晰的图片")
    summary = "\n".join(
        f"知识点{w.knowledge_points} 错因:{(w.wrong_reason or '')[:150]}" for w in rows
    )
    background.add_task(_background_profile_update, user.id, rows[0].subject, summary)
    # 汇入该科老师的常驻对话流（v6：不单开对话）
    from ..services.teachers import post_to_teacher_thread
    report = "\n\n".join(
        f"## 新错题分析\n**题目**：{w.question_text[:120]}\n**错因**：{(w.wrong_reason or '')[:200]}\n"
        f"**知识点**：{'、'.join(w.knowledge_points or [])}" for w in rows)
    tid = post_to_teacher_thread(db, user, rows[0].subject or "综合", report[:4000])
    return {"items": [_serialize(w) for w in rows], "teacher_thread_id": tid}


@router.post("/detect-questions")
async def detect_questions(payload: AnalyzeIn, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """整页照片 → 仅识别题目清单（不作答），供用户勾选哪道题错了（需求 13）。"""
    if not payload.image_ids:
        raise HTTPException(status_code=400, detail="请先上传照片")
    from .. import prompts as prompts_mod
    client = get_vision_client(db, user)
    system = prompts_mod.detect_questions_system_prompt(payload.subject or "",
                                                        payload.grade or user.grade)
    content = build_user_content("请识别这页上的所有题目。", payload.image_ids, user.id,
                                 max_images=getattr(client, "max_images", 10))
    try:
        data = await client.complete_json([
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ], temperature=0.2)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 识别失败：{e}")
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list):
        questions = []
    return {"questions": questions[:20]}


@router.post("/analyze-selected")
async def analyze_selected(payload: dict, background: BackgroundTasks,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """用户从整页中勾选的题目 + 错因 → 针对该题深度分析（需求 13）。"""
    question_text = str(payload.get("question_text") or "").strip()
    if not question_text:
        raise HTTPException(status_code=400, detail="缺少题目")
    wrong_hint = str(payload.get("wrong_hint") or "").strip()
    subject = str(payload.get("subject") or "")
    grade = str(payload.get("grade") or user.grade or "")
    from .. import prompts as prompts_mod
    from ..services.wrong_question import _normalize
    client = get_vision_client(db, user)
    system = prompts_mod.analyze_selected_question_system_prompt(subject, grade)
    instruct = f"【选出的题目】\n{question_text}\n\n【我的错因说明】{wrong_hint or '（未填写）'}"
    image_ids = payload.get("image_ids") or []
    content = build_user_content(instruct, image_ids, user.id,
                                 max_images=getattr(client, "max_images", 10))
    try:
        data = await client.complete_json([
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ], temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 分析失败：{e}")
    item = data if isinstance(data, dict) else {}
    norm = _normalize(item, subject, grade)
    if not norm["question_text"] and not norm["correct_solution"]:
        raise HTTPException(status_code=502, detail="AI 未能分析该题")
    from ..models import LibraryItem
    image_urls = [f"/api/images/u{user.id}_{iid}.jpg" for iid in image_ids]
    wq = WrongQuestion(
        user_id=user.id, source="photo" if image_ids else "text",
        my_question=wrong_hint,
        images=image_urls[:1], original_images=image_urls,
        **norm,
    )
    db.add(wq)
    db.flush()
    if wq.knowledge_points:
        from ..services.knowledge import touch_error
        touch_error(db, user, wq.subject, wq.knowledge_points, unit=wq.unit)
    for img in (wq.images or []):
        fname = img.split("/")[-1]
        db.add(LibraryItem(
            user_id=user.id, subject=wq.subject, kind="wrong_question",
            title=(wq.question_text or "错题照片")[:256],
            content=(wq.wrong_reason or "")[:2000],
            file_path=fname, file_name=fname, file_type="image/jpeg",
            source="wrong_question", ocr_text=(wq.question_text or "")[:2000],
            ocr_status="pending"))
    db.commit()
    db.refresh(wq)
    summary = f"知识点{wq.knowledge_points} 错因:{(wq.wrong_reason or '')[:150]}"
    background.add_task(_background_profile_update, user.id, wq.subject, summary)
    from ..services.teachers import post_to_teacher_thread
    report = (f"## 新错题分析\n**题目**：{(wq.question_text or '')[:120]}\n"
              f"**错因**：{(wq.wrong_reason or '')[:200]}\n"
              f"**知识点**：{'、'.join(wq.knowledge_points or [])}")
    tid = post_to_teacher_thread(db, user, wq.subject or "综合", report[:4000])
    return {"item": _serialize(wq), "teacher_thread_id": tid}


@router.get("")
def list_questions(
    subject: str = Query(""),
    grade: str = Query(""),
    keyword: str = Query(""),
    mastery: str = Query(""),
    reviewed: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if subject:
        q = q.filter(WrongQuestion.subject == subject)
    if grade:
        q = q.filter(WrongQuestion.grade == grade)
    if mastery:
        q = q.filter(WrongQuestion.mastery == mastery)
    if reviewed == "1":
        q = q.filter(WrongQuestion.is_reviewed.is_(True))
    elif reviewed == "0":
        q = q.filter(WrongQuestion.is_reviewed.is_(False))
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(WrongQuestion.question_text.like(like),
                         WrongQuestion.wrong_reason.like(like),
                         WrongQuestion.correct_solution.like(like),
                         WrongQuestion.unit.like(like),
                         WrongQuestion.knowledge_points.cast(String).like(like)))
    total = q.count()
    rows = q.order_by(WrongQuestion.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_serialize(w) for w in rows]}


@router.get("/{wq_id}")
def get_question(wq_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    w = db.query(WrongQuestion).filter(WrongQuestion.id == wq_id,
                                       WrongQuestion.user_id == user.id).first()
    if not w:
        raise HTTPException(status_code=404, detail="错题不存在")
    return _serialize(w)


@router.put("/{wq_id}")
def update_question(wq_id: int, payload: WrongQuestionUpdate,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    w = db.query(WrongQuestion).filter(WrongQuestion.id == wq_id,
                                       WrongQuestion.user_id == user.id).first()
    if not w:
        raise HTTPException(status_code=404, detail="错题不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_reviewed") and not w.is_reviewed:
        from datetime import datetime
        w.reviewed_at = datetime.utcnow()
    for k, v in data.items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return _serialize(w)


@router.delete("/{wq_id}")
def delete_question(wq_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    w = db.query(WrongQuestion).filter(WrongQuestion.id == wq_id,
                                       WrongQuestion.user_id == user.id).first()
    if not w:
        raise HTTPException(status_code=404, detail="错题不存在")
    db.delete(w)
    db.commit()
    return {"ok": True}
