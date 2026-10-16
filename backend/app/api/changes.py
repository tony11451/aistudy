"""变更日志：列表 + 撤销（恢复 before 快照）。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (ChangeLog, KnowledgeNode, MethodCard, PracticeGoal,
                      StudyProfile, User)
from ..services.knowledge import get_or_create_node

router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.get("")
def list_changes(limit: int = Query(50, le=200), undone: str = Query(""),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ChangeLog).filter(ChangeLog.user_id == user.id)
    if undone == "0":
        q = q.filter(ChangeLog.undone.is_(False))
    rows = q.order_by(ChangeLog.created_at.desc()).limit(limit).all()
    return [{
        "id": c.id, "skill": c.skill, "action": c.action,
        "target_type": c.target_type, "target_id": c.target_id,
        "description": c.description, "reason": c.reason,
        "undone": c.undone, "conversation_id": c.conversation_id,
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


@router.post("/{change_id}/undo")
def undo_change(change_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    c = db.query(ChangeLog).filter(ChangeLog.id == change_id,
                                   ChangeLog.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="变更记录不存在")
    if c.undone:
        raise HTTPException(status_code=400, detail="该变更已撤销")

    if c.target_type == "node":
        if c.action == "create":
            node = db.query(KnowledgeNode).filter(
                KnowledgeNode.id == c.target_id,
                KnowledgeNode.user_id == user.id).first()
            if node:
                db.query(KnowledgeNode).filter(KnowledgeNode.parent_id == node.id).delete(
                    synchronize_session=False)
                db.delete(node)
        elif c.action == "delete":
            if c.before:
                _restore_node(db, user, c.before)
        else:  # update
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

    c.undone = True
    db.commit()
    return {"ok": True, "description": c.description}
