from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import PracticeGoal, Report, User, MethodCard
from ..schemas import GoalCreate, GoalUpdate, MethodCreate, ScanHomeworkIn
from ..services import extras as extras_svc
from ..services import knowledge as knowledge_svc

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/knowledge/mindmap")
def mindmap(subject: str = Query("数学"), user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    return knowledge_svc.build_mindmap(db, user, subject)


@router.get("/knowledge/progress")
def progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return knowledge_svc.progress_summary(db, user)


@router.post("/knowledge/scan-homework")
async def scan_homework(payload: ScanHomeworkIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not payload.image_ids:
        raise HTTPException(status_code=400, detail="请先上传作业照片")
    try:
        result = await extras_svc.scan_homework(
            db, user, payload.subject, payload.grade or user.grade, payload.image_ids)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 识别失败：{e}")
    return result


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.profile import get_all_profiles
    rows = get_all_profiles(db, user)
    return [{"subject": r.subject, "content": r.content,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


@router.post("/profile")
def upsert_profile(payload: dict, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    from datetime import datetime
    from ..models import StudyProfile
    subject = payload.get("subject", "")
    content = payload.get("content", "")
    if not subject:
        raise HTTPException(status_code=400, detail="缺少学科")
    row = (db.query(StudyProfile)
           .filter(StudyProfile.user_id == user.id, StudyProfile.subject == subject).first())
    if not row:
        row = StudyProfile(user_id=user.id, subject=subject)
        db.add(row)
    row.content = content
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/profile/refresh")
async def refresh_profile(payload: dict, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    from ..services.profile import summarize_recent, update_profile_with_analysis
    subject = payload.get("subject", "")
    if not subject:
        raise HTTPException(status_code=400, detail="缺少学科")
    summary = summarize_recent(db, user, subject)
    try:
        content = await update_profile_with_analysis(db, user, subject, summary)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 更新档案失败：{e}")
    return {"content": content}


# ---------- 刷题目标 ----------
@router.get("/goals")
def list_goals(status: str = Query(""), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    q = db.query(PracticeGoal).filter(PracticeGoal.user_id == user.id)
    if status:
        q = q.filter(PracticeGoal.status == status)
    rows = q.order_by(PracticeGoal.created_at.desc()).all()
    return [{
        "id": g.id, "subject": g.subject, "title": g.title,
        "question_type": g.question_type, "description": g.description,
        "reason": g.reason, "status": g.status, "due_date": g.due_date,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    } for g in rows]


@router.post("/goals/generate")
async def generate_goals(payload: dict, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    try:
        goals = await extras_svc.generate_goals(db, user, payload.get("subject", ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 生成目标失败：{e}")
    return {"items": [{
        "id": g.id, "subject": g.subject, "title": g.title,
        "question_type": g.question_type, "description": g.description,
        "reason": g.reason, "status": g.status, "due_date": g.due_date,
    } for g in goals]}


@router.post("/goals")
def create_goal(payload: GoalCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    g = PracticeGoal(user_id=user.id, subject=payload.subject, title=payload.title,
                     question_type=payload.question_type, description=payload.description,
                     reason=payload.reason, due_date=payload.due_date)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id}


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, payload: GoalUpdate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    g = db.query(PracticeGoal).filter(PracticeGoal.id == goal_id,
                                      PracticeGoal.user_id == user.id).first()
    if not g:
        raise HTTPException(status_code=404, detail="目标不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    g = db.query(PracticeGoal).filter(PracticeGoal.id == goal_id,
                                      PracticeGoal.user_id == user.id).first()
    if g:
        db.delete(g)
        db.commit()
    return {"ok": True}


# ---------- 答题方法库 ----------
@router.get("/methods")
def list_methods(subject: str = Query(""), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    q = db.query(MethodCard).filter(MethodCard.user_id == user.id)
    if subject:
        q = q.filter(MethodCard.subject == subject)
    rows = q.order_by(MethodCard.created_at.desc()).limit(100).all()
    return [{
        "id": m.id, "subject": m.subject, "knowledge_point": m.knowledge_point,
        "question_type": m.question_type, "specific_method": m.specific_method,
        "general_method": m.general_method,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in rows]


@router.post("/methods/summarize")
async def summarize_method(payload: dict, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    subject = payload.get("subject", "")
    question = payload.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="缺少题目")
    try:
        data = await extras_svc.summarize_method(db, user, subject, question,
                                                 payload.get("ask", ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 总结失败：{e}")
    if data:
        db.add(MethodCard(
            user_id=user.id, subject=subject,
            knowledge_point=str(data.get("knowledge_point") or "")[:64],
            question_type=str(data.get("question_type") or "")[:64],
            specific_method=str(data.get("specific_method") or ""),
            general_method=str(data.get("general_method") or ""),
        ))
        db.commit()
    return data


@router.post("/methods")
def create_method(payload: MethodCreate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    m = MethodCard(user_id=user.id, subject=payload.subject,
                   knowledge_point=payload.knowledge_point,
                   question_type=payload.question_type,
                   specific_method=payload.specific_method,
                   general_method=payload.general_method)
    db.add(m)
    db.commit()
    return {"ok": True}


@router.delete("/methods/{method_id}")
def delete_method(method_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    m = db.query(MethodCard).filter(MethodCard.id == method_id,
                                    MethodCard.user_id == user.id).first()
    if m:
        db.delete(m)
        db.commit()
    return {"ok": True}


# ---------- 学习报告 ----------
@router.get("/reports")
def list_reports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Report).filter(Report.user_id == user.id)
            .order_by(Report.created_at.desc()).limit(20).all())
    return [{
        "id": r.id, "kind": r.kind, "title": r.title, "content": r.content,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/reports/generate")
async def generate_report(payload: dict, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    try:
        r = await extras_svc.generate_report(db, user, payload.get("subject", ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 生成报告失败：{e}")
    return {"id": r.id, "title": r.title, "content": r.content}
