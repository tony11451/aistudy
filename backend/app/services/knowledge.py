"""知识点管理、学习进度、思维导图数据。"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import KnowledgePoint, User, UserKnowledgeStatus, WrongQuestion

MINDMAP_MASTERY = {"unknown", "weak", "improving", "mastered"}
MINDMAP_STATE = {"not_started", "learning", "learned"}


def upsert_knowledge_point(db: Session, subject: str, name: str, unit: str = "") -> KnowledgePoint:
    name = (name or "").strip()[:64]
    if not name:
        raise ValueError("知识点名为空")
    kp = (db.query(KnowledgePoint)
          .filter(KnowledgePoint.subject == subject, KnowledgePoint.name == name)
          .first())
    if not kp:
        kp = KnowledgePoint(subject=subject, name=name, unit=(unit or "").strip()[:64])
        db.add(kp)
        db.flush()
    elif unit and not kp.unit:
        kp.unit = unit[:64]
    return kp


def touch_knowledge(db: Session, user: User, subject: str, names: list[str],
                    unit: str = "", mastery: str = "weak",
                    learning_state: str = "learning", count: int = 1):
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        try:
            kp = upsert_knowledge_point(db, subject, name, unit)
        except ValueError:
            continue
        status = (db.query(UserKnowledgeStatus)
                  .filter(UserKnowledgeStatus.user_id == user.id,
                          UserKnowledgeStatus.knowledge_point_id == kp.id)
                  .first())
        if not status:
            status = UserKnowledgeStatus(user_id=user.id, knowledge_point_id=kp.id,
                                         error_count=0, mastery="unknown",
                                         learning_state="not_started")
            db.add(status)
        status.error_count = (status.error_count or 0) + count
        status.last_seen = datetime.utcnow()
        if learning_state in MINDMAP_STATE:
            if status.learning_state != "learned":
                status.learning_state = learning_state
        if mastery in MINDMAP_MASTERY:
            status.mastery = _upgrade_mastery(status.mastery, mastery)
    db.commit()


def _upgrade_mastery(current: str | None, new: str) -> str:
    current = current or "unknown"
    order = {"unknown": 0, "weak": 1, "improving": 2, "mastered": 3}
    # 新出现错题：直接标记薄弱
    if new == "weak":
        return "weak"
    return new if order.get(new, 0) > order.get(current, 0) else current


def set_learning_state(db: Session, user: User, items: list[dict]):
    """根据作业扫描结果更新学习状态。"""
    for it in items:
        name = (it.get("knowledge_point") or "").strip()
        if not name:
            continue
        kp = upsert_knowledge_point(db, it.get("subject") or "", name, it.get("unit", ""))
        if not kp.subject and it.get("subject"):
            kp.subject = it["subject"]
        status = (db.query(UserKnowledgeStatus)
                  .filter(UserKnowledgeStatus.user_id == user.id,
                          UserKnowledgeStatus.knowledge_point_id == kp.id)
                  .first())
        if not status:
            status = UserKnowledgeStatus(user_id=user.id, knowledge_point_id=kp.id,
                                         error_count=0, mastery="unknown",
                                         learning_state="not_started")
            db.add(status)
        state = it.get("learning_state", "learning")
        if state in MINDMAP_STATE and status.learning_state != "learned":
            status.learning_state = state
        status.last_seen = datetime.utcnow()
        if it.get("evidence"):
            status.note = it["evidence"][:200]
    db.commit()


def build_mindmap(db: Session, user: User, subject: str) -> dict:
    """生成思维导图节点与边：学科中心 -> 单元 -> 知识点。"""
    statuses = (db.query(UserKnowledgeStatus)
                .join(KnowledgePoint, KnowledgePoint.id == UserKnowledgeStatus.knowledge_point_id)
                .filter(UserKnowledgeStatus.user_id == user.id)
                .all())
    kp_rows = db.query(KnowledgePoint).filter(KnowledgePoint.subject == subject).all()
    kp_status = {s.knowledge_point_id: s for s in statuses}

    # 错题计数（知识点粒度）
    error_map: dict[str, int] = {}
    wqs = (db.query(WrongQuestion)
           .filter(WrongQuestion.user_id == user.id, WrongQuestion.subject == subject)
           .all())
    for w in wqs:
        for name in (w.knowledge_points or []):
            error_map[name] = error_map.get(name, 0) + 1

    units: dict[str, list] = {}
    for kp in kp_rows:
        st = kp_status.get(kp.id)
        if not st and kp.name not in error_map:
            continue
        unit = kp.unit or "未分类"
        units.setdefault(unit, []).append((kp, st))

    nodes = [{"id": "root", "label": subject, "kind": "root",
              "mastery": "unknown", "errorCount": 0, "learningState": "learned",
              "unit": "", "position": {"x": 0, "y": 0}}]
    edges = []
    unit_items = list(units.items())
    radius_u = 260
    import math
    for i, (unit, items) in enumerate(unit_items):
        angle = (2 * math.pi * i / max(len(unit_items), 1)) - math.pi / 2
        ux = radius_u * math.cos(angle)
        uy = radius_u * math.sin(angle)
        uid = f"u{i}"
        nodes.append({"id": uid, "label": unit, "kind": "unit", "mastery": "unknown",
                      "errorCount": 0, "learningState": "learning", "unit": unit,
                      "position": {"x": ux, "y": uy}})
        edges.append({"id": f"e-root-{uid}", "source": "root", "target": uid})
        n = len(items)
        for j, (kp, st) in enumerate(items):
            spread = math.pi / max(n, 1) * 0.9
            base = angle - spread / 2 + (spread * j / max(n - 1, 1) if n > 1 else spread / 2)
            r = 150 + (j % 2) * 40
            x = ux + r * math.cos(base)
            y = uy + r * math.sin(base)
            err = error_map.get(kp.name, 0)
            mastery = (st.mastery if st and st.mastery else None) or ("weak" if err else "unknown")
            nodes.append({
                "id": f"kp{kp.id}", "label": kp.name, "kind": "kp",
                "mastery": mastery,
                "errorCount": max(err, st.error_count if st and st.error_count else 0),
                "learningState": (st.learning_state if st and st.learning_state else None)
                                 or ("learning" if err else "not_started"),
                "unit": unit,
                "note": st.note if st else "",
                "position": {"x": x, "y": y},
            })
            edges.append({"id": f"e-{uid}-kp{kp.id}", "source": uid, "target": f"kp{kp.id}"})
    return {"nodes": nodes, "edges": edges}


def progress_summary(db: Session, user: User) -> dict:
    statuses = (db.query(UserKnowledgeStatus)
                .join(KnowledgePoint, KnowledgePoint.id == UserKnowledgeStatus.knowledge_point_id)
                .filter(UserKnowledgeStatus.user_id == user.id)
                .all())
    by_subject: dict[str, dict] = {}
    for s in statuses:
        subj = s.knowledge_point.subject if s.knowledge_point else "其他"
        d = by_subject.setdefault(subj, {"weak": [], "improving": [], "mastered": [], "unknown": [],
                                        "learning": 0, "learned": 0, "not_started": 0})
        d.get(s.mastery, d["unknown"]).append(s.knowledge_point.name if s.knowledge_point else "?")
        if s.learning_state in d:
            d[s.learning_state] += 1
    for subj, d in by_subject.items():
        d["total"] = len(d["weak"]) + len(d["improving"]) + len(d["mastered"]) + len(d["unknown"])
    return by_subject
