from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import KnowledgeNode, PracticeGoal, Report, User, MethodCard, WrongQuestion
from ..schemas import GoalCreate, GoalUpdate, MethodCreate, ScanHomeworkIn
from ..services import extras as extras_svc
from ..services import knowledge as knowledge_svc
from ..services.context import get_ai_client
from .. import prompts

router = APIRouter(prefix="/api", tags=["knowledge"])


# ---------- 图谱 / 节点 ----------
@router.get("/knowledge/mindmap")
def mindmap(subject: str = Query("数学"), kind: str = Query(""),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return knowledge_svc.build_mindmap(db, user, subject, kind)


@router.get("/knowledge/nodes")
def list_nodes(subject: str = Query(""), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    q = db.query(KnowledgeNode).filter(KnowledgeNode.user_id == user.id)
    if subject:
        q = q.filter(KnowledgeNode.subject == subject)
    nodes = q.order_by(KnowledgeNode.sort_order, KnowledgeNode.id).all()
    return [knowledge_svc.serialize_node(n) for n in nodes]


@router.post("/knowledge/nodes")
def create_node(payload: dict, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    subject = (payload.get("subject") or "").strip()
    if not name or not subject:
        raise HTTPException(status_code=400, detail="缺少节点名或学科")
    node_type = payload.get("node_type", "knowledge")
    if node_type not in ("knowledge", "weakness"):
        node_type = "knowledge"
    parent_id = payload.get("parent_id")
    if not parent_id and payload.get("parent_name"):
        parent = knowledge_svc.get_or_create_node(db, user, subject, str(payload["parent_name"]).strip())
        parent_id = parent.id
    node = knowledge_svc.get_or_create_node(
        db, user, subject, name, parent_id, node_type,
        source=payload.get("source", "manual"))
    if payload.get("description"):
        node.description = str(payload["description"])[:2000]
    if payload.get("confidence") in ("suspected", "confirmed"):
        node.confidence = payload["confidence"]
    db.commit()
    db.refresh(node)
    return knowledge_svc.serialize_node(node)


@router.put("/knowledge/nodes/{node_id}")
def update_node(node_id: int, payload: dict, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    node = db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id,
                                          KnowledgeNode.user_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if "name" in payload and payload["name"]:
        node.name = str(payload["name"]).strip()[:64]
    if "description" in payload:
        node.description = str(payload["description"] or "")[:2000]
    if "note" in payload:
        node.note = str(payload["note"] or "")[:1000]
    if "mastery" in payload and payload["mastery"] in ("unknown", "weak", "improving", "mastered"):
        node.mastery = payload["mastery"]
    if "confidence" in payload and payload["confidence"] in ("suspected", "confirmed"):
        node.confidence = payload["confidence"]
    if "node_type" in payload and payload["node_type"] in ("knowledge", "weakness"):
        node.node_type = payload["node_type"]
    if "learning_state" in payload and payload["learning_state"] in ("not_started", "learning", "learned"):
        node.learning_state = payload["learning_state"]
    if "pos_x" in payload:
        node.pos_x = float(payload["pos_x"])
    if "pos_y" in payload:
        node.pos_y = float(payload["pos_y"])
    from datetime import datetime
    node.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(node)
    return knowledge_svc.serialize_node(node)


@router.post("/knowledge/nodes/positions")
def save_positions(payload: dict, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    items = payload.get("positions") or []
    for it in items:
        node = db.query(KnowledgeNode).filter(KnowledgeNode.id == int(it.get("id", 0)),
                                              KnowledgeNode.user_id == user.id).first()
        if node:
            node.pos_x = float(it.get("x", node.pos_x or 0))
            node.pos_y = float(it.get("y", node.pos_y or 0))
    db.commit()
    return {"ok": True}


@router.delete("/knowledge/nodes/{node_id}")
def delete_node(node_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    node = db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id,
                                          KnowledgeNode.user_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    def cascade(rid: int):
        kids = db.query(KnowledgeNode).filter(KnowledgeNode.parent_id == rid).all()
        for k in kids:
            cascade(k.id)
        db.query(KnowledgeNode).filter(KnowledgeNode.id == rid).delete(synchronize_session=False)

    cascade(node_id)
    db.commit()
    return {"ok": True}


@router.post("/knowledge/nodes/apply")
def apply_proposals(payload: dict, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """应用「总结成知识点」产生的节点变更（用户已勾选确认）。"""
    applied = []
    for p in payload.get("proposals") or []:
        action = p.get("action", "add")
        subject = p.get("subject") or "综合"
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if action == "delete":
            if p.get("node_id"):
                node = db.query(KnowledgeNode).filter(
                    KnowledgeNode.id == int(p["node_id"]),
                    KnowledgeNode.user_id == user.id).first()
                if node:
                    db.delete(node)
                    applied.append({"action": "delete", "name": name})
            continue
        parent_id = None
        parent_name = (p.get("parent_name") or "").strip()
        if parent_name:
            parent = knowledge_svc.get_or_create_node(db, user, subject, parent_name)
            parent_id = parent.id
        node_type = p.get("node_type", "knowledge")
        if node_type not in ("knowledge", "weakness"):
            node_type = "knowledge"
        if action == "update" and p.get("node_id"):
            node = db.query(KnowledgeNode).filter(
                KnowledgeNode.id == int(p["node_id"]),
                KnowledgeNode.user_id == user.id).first()
            if not node:
                continue
            node.name = name
            node.node_type = node_type
            if p.get("confidence"):
                node.confidence = p["confidence"]
            if p.get("reason"):
                node.note = str(p["reason"])[:200]
            applied.append({"action": "update", "id": node.id, "name": name})
        else:
            node = knowledge_svc.get_or_create_node(
                db, user, subject, name, parent_id, node_type, source="chat_summary")
            if p.get("confidence") in ("suspected", "confirmed"):
                node.confidence = p["confidence"]
            if p.get("reason"):
                node.note = str(p["reason"])[:200]
            applied.append({"action": "add", "id": node.id, "name": name})
        for c in (p.get("children") or [])[:3]:
            cname = (c.get("name") or "").strip()
            if cname:
                child = knowledge_svc.get_or_create_node(
                    db, user, subject, cname, node.id,
                    c.get("node_type", "knowledge"), source="chat_summary")
                applied.append({"action": "add", "id": child.id, "name": cname})
    db.commit()
    return {"ok": True, "applied": applied}


@router.post("/knowledge/nodes/{node_id}/resummarize")
async def resummarize_node(node_id: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """AI 结合相关错题重新总结该节点。"""
    node = db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id,
                                          KnowledgeNode.user_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    related = (db.query(WrongQuestion)
               .filter(WrongQuestion.user_id == user.id, WrongQuestion.subject == node.subject)
               .order_by(WrongQuestion.created_at.desc()).limit(30).all())
    rows = [w for w in related if node.name in (w.knowledge_points or [])][:6]
    ctx = "\n".join(
        f"- 题目：{(w.question_text or '')[:100]}\n  错因：{(w.wrong_reason or '')[:100]}"
        for w in rows) or "（暂无相关错题）"
    client = get_ai_client(db, user)
    try:
        data = await client.complete_json([
            {"role": "system", "content": prompts.resummarize_node_system_prompt(node.subject)},
            {"role": "user", "content": f"节点：{node.name}\n类型：{node.node_type}\n现有描述：{node.description}\n\n【相关错题】\n{ctx}"},
        ], temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 重总结失败：{e}")
    if isinstance(data, dict):
        if data.get("name"):
            node.name = str(data["name"]).strip()[:64]
        if data.get("node_type") in ("knowledge", "weakness"):
            node.node_type = data["node_type"]
        if data.get("confidence") in ("suspected", "confirmed"):
            node.confidence = data["confidence"]
        if data.get("description"):
            node.description = str(data["description"])[:2000]
        for c in (data.get("children") or [])[:3]:
            cname = (c.get("name") or "").strip()
            if cname:
                knowledge_svc.get_or_create_node(db, user, node.subject, cname, node.id,
                                                 c.get("node_type", "knowledge"), source="ai")
        if data.get("reason"):
            node.note = str(data["reason"])[:200]
        from datetime import datetime
        node.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(node)
    return knowledge_svc.serialize_node(node)


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


# ---------- 学习档案 ----------
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
