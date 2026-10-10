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
    for f in files[:8]:
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
    return {"items": [_serialize(w) for w in rows]}


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
