"""变更日志：列表 + 允许/撤销审核（v6：夜间改动默认待审）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (ChangeLog, KnowledgeNode, LibraryItem, MethodCard,
                      PracticeGoal, StudyProfile, User, WrongQuestion)
from ..services.knowledge import get_or_create_node

router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.get("")
def list_changes(limit: int = Query(50, le=200), undone: str = Query(""),
                 status: str = Query(""), source: str = Query(""),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ChangeLog).filter(ChangeLog.user_id == user.id)
    if undone == "0":
        q = q.filter(ChangeLog.undone.is_(False))
    if status:
        q = q.filter(ChangeLog.status == status)
    if source:
        q = q.filter(ChangeLog.source == source)
    rows = q.order_by(ChangeLog.created_at.desc()).limit(limit).all()
    return [{
        "id": c.id, "skill": c.skill, "action": c.action,
        "target_type": c.target_type, "target_id": c.target_id,
        "description": c.description, "reason": c.reason,
        "undone": c.undone, "status": c.status, "source": c.source,
        "conversation_id": c.conversation_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows]


def _restore_node(db: Session, user: User, snap: dict) -> int | None:
    """按快照恢复节点（不存在则重建）。"""
    node = db.query(KnowledgeNode).filter(
        KnowledgeNode.id == snap.get("id"),
        KnowledgeNode.user_id == user.id).first()
    subject = snap.get("subject") or "综合"
    name = snap.get("name") or ""
    if not name:
        return None
    if not node:
        node = db.query(KnowledgeNode).filter(
            KnowledgeNode.user_id == user.id, KnowledgeNode.subject == subject,
            KnowledgeNode.name == name).first()
    if not node:
        parent_id = None
        if snap.get("parent_name"):
            parent = get_or_create_node(db, user, subject, snap["parent_name"])
            parent_id = parent.id
        node = get_or_create_node(db, user, subject, name, parent_id,
                                  snap.get("node_type", "knowledge"))
    node.name = name
    node.description = snap.get("description") or ""
    node.note = snap.get("note") or ""
    node.mastery = snap.get("mastery") or "unknown"
    node.confidence = snap.get("confidence") or "suspected"
    node.node_type = snap.get("node_type") or "knowledge"
    node.learning_state = snap.get("learning_state") or "not_started"
    node.error_count = snap.get("error_count") or 0
    if snap.get("pos_x") is not None:
        node.pos_x = snap["pos_x"]
    if snap.get("pos_y") is not None:
        node.pos_y = snap["pos_y"]
    db.flush()
    return node.id


def undo_change_record(db: Session, user: User, c: ChangeLog) -> None:
    """执行撤销：恢复 before 快照（幂等由调用方保证）。"""
    if c.target_type == "node":
        if c.action == "create":
            node = db.query(KnowledgeNode).filter(
                KnowledgeNode.id == c.target_id,
                KnowledgeNode.user_id == user.id).first()
            if node:
                db.query(KnowledgeNode).filter(KnowledgeNode.parent_id == node.id).delete(
                    synchronize_session=False)
                db.delete(node)
        else:
            if c.before:
                _restore_node(db, user, c.before)
    elif c.target_type == "profile":
        row = db.query(StudyProfile).filter(StudyProfile.id == c.target_id,
                                            StudyProfile.user_id == user.id).first()
        before_content = (c.before or {}).get("content", "")
        if not before_content:
            if row:
                db.delete(row)
        elif row:
            row.content = before_content
    elif c.target_type == "goal":
        g = db.query(PracticeGoal).filter(PracticeGoal.id == c.target_id,
                                          PracticeGoal.user_id == user.id).first()
        if c.action == "create":
            if g:
                db.delete(g)
        elif g and c.before:
            for k, v in c.before.items():
                if hasattr(g, k) and k != "id":
                    setattr(g, k, v)
    elif c.target_type == "method":
        if c.action == "create":
            m = db.query(MethodCard).filter(MethodCard.id == c.target_id,
                                            MethodCard.user_id == user.id).first()
            if m:
                db.delete(m)
    elif c.target_type == "library":
        if c.action == "delete" and c.before:
            it = LibraryItem(user_id=user.id, **{k: v for k, v in c.before.items()
                                                 if hasattr(LibraryItem, k) and k != "id"})
            db.add(it)
        elif c.action == "create":
            it = db.query(LibraryItem).filter(LibraryItem.id == c.target_id,
                                              LibraryItem.user_id == user.id).first()
            if it:
                db.delete(it)
        elif c.before:
            it = db.query(LibraryItem).filter(LibraryItem.id == c.target_id,
                                              LibraryItem.user_id == user.id).first()
            if it:
                for k, v in c.before.items():
                    if hasattr(it, k) and k != "id":
                        setattr(it, k, v)
    elif c.target_type == "learning_items":
        pass  # 进度类更新为累积性，撤销不回退
    elif c.target_type == "wrong_question":
        if c.action == "delete":
            wq = WrongQuestion(user_id=user.id,
                               subject=(c.before or {}).get("subject", "综合"),
                               question_text=(c.before or {}).get("question_text", ""),
                               correct_solution=(c.before or {}).get("correct_solution", ""),
                               wrong_reason=(c.before or {}).get("wrong_reason", ""),
                               images=(c.before or {}).get("images") or [],
                               mastery="weak")
            db.add(wq)
        else:
            wq = db.query(WrongQuestion).filter(WrongQuestion.id == c.target_id,
                                                WrongQuestion.user_id == user.id).first()
            if wq and c.before:
                for k, v in c.before.items():
                    if hasattr(wq, k) and k != "id":
                        setattr(wq, k, v)
    c.undone = True
    c.status = "revoked"
    db.commit()


@router.post("/{change_id}/undo")
def undo_change(change_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    c = db.query(ChangeLog).filter(ChangeLog.id == change_id,
                                   ChangeLog.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="变更记录不存在")
    if c.undone:
        raise HTTPException(status_code=400, detail="该变更已撤销")
    undo_change_record(db, user, c)
    return {"ok": True, "description": c.description}


@router.post("/{change_id}/approve")
def approve_change(change_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    c = db.query(ChangeLog).filter(ChangeLog.id == change_id,
                                   ChangeLog.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="变更记录不存在")
    c.status = "approved"
    db.commit()
    return {"ok": True}


@router.post("/approve-batch")
def approve_batch(payload: dict, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """批量允许/撤销。参数：ids(list)、action(approve|revoke)"""
    ids = [int(i) for i in (payload.get("ids") or [])][:100]
    action = payload.get("action") or "approve"
    done = 0
    for cid in ids:
        c = db.query(ChangeLog).filter(ChangeLog.id == cid,
                                       ChangeLog.user_id == user.id).first()
        if not c:
            continue
        if action == "revoke":
            if not c.undone:
                undo_change_record(db, user, c)
                done += 1
        else:
            c.status = "approved"
            done += 1
    db.commit()
    return {"ok": True, "done": done}