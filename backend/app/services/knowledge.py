"""统一知识点/弱点节点树：CRUD、置信度、布局、进度。"""
import math
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import KnowledgeNode, User, WrongQuestion

MASTERY_ORDER = {"unknown": 0, "weak": 1, "improving": 2, "mastered": 3}
CONFIDENCE_THRESHOLD = 2  # ≥2 题才升级为 confirmed


def get_or_create_node(db: Session, user: User, subject: str, name: str,
                       parent_id: int | None = None, node_type: str = "knowledge",
                       source: str = "ai") -> KnowledgeNode:
    name = (name or "").strip()[:64]
    if not name:
        raise ValueError("节点名为空")
    q = db.query(KnowledgeNode).filter(
        KnowledgeNode.user_id == user.id,
        KnowledgeNode.subject == subject,
        KnowledgeNode.name == name,
    )
    node = q.first()
    if node:
        return node
    node = KnowledgeNode(
        user_id=user.id, subject=subject, parent_id=parent_id,
        name=name, node_type=node_type, source=source,
    )
    db.add(node)
    db.flush()
    return node


def touch_error(db: Session, user: User, subject: str, names: list[str],
                unit: str = "") -> list[KnowledgeNode]:
    """错题场景：确保节点存在并累计错题数、置信度升级、掌握度标记薄弱。"""
    touched = []
    parent = None
    if unit:
        parent = get_or_create_node(db, user, subject, unit, None, "knowledge")
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        node = get_or_create_node(db, user, subject, name, parent.id if parent else None, "knowledge")
        node.error_count = (node.error_count or 0) + 1
        node.updated_at = datetime.utcnow()
        if node.error_count >= CONFIDENCE_THRESHOLD:
            node.confidence = "confirmed"
        node.mastery = "weak"
        if node.learning_state != "learned":
            node.learning_state = "learning"
        touched.append(node)
    db.commit()
    return touched


def set_learning_items(db: Session, user: User, items: list[dict]) -> None:
    for it in items:
        name = (it.get("knowledge_point") or "").strip()
        if not name:
            continue
        subject = it.get("subject") or "综合"
        parent = None
        if it.get("unit"):
            parent = get_or_create_node(db, user, subject, it["unit"], None, "knowledge")
        node = get_or_create_node(db, user, subject, name, parent.id if parent else None)
        state = it.get("learning_state", "learning")
        if state in ("learning", "learned") and node.learning_state != "learned":
            node.learning_state = state
        if it.get("evidence"):
            node.note = str(it["evidence"])[:200]
        node.updated_at = datetime.utcnow()
    db.commit()


def _auto_positions(db: Session, user: User, subject: str) -> None:
    """为无位置的节点做极坐标自动布局（已定位的保持不变）。"""
    nodes = (db.query(KnowledgeNode)
             .filter(KnowledgeNode.user_id == user.id, KnowledgeNode.subject == subject)
             .all())
    roots = [n for n in nodes if not n.parent_id]
    for i, root in enumerate(roots):
        if root.pos_x is None or root.pos_y is None:
            root.pos_x = 0
            root.pos_y = 0
        children = [n for n in nodes if n.parent_id == root.id]
        need = [n for n in children if n.pos_x is None or n.pos_y is None]
        if not need:
            continue
        n = len(children) or 1
        radius = 240
        for j, node in enumerate(need):
            angle = (2 * math.pi * (i + j / max(len(need), 1)) / max(len(roots), 1)) - math.pi / 2
            node.pos_x = root.pos_x + radius * math.cos(angle) * (1 + 0.3 * (j % 2))
            node.pos_y = root.pos_y + radius * math.sin(angle) * (1 + 0.3 * (j % 2))
    db.commit()


def build_mindmap(db: Session, user: User, subject: str, kind_filter: str = "") -> dict:
    _auto_positions(db, user, subject)
    q = db.query(KnowledgeNode).filter(
        KnowledgeNode.user_id == user.id, KnowledgeNode.subject == subject)
    nodes = q.order_by(KnowledgeNode.sort_order, KnowledgeNode.id).all()
    by_id = {n.id: n for n in nodes}

    def keep(n: KnowledgeNode) -> bool:
        if not kind_filter or kind_filter == "all":
            return True
        return n.node_type == kind_filter

    node_items = [{
        "id": "root",
        "label": subject,
        "kind": "root",
        "nodeType": "subject",
        "mastery": "unknown",
        "confidence": "confirmed",
        "errorCount": 0,
        "learningState": "learning",
        "note": "",
        "description": "",
        "source": "ai",
        "position": {"x": 0, "y": 0},
        "realId": 0,
    }]
    edge_items = []
    for n in nodes:
        # 筛选时保留父链，避免孤岛
        visible = keep(n)
        if not visible:
            continue
        node_items.append({
            "id": f"n{n.id}",
            "label": n.name,
            "kind": "root" if not n.parent_id else ("weakness" if n.node_type == "weakness" else "kp"),
            "nodeType": n.node_type,
            "mastery": n.mastery,
            "confidence": n.confidence,
            "errorCount": n.error_count or 0,
            "learningState": n.learning_state,
            "note": n.note,
            "description": n.description,
            "source": n.source,
            "position": {"x": n.pos_x or 0, "y": n.pos_y or 0},
            "realId": n.id,
        })
        if n.parent_id and f"n{n.parent_id}" != f"n{n.id}":
            edge_items.append({
                "id": f"e{n.parent_id}-{n.id}",
                "source": f"n{n.parent_id}",
                "target": f"n{n.id}",
            })
    # 顶层节点连到学科中心；父节点被筛掉的子节点同样挂到中心
    visible_ids = {i["id"] for i in node_items}
    for n in nodes:
        if keep(n):
            has_parent_edge = any(e["target"] == f"n{n.id}" for e in edge_items)
            if not has_parent_edge:
                edge_items.append({"id": f"e0-{n.id}", "source": "root", "target": f"n{n.id}"})
    return {"nodes": node_items, "edges": edge_items, "subject": subject}


def progress_summary(db: Session, user: User) -> dict:
    nodes = (db.query(KnowledgeNode)
             .filter(KnowledgeNode.user_id == user.id)
             .all())
    by_subject: dict[str, dict] = {}
    for n in nodes:
        d = by_subject.setdefault(n.subject, {
            "weak": [], "improving": [], "mastered": [], "unknown": [],
            "learning": 0, "learned": 0, "not_started": 0, "total": 0,
        })
        d.get(n.mastery, d["unknown"]).append(n.name)
        d[n.learning_state] = d.get(n.learning_state, 0) + 1
        d["total"] += 1
    return by_subject


def serialize_node(n: KnowledgeNode) -> dict:
    return {
        "id": n.id,
        "subject": n.subject,
        "parent_id": n.parent_id,
        "name": n.name,
        "node_type": n.node_type,
        "confidence": n.confidence,
        "mastery": n.mastery,
        "learning_state": n.learning_state,
        "error_count": n.error_count,
        "note": n.note,
        "description": n.description,
        "source": n.source,
        "pos_x": n.pos_x,
        "pos_y": n.pos_y,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
