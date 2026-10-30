"""Skill 系统：AI 读写应用数据的唯一通道。

- 读技能：返回数据摘要（注入对话上下文）
- 写技能：直接生效 + 记录 change_log（before/after 快照，支持撤销）
"""
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import (ChangeLog, KnowledgeNode, MethodCard,
                      PracticeGoal, StudyProfile, User, WrongQuestion)
from .knowledge import (get_or_create_node, serialize_node, progress_summary,
                        build_mindmap)


class SkillError(Exception):
    pass


# ---------- 变更记录 ----------

def record_change(db: Session, user: User, ctx: dict, *, skill: str, action: str,
                  target_type: str, target_id: int | None, description: str,
                  reason: str = "", before: dict | None = None,
                  after: dict | None = None) -> dict:
    log = ChangeLog(
        user_id=user.id,
        conversation_id=ctx.get("conversation_id"),
        skill=skill, action=action,
        target_type=target_type, target_id=target_id,
        description=description[:500], reason=reason[:500],
        before=before, after=after,
    )
    db.add(log)
    db.flush()
    return {
        "change_id": log.id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "description": description,
        "reason": reason,
    }


def _node_snapshot(db: Session, node: KnowledgeNode) -> dict:
    snap = serialize_node(node)
    parent = db.query(KnowledgeNode).filter(KnowledgeNode.id == node.parent_id).first() if node.parent_id else None
    snap["parent_name"] = parent.name if parent else ""
    return snap


# ---------- 节点操作底层 ----------

def _find_node(db: Session, user: User, args: dict) -> KnowledgeNode | None:
    if args.get("node_id"):
        return db.query(KnowledgeNode).filter(
            KnowledgeNode.id == int(args["node_id"]),
            KnowledgeNode.user_id == user.id).first()
    name = (args.get("name") or "").strip()
    subject = (args.get("subject") or "").strip()
    q = db.query(KnowledgeNode).filter(KnowledgeNode.user_id == user.id, KnowledgeNode.name == name)
    if subject:
        q = q.filter(KnowledgeNode.subject == subject)
    return q.first()


def _resolve_parent(db: Session, user: User, subject: str, parent_name: str) -> int | None:
    if not parent_name:
        return None
    parent = get_or_create_node(db, user, subject, parent_name)
    return parent.id


# ---------- 读技能 ----------

def read_mindmap(db: Session, user: User, args: dict, ctx: dict) -> dict:
    subject = args.get("subject") or ""
    if not subject:
        row = db.query(KnowledgeNode.subject).filter(
            KnowledgeNode.user_id == user.id).distinct().limit(6).all()
        subjects = [r[0] for r in row]
        out = {}
        for s in subjects:
            mp = build_mindmap(db, user, s, args.get("kind", ""))
            out[s] = [
                {"id": n["realId"], "name": n["label"], "type": n["nodeType"],
                 "mastery": n["mastery"], "confidence": n["confidence"],
                 "errorCount": n["errorCount"]}
                for n in mp["nodes"] if n["realId"]
            ]
        return {"summary": f"已读取 {sum(len(v) for v in out.values())} 个节点（{len(out)} 个学科）",
                "data": out}
    mp = build_mindmap(db, user, subject, args.get("kind", ""))
    items = [{"id": n["realId"], "name": n["label"], "type": n["nodeType"],
              "mastery": n["mastery"], "confidence": n["confidence"],
              "errorCount": n["errorCount"], "note": n["note"],
              "description": (n["description"] or "")[:120]}
             for n in mp["nodes"] if n["realId"]]
    return {"summary": f"已读取「{subject}」图谱 {len(items)} 个节点", "data": items}


def read_wrong_questions(db: Session, user: User, args: dict, ctx: dict) -> dict:
    q = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if args.get("subject"):
        q = q.filter(WrongQuestion.subject == args["subject"])
    if args.get("keyword"):
        like = f"%{args['keyword']}%"
        q = q.filter(or_(WrongQuestion.question_text.like(like),
                         WrongQuestion.wrong_reason.like(like)))
    rows = q.order_by(WrongQuestion.created_at.desc()).limit(min(int(args.get("limit") or 10), 30)).all()
    if args.get("knowledge_point"):
        rows = [w for w in rows if args["knowledge_point"] in (w.knowledge_points or [])]
    items = [{
        "id": w.id, "subject": w.subject, "knowledge_points": w.knowledge_points or [],
        "difficulty": w.difficulty, "mastery": w.mastery,
        "question": (w.question_text or "")[:150],
        "wrong_reason": (w.wrong_reason or "")[:150],
    } for w in rows]
    return {"summary": f"已读取 {len(items)} 道错题", "data": items}


def read_wrong_question(db: Session, user: User, args: dict, ctx: dict) -> dict:
    w = db.query(WrongQuestion).filter(
        WrongQuestion.id == int(args.get("id") or 0),
        WrongQuestion.user_id == user.id).first()
    if not w:
        raise SkillError("错题不存在")
    return {"summary": f"已读取错题 #{w.id}", "data": {
        "id": w.id, "subject": w.subject, "unit": w.unit,
        "knowledge_points": w.knowledge_points or [],
        "question_text": w.question_text, "wrong_reason": w.wrong_reason,
        "correct_solution": w.correct_solution, "extensions": w.extensions,
        "mastery": w.mastery,
    }}


def read_profile(db: Session, user: User, args: dict, ctx: dict) -> dict:
    q = db.query(StudyProfile).filter(StudyProfile.user_id == user.id)
    if args.get("subject"):
        q = q.filter(StudyProfile.subject == args["subject"])
    rows = q.all()
    return {"summary": f"已读取 {len(rows)} 份学习档案",
            "data": [{"subject": r.subject, "content": r.content[:800]} for r in rows]}


def read_progress(db: Session, user: User, args: dict, ctx: dict) -> dict:
    prog = progress_summary(db, user)
    return {"summary": f"已读取进度（{len(prog)} 个学科）", "data": prog}


def read_goals(db: Session, user: User, args: dict, ctx: dict) -> dict:
    q = db.query(PracticeGoal).filter(PracticeGoal.user_id == user.id)
    if args.get("status"):
        q = q.filter(PracticeGoal.status == args["status"])
    rows = q.order_by(PracticeGoal.created_at.desc()).limit(20).all()
    return {"summary": f"已读取 {len(rows)} 个刷题目标",
            "data": [{"id": g.id, "subject": g.subject, "title": g.title,
                      "question_type": g.question_type, "status": g.status,
                      "description": g.description[:150]} for g in rows]}


def read_methods(db: Session, user: User, args: dict, ctx: dict) -> dict:
    q = db.query(MethodCard).filter(MethodCard.user_id == user.id)
    if args.get("subject"):
        q = q.filter(MethodCard.subject == args["subject"])
    rows = q.order_by(MethodCard.created_at.desc()).limit(15).all()
    return {"summary": f"已读取 {len(rows)} 条答题方法",
            "data": [{"id": m.id, "subject": m.subject,
                      "knowledge_point": m.knowledge_point,
                      "specific_method": m.specific_method[:200],
                      "general_method": m.general_method[:200]} for m in rows]}


def read_change_log(db: Session, user: User, args: dict, ctx: dict) -> dict:
    rows = (db.query(ChangeLog).filter(ChangeLog.user_id == user.id)
            .order_by(ChangeLog.created_at.desc())
            .limit(min(int(args.get("limit") or 10), 30)).all())
    return {"summary": f"已读取 {len(rows)} 条变更记录",
            "data": [{"id": c.id, "action": c.action, "target_type": c.target_type,
                      "description": c.description, "reason": c.reason,
                      "undone": c.undone,
                      "created_at": c.created_at.isoformat() if c.created_at else None}
                     for c in rows]}


# ---------- 写技能 ----------

def create_node(db: Session, user: User, args: dict, ctx: dict) -> dict:
    subject = (args.get("subject") or "").strip()
    name = (args.get("name") or "").strip()
    if not subject or not name:
        raise SkillError("缺少 subject 或 name")
    existing = _find_node(db, user, {"name": name, "subject": subject})
    if existing:
        raise SkillError(f"节点「{name}」已存在（id={existing.id}），如需修改请调用 update_node")
    parent_id = _resolve_parent(db, user, subject, (args.get("parent_name") or "").strip())
    node_type = args.get("node_type") if args.get("node_type") in ("knowledge", "weakness") else "knowledge"
    node = get_or_create_node(db, user, subject, name, parent_id, node_type, source="ai")
    if args.get("description"):
        node.description = str(args["description"])[:2000]
    if args.get("confidence") in ("suspected", "confirmed"):
        node.confidence = args["confidence"]
    if node_type == "weakness":
        node.mastery = "weak"
    db.commit()
    db.refresh(node)
    change = record_change(
        db, user, ctx, skill="create_node", action="create",
        target_type="node", target_id=node.id,
        description=f"新建{'弱点' if node_type == 'weakness' else '知识点'}「{subject}/{name}」",
        reason=str(args.get("reason") or ""), before=None,
        after=_node_snapshot(db, node))
    db.commit()
    return {"summary": f"已创建节点「{name}」", "data": serialize_node(node), "changes": [change]}


def update_node(db: Session, user: User, args: dict, ctx: dict) -> dict:
    node = _find_node(db, user, args)
    if not node:
        raise SkillError("节点不存在")
    before = _node_snapshot(db, node)
    changed = []
    if args.get("name") and args["name"] != node.name:
        changed.append(f"名称 {node.name}→{args['name']}")
        node.name = str(args["name"]).strip()[:64]
    if "description" in args:
        node.description = str(args.get("description") or "")[:2000]
        changed.append("更新说明")
    if args.get("mastery") in ("unknown", "weak", "improving", "mastered"):
        if args["mastery"] != node.mastery:
            changed.append(f"掌握度 {node.mastery}→{args['mastery']}")
        node.mastery = args["mastery"]
    if args.get("confidence") in ("suspected", "confirmed"):
        if args["confidence"] != node.confidence:
            changed.append(f"置信度 {node.confidence}→{args['confidence']}")
        node.confidence = args["confidence"]
    if args.get("node_type") in ("knowledge", "weakness") and args["node_type"] != node.node_type:
        changed.append(f"类型 {node.node_type}→{args['node_type']}")
        node.node_type = args["node_type"]
    if args.get("learning_state") in ("not_started", "learning", "learned"):
        node.learning_state = args["learning_state"]
    if "note" in args:
        node.note = str(args.get("note") or "")[:1000]
    node.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(node)
    desc = f"更新「{node.name}」" + ("：" + "，".join(changed) if changed else "")
    change = record_change(
        db, user, ctx, skill="update_node", action="update",
        target_type="node", target_id=node.id,
        description=desc, reason=str(args.get("reason") or ""),
        before=before, after=_node_snapshot(db, node))
    db.commit()
    return {"summary": desc, "data": serialize_node(node), "changes": [change]}


def delete_node(db: Session, user: User, args: dict, ctx: dict) -> dict:
    node = _find_node(db, user, args)
    if not node:
        raise SkillError("节点不存在")
    before = _node_snapshot(db, node)
    names = [node.name]

    def cascade(rid: int):
        kids = db.query(KnowledgeNode).filter(KnowledgeNode.parent_id == rid).all()
        for k in kids:
            names.append(k.name)
            cascade(k.id)
        db.query(KnowledgeNode).filter(KnowledgeNode.id == rid).delete(synchronize_session=False)

    target_id = node.id
    subject = node.subject
    cascade(target_id)
    db.commit()
    change = record_change(
        db, user, ctx, skill="delete_node", action="delete",
        target_type="node", target_id=target_id,
        description=f"删除节点「{'、'.join(names)}」",
        reason=str(args.get("reason") or ""), before=before, after=None)
    db.commit()
    return {"summary": f"已删除节点「{'、'.join(names)}」", "changes": [change]}


def reorganize_weaknesses(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """整理/精简弱点：批量 rename / merge / delete / demote / promote。"""
    ops = args.get("operations") or []
    if not ops:
        raise SkillError("缺少 operations")
    results = []
    changes = []
    for op in ops[:12]:
        kind = op.get("op")
        node = _find_node(db, user, op)
        if not node:
            results.append(f"跳过（未找到）：{op.get('name') or op.get('node_id')}")
            continue
        if kind == "rename" and op.get("new_name"):
            args2 = {**op, "name": node.name, "reason": op.get("reason", "整理精简")}
            args2["name"] = op["new_name"]
            r = update_node(db, user, args2, ctx)
            changes.extend(r.get("changes") or [])
            results.append(f"改名：{op['new_name']}")
        elif kind == "merge" and op.get("into"):
            target = _find_node(db, user, {"name": op["into"], "subject": node.subject})
            if not target:
                results.append(f"跳过（合并目标不存在）：{op['into']}")
                continue
            before = _node_snapshot(db, node)
            # 错题数并入目标，删除源节点
            target.error_count = (target.error_count or 0) + (node.error_count or 0)
            if node.mastery == "weak":
                target.mastery = "weak"
            db.query(KnowledgeNode).filter(KnowledgeNode.id == node.id).delete(synchronize_session=False)
            db.commit()
            changes.append(record_change(
                db, user, ctx, skill="reorganize_weaknesses", action="delete",
                target_type="node", target_id=node.id,
                description=f"合并「{node.name}」→「{target.name}」",
                reason=str(op.get("reason") or "整理精简"), before=before, after=None))
            db.commit()
            results.append(f"合并：{node.name}→{target.name}")
        elif kind == "delete":
            r = delete_node(db, user, {"node_id": node.id, "reason": op.get("reason", "整理精简")}, ctx)
            changes.extend(r.get("changes") or [])
            results.append(f"删除：{node.name}")
        elif kind in ("demote", "promote"):
            # demote: 确认弱点→疑似；promote: 疑似→已确认
            r = update_node(db, user, {
                "node_id": node.id,
                "confidence": "suspected" if kind == "demote" else "confirmed",
                "reason": op.get("reason", "整理精简"),
            }, ctx)
            changes.extend(r.get("changes") or [])
            results.append(f"{'降级为疑似' if kind == 'demote' else '升级为已确认'}：{node.name}")
        elif kind == "weaken":
            r = update_node(db, user, {"node_id": node.id, "mastery": "weak",
                                       "reason": op.get("reason", "整理精简")}, ctx)
            changes.extend(r.get("changes") or [])
            results.append(f"标记薄弱：{node.name}")
        else:
            results.append(f"未知操作：{kind}")
    return {"summary": "整理完成：" + "；".join(results)[:300], "changes": changes}


def re_evaluate(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """按历史错题重新评估节点：错题数→置信度，学习状态→掌握度建议。"""
    q = db.query(KnowledgeNode).filter(KnowledgeNode.user_id == user.id)
    if args.get("subject"):
        q = q.filter(KnowledgeNode.subject == args["subject"])
    if args.get("names"):
        q = q.filter(KnowledgeNode.name.in_(list(args["names"])[:20]))
    nodes = q.all()
    if not nodes:
        raise SkillError("没有可评估的节点")
    wq_rows = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id).all()
    error_map: dict[str, int] = {}
    for w in wq_rows:
        for name in (w.knowledge_points or []):
            error_map[name] = error_map.get(name, 0) + 1
    changes = []
    evaluated = 0
    for node in nodes[:20]:
        if node.node_type != "weakness" and node.mastery == "mastered":
            continue
        err = error_map.get(node.name, 0)
        before = _node_snapshot(db, node)
        touched = False
        new_conf = "confirmed" if err >= 2 else "suspected"
        if node.confidence != new_conf:
            node.confidence = new_conf
            touched = True
        if err == 0 and node.mastery == "weak":
            node.mastery = "improving"
            touched = True
        elif err >= 2 and node.mastery in ("unknown", "improving"):
            node.mastery = "weak"
            touched = True
        if err:
            node.error_count = max(node.error_count or 0, err)
            touched = True
        if touched:
            node.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(node)
            changes.append(record_change(
                db, user, ctx, skill="re_evaluate", action="update",
                target_type="node", target_id=node.id,
                description=f"重新评估「{node.name}」：错题 {err} 道 → 置信度 {new_conf}、掌握度 {node.mastery}",
                reason=str(args.get("reason") or "根据历史错题重新评估"),
                before=before, after=_node_snapshot(db, node)))
            db.commit()
            evaluated += 1
    return {"summary": f"重新评估完成：{evaluated} 个节点有更新",
            "data": {"evaluated": evaluated}, "changes": changes}


def update_profile(db: Session, user: User, args: dict, ctx: dict) -> dict:
    subject = (args.get("subject") or "").strip()
    content = str(args.get("content") or "")
    if not subject:
        raise SkillError("缺少 subject")
    row = db.query(StudyProfile).filter(
        StudyProfile.user_id == user.id, StudyProfile.subject == subject).first()
    before = {"subject": subject, "content": row.content if row else ""}
    if not row:
        row = StudyProfile(user_id=user.id, subject=subject)
        db.add(row)
    row.content = content[:8000]
    row.updated_at = datetime.utcnow()
    db.commit()
    change = record_change(
        db, user, ctx, skill="update_profile", action="update" if before["content"] else "create",
        target_type="profile", target_id=row.id,
        description=f"更新学习档案《{subject}》",
        reason=str(args.get("reason") or ""), before=before,
        after={"subject": subject, "content": row.content})
    db.commit()
    return {"summary": f"已更新「{subject}」学习档案", "changes": [change]}


def create_goal(db: Session, user: User, args: dict, ctx: dict) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        raise SkillError("缺少 title")
    g = PracticeGoal(
        user_id=user.id, subject=args.get("subject") or "",
        title=title[:128], question_type=str(args.get("question_type") or "")[:64],
        description=str(args.get("description") or "")[:2000],
        reason=str(args.get("reason") or "")[:1000],
        due_date=str(args.get("due_date") or "")[:32])
    db.add(g)
    db.commit()
    db.refresh(g)
    change = record_change(
        db, user, ctx, skill="create_goal", action="create",
        target_type="goal", target_id=g.id,
        description=f"新建刷题目标「{g.title}」", reason=g.reason,
        before=None,
        after={"id": g.id, "subject": g.subject, "title": g.title,
               "description": g.description, "status": g.status})
    db.commit()
    return {"summary": f"已创建刷题目标「{g.title}」", "changes": [change]}


def complete_goal(db: Session, user: User, args: dict, ctx: dict) -> dict:
    g = db.query(PracticeGoal).filter(
        PracticeGoal.id == int(args.get("id") or 0),
        PracticeGoal.user_id == user.id).first()
    if not g:
        raise SkillError("目标不存在")
    before = {"id": g.id, "status": g.status}
    g.status = "done"
    db.commit()
    change = record_change(
        db, user, ctx, skill="complete_goal", action="update",
        target_type="goal", target_id=g.id,
        description=f"完成刷题目标「{g.title}」", reason=str(args.get("reason") or ""),
        before=before, after={"id": g.id, "status": "done"})
    db.commit()
    return {"summary": f"目标「{g.title}」已标记完成", "changes": [change]}


def save_method(db: Session, user: User, args: dict, ctx: dict) -> dict:
    if not (args.get("specific_method") or args.get("general_method")):
        raise SkillError("缺少方法内容")
    m = MethodCard(
        user_id=user.id, subject=args.get("subject") or "",
        knowledge_point=str(args.get("knowledge_point") or "")[:64],
        question_type=str(args.get("question_type") or "")[:64],
        specific_method=str(args.get("specific_method") or ""),
        general_method=str(args.get("general_method") or ""))
    db.add(m)
    db.commit()
    db.refresh(m)
    change = record_change(
        db, user, ctx, skill="save_method", action="create",
        target_type="method", target_id=m.id,
        description=f"保存答题方法「{m.knowledge_point or m.question_type or '方法'}」",
        reason=str(args.get("reason") or ""), before=None,
        after={"id": m.id, "subject": m.subject, "knowledge_point": m.knowledge_point,
               "specific_method": m.specific_method, "general_method": m.general_method})
    db.commit()
    return {"summary": "答题方法已保存", "changes": [change]}


# ---------- 注册表 ----------

SKILLS: dict[str, dict] = {
    "read_mindmap": {
        "kind": "read",
        "description": "读取知识图谱（思维导图）节点。参数：subject(可选,如\"数学\")、kind(可选:knowledge|weakness)",
        "executor": read_mindmap,
    },
    "read_wrong_questions": {
        "kind": "read",
        "description": "搜索历史错题。参数：subject、keyword、knowledge_point、limit(默认10)",
        "executor": read_wrong_questions,
    },
    "read_wrong_question": {
        "kind": "read",
        "description": "读取某道错题完整分析。参数：id",
        "executor": read_wrong_question,
    },
    "read_profile": {
        "kind": "read",
        "description": "读取学习档案。参数：subject(可选)",
        "executor": read_profile,
    },
    "read_progress": {
        "kind": "read",
        "description": "读取各学科学习进度与掌握度统计。无参数",
        "executor": read_progress,
    },
    "read_goals": {
        "kind": "read",
        "description": "读取刷题目标。参数：status(active|done|archived,可选)",
        "executor": read_goals,
    },
    "read_methods": {
        "kind": "read",
        "description": "读取答题方法库。参数：subject(可选)",
        "executor": read_methods,
    },
    "read_change_log": {
        "kind": "read",
        "description": "读取最近的变更记录（你做过哪些修改）。参数：limit(默认10)",
        "executor": read_change_log,
    },
    "create_node": {
        "kind": "write",
        "description": "新建知识点/弱点节点。参数：subject、name、node_type(knowledge|weakness)、parent_name(可选)、description(可选)、confidence(suspected|confirmed,可选)、reason(可选)",
        "executor": create_node,
    },
    "update_node": {
        "kind": "write",
        "description": "修改节点。参数：node_id 或 (subject+name) 定位；可改 name、description、mastery(unknown|weak|improving|mastered)、confidence、node_type、learning_state、note、reason",
        "executor": update_node,
    },
    "delete_node": {
        "kind": "write",
        "description": "删除节点（含其子节点）。参数：node_id 或 (subject+name)、reason(可选)",
        "executor": delete_node,
    },
    "reorganize_weaknesses": {
        "kind": "write",
        "description": "批量整理/精简弱点。参数：operations 数组，每项 {op: rename|merge|delete|demote|promote|weaken, subject, name 或 node_id, new_name(仅rename), into(仅merge,目标名), reason}",
        "executor": reorganize_weaknesses,
    },
    "re_evaluate": {
        "kind": "write",
        "description": "根据历史错题重新评估节点的置信度/掌握度。参数：subject(可选)、names(可选,节点名数组)、reason(可选)",
        "executor": re_evaluate,
    },
    "update_profile": {
        "kind": "write",
        "description": "更新某学科的学习档案全文（弱点画像）。参数：subject、content(Markdown 全文,不含原题)、reason(可选)",
        "executor": update_profile,
    },
    "create_goal": {
        "kind": "write",
        "description": "新建刷题目标。参数：subject、title、question_type、description、reason、due_date(可选)",
        "executor": create_goal,
    },
    "complete_goal": {
        "kind": "write",
        "description": "把刷题目标标记为完成。参数：id、reason(可选)",
        "executor": complete_goal,
    },
    "save_method": {
        "kind": "write",
        "description": "保存答题方法卡。参数：subject、knowledge_point、question_type、specific_method、general_method、reason(可选)",
        "executor": save_method,
    },
}


async def execute_skill(db: Session, user: User, ctx: dict, name: str, args: dict) -> dict:
    spec = SKILLS.get(name)
    if not spec:
        raise SkillError(f"未知技能：{name}")
    result = spec["executor"](db, user, args or {}, ctx)
    if hasattr(result, "__await__"):
        result = await result
    result.setdefault("summary", "完成")
    result["skill"] = name
    result["kind"] = spec["kind"]
    return result


def skills_catalog_prompt() -> str:
    lines = []
    for name, spec in SKILLS.items():
        lines.append(f"- {name}（{'读' if spec['kind'] == 'read' else '写'}）：{spec['description']}")
    return "\n".join(lines)


# ===================== 档案库技能（v5） =====================

def search_library(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """基础搜索档案库（标题/正文/OCR 文字）。参数：q、subject、kind(image|text|attachment|review|wrong_question)、source、limit"""
    from ..models import LibraryItem
    q = db.query(LibraryItem).filter(LibraryItem.user_id == user.id)
    kw = (args.get("q") or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(LibraryItem.title.like(like), LibraryItem.content.like(like),
                         LibraryItem.ocr_text.like(like), LibraryItem.file_name.like(like)))
    if args.get("subject"):
        q = q.filter(LibraryItem.subject == args["subject"])
    if args.get("kind"):
        q = q.filter(LibraryItem.kind == args["kind"])
    if args.get("source"):
        q = q.filter(LibraryItem.source == args["source"])
    rows = q.order_by(LibraryItem.created_at.desc()).limit(min(int(args.get("limit") or 10), 30)).all()
    items = [{"id": r.id, "subject": r.subject, "kind": r.kind, "title": r.title,
              "page_no": r.page_no, "ocr_preview": (r.ocr_text or "")[:150],
              "content_preview": (r.content or "")[:150]} for r in rows]
    return {"summary": f"档案库搜索到 {len(items)} 条", "data": items}


def read_library_item(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """读取档案库某条目的完整文字内容（含 OCR/正文）。参数：id"""
    from ..models import LibraryItem
    it = db.query(LibraryItem).filter(LibraryItem.id == int(args.get("id") or 0),
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise SkillError("条目不存在")
    return {"summary": f"已读取「{it.title}」", "data": {
        "id": it.id, "subject": it.subject, "kind": it.kind, "title": it.title,
        "content": (it.content or "")[:3000], "ocr_text": (it.ocr_text or "")[:3000],
        "page_no": it.page_no, "file_type": it.file_type}}


def read_attachment(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """读取附件的文字内容（答案解析等文档已提取文字）。参数：id"""
    from ..models import LibraryItem
    it = db.query(LibraryItem).filter(LibraryItem.id == int(args.get("id") or 0),
                                      LibraryItem.user_id == user.id,
                                      LibraryItem.kind == "attachment").first()
    if not it:
        raise SkillError("附件不存在")
    text = it.content or it.ocr_text or "（该附件未能提取出文字）"
    return {"summary": f"已读取附件「{it.title}」", "data": {
        "id": it.id, "title": it.title, "text": text[:4000], "file_type": it.file_type}}


def read_book_page(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """按页读取课本/笔记本的一页（OCR 文字）。参数：book_id、page_no（或 page_id）"""
    from ..models import LibraryBook, LibraryPage
    if args.get("page_id"):
        pg = db.query(LibraryPage).filter(LibraryPage.id == int(args["page_id"]),
                                          LibraryPage.user_id == user.id).first()
    else:
        pg = db.query(LibraryPage).filter(
            LibraryPage.book_id == int(args.get("book_id") or 0),
            LibraryPage.user_id == user.id,
            LibraryPage.page_no == int(args.get("page_no") or 0)).first()
    if not pg:
        raise SkillError("页面不存在")
    book = db.query(LibraryBook).filter(LibraryBook.id == pg.book_id).first()
    return {"summary": f"已读取《{book.name if book else '?'}》第 {pg.page_no} 页",
            "data": {"book": book.name if book else "", "page_no": pg.page_no,
                     "ocr_text": (pg.ocr_text or "")[:4000]}}


def library_books_overview(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """查看档案库结构：书本列表与板块列表。参数：subject(可选)"""
    from ..models import LibraryBoard, LibraryBook
    q = db.query(LibraryBook).filter(LibraryBook.user_id == user.id)
    if args.get("subject"):
        q = q.filter(LibraryBook.subject == args["subject"])
    books = q.order_by(LibraryBook.created_at.desc()).limit(30).all()
    bq = db.query(LibraryBoard).filter(LibraryBoard.user_id == user.id)
    if args.get("subject"):
        bq = bq.filter(LibraryBoard.subject == args["subject"])
    boards = bq.order_by(LibraryBoard.sort_order, LibraryBoard.id).limit(50).all()
    return {"summary": f"书本 {len(books)} 本、板块 {len(boards)} 个", "data": {
        "books": [{"id": b.id, "subject": b.subject, "kind": b.kind, "name": b.name} for b in books],
        "boards": [{"id": b.id, "subject": b.subject, "parent_id": b.parent_id, "name": b.name}
                   for b in boards]}}


def create_board(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """新建档案库板块。参数：subject、name、parent_id(可选)、reason(可选)"""
    from ..models import LibraryBoard
    name = (args.get("name") or "").strip()
    if not name:
        raise SkillError("缺少板块名")
    b = LibraryBoard(user_id=user.id, subject=args.get("subject") or "",
                     parent_id=int(args["parent_id"]) if args.get("parent_id") else None,
                     name=name[:128])
    db.add(b)
    db.commit()
    db.refresh(b)
    change = record_change(db, user, ctx, skill="create_board", action="create",
                           target_type="library", target_id=b.id,
                           description=f"新建板块「{name}」",
                           reason=str(args.get("reason") or ""), before=None,
                           after={"id": b.id, "name": name})
    db.commit()
    return {"summary": f"已新建板块「{name}」", "changes": [change]}


def update_library_item(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """修改档案库条目（改名/改说明/换板块）。参数：id、title、content、board_id(可选,0=移出板块)、reason"""
    from ..models import LibraryItem
    it = db.query(LibraryItem).filter(LibraryItem.id == int(args.get("id") or 0),
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise SkillError("条目不存在")
    before = {"id": it.id, "title": it.title, "board_id": it.board_id, "content": (it.content or "")[:200]}
    if args.get("title"):
        it.title = str(args["title"])[:256]
    if "content" in args:
        it.content = str(args.get("content") or "")[:20000]
    if "board_id" in args:
        it.board_id = int(args["board_id"]) if args.get("board_id") else None
    db.commit()
    db.refresh(it)
    change = record_change(db, user, ctx, skill="update_library_item", action="update",
                           target_type="library", target_id=it.id,
                           description=f"修改资料「{it.title}」",
                           reason=str(args.get("reason") or ""),
                           before=before,
                           after={"id": it.id, "title": it.title, "board_id": it.board_id})
    db.commit()
    return {"summary": f"已修改资料「{it.title}」", "changes": [change]}


def delete_library_item(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """删除档案库条目。参数：id、reason"""
    from ..models import LibraryItem, LibraryLink
    it = db.query(LibraryItem).filter(LibraryItem.id == int(args.get("id") or 0),
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise SkillError("条目不存在")
    before = {"id": it.id, "title": it.title, "subject": it.subject, "kind": it.kind,
              "content": (it.content or "")[:200], "board_id": it.board_id}
    db.query(LibraryLink).filter(LibraryLink.item_id == it.id).delete(synchronize_session=False)
    db.delete(it)
    db.commit()
    change = record_change(db, user, ctx, skill="delete_library_item", action="delete",
                           target_type="library", target_id=before["id"],
                           description=f"删除资料「{before['title']}」",
                           reason=str(args.get("reason") or ""), before=before, after=None)
    db.commit()
    return {"summary": f"已删除资料「{before['title']}」", "changes": [change]}


def move_library_item(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """把资料移动/归入某板块或书本。参数：id、board_id 或 book_id、page_no(可选)、reason"""
    from ..models import LibraryItem
    it = db.query(LibraryItem).filter(LibraryItem.id == int(args.get("id") or 0),
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise SkillError("条目不存在")
    before = {"id": it.id, "board_id": it.board_id, "book_id": it.book_id, "page_no": it.page_no}
    if "board_id" in args:
        it.board_id = int(args["board_id"]) if args.get("board_id") else None
    if "book_id" in args:
        it.book_id = int(args["book_id"]) if args.get("book_id") else None
    if "page_no" in args:
        it.page_no = int(args["page_no"]) if args.get("page_no") else None
    db.commit()
    change = record_change(db, user, ctx, skill="move_library_item", action="update",
                           target_type="library", target_id=it.id,
                           description=f"移动资料「{it.title}」到新位置",
                           reason=str(args.get("reason") or ""),
                           before=before,
                           after={"board_id": it.board_id, "book_id": it.book_id, "page_no": it.page_no})
    db.commit()
    return {"summary": f"已移动「{it.title}」", "changes": [change]}


# ===================== 对话历史/摘要技能（v5） =====================

def read_conversations(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """查看历史对话列表（标题/学科/时间）。参数：limit"""
    from ..models import Conversation
    rows = (db.query(Conversation).filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(min(int(args.get("limit") or 10), 30)).all())
    return {"summary": f"已读取 {len(rows)} 个历史对话",
            "data": [{"id": c.id, "title": c.title, "subject": c.subject,
                      "updated_at": c.updated_at.isoformat() if c.updated_at else None}
                     for c in rows]}


def read_conversation_content(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """读取某个历史对话的消息内容（可用来回顾当时讨论）。参数：conversation_id、limit"""
    from ..models import Conversation, Message
    cid = int(args.get("conversation_id") or 0)
    conv = db.query(Conversation).filter(Conversation.id == cid,
                                         Conversation.user_id == user.id).first()
    if not conv:
        raise SkillError("对话不存在")
    msgs = (db.query(Message).filter(Message.conversation_id == cid)
            .order_by(Message.id.desc())
            .limit(min(int(args.get("limit") or 20), 40)).all())[::-1]
    return {"summary": f"已读取对话「{conv.title}」{len(msgs)} 条消息",
            "data": [{"role": m.role, "content": (m.content or "")[:300]} for m in msgs]}


async def summarize_conversation_skill(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """用独立 AI 请求总结某个历史对话（结果存为对话摘要，默认不进入当前对话）。参数：conversation_id、focus(可选)"""
    from ..models import Conversation, ConversationSummary, Message
    from .context import get_ai_client
    cid = int(args.get("conversation_id") or 0)
    conv = db.query(Conversation).filter(Conversation.id == cid,
                                         Conversation.user_id == user.id).first()
    if not conv:
        raise SkillError("对话不存在")
    msgs = (db.query(Message).filter(Message.conversation_id == cid)
            .order_by(Message.id).all())
    dialogue = "\n".join(f"{'学生' if m.role == 'user' else '导师'}：{(m.content or '')[:300]}"
                         for m in msgs)[-5000:]
    client = get_ai_client(db, user)
    focus = str(args.get("focus") or "重点总结：讨论过的知识点、学生的疑问点、达成的结论、后续行动。")
    text = await client.complete([
        {"role": "system", "content": "你是学习记录整理员。请用简洁的中文条目总结一段学习对话，不复述寒暄。"},
        {"role": "user", "content": f"{focus}\n\n【对话记录】\n{dialogue}"},
    ], temperature=0.3)
    s = ConversationSummary(user_id=user.id, conversation_id=cid, content=text)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"summary": f"已生成对话摘要（{conv.title}）",
            "data": {"summary_id": s.id, "content": text[:600]}}


def read_conversation_summaries(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """读取历史对话的摘要记录。参数：conversation_id(可选)、limit"""
    from ..models import ConversationSummary
    q = db.query(ConversationSummary).filter(ConversationSummary.user_id == user.id)
    if args.get("conversation_id"):
        q = q.filter(ConversationSummary.conversation_id == int(args["conversation_id"]))
    rows = q.order_by(ConversationSummary.created_at.desc()).limit(
        min(int(args.get("limit") or 5), 20)).all()
    return {"summary": f"已读取 {len(rows)} 条对话摘要",
            "data": [{"id": s.id, "conversation_id": s.conversation_id,
                      "content": (s.content or "")[:400]} for s in rows]}


# ===================== 复习资料（v5） =====================

async def generate_review_material(db: Session, user: User, args: dict, ctx: dict) -> dict:
    """针对弱点/时间段生成复习资料并存入档案库（可下载）。参数：subject(可选)、title、days(默认14)、focus(可选)"""
    from ..models import LibraryItem, WrongQuestion
    from .context import get_ai_client
    subject = args.get("subject") or ""
    days = min(int(args.get("days") or 14), 60)
    q = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if subject:
        q = q.filter(WrongQuestion.subject == subject)
    from datetime import datetime, timedelta
    rows = q.filter(WrongQuestion.created_at >= datetime.utcnow() - timedelta(days=days)) \
        .order_by(WrongQuestion.created_at.desc()).limit(30).all()
    material = "\n".join(
        f"- [{w.subject}] {w.knowledge_points}：{(w.question_text or '')[:80]}｜错因：{(w.wrong_reason or '')[:80]}"
        for w in rows)
    nodes = progress_summary(db, user)
    weaknesses = "\n".join(
        f"- {s}/{d.get('weak', [])}" for s, d in nodes.items() if d.get("weak"))
    client = get_ai_client(db, user)
    focus = str(args.get("focus") or "期中复习")
    text = await client.complete([
        {"role": "system", "content": f"{PERSONA_BASE_FOR_REVIEW}"},
        {"role": "user", "content": "请为学生生成一份复习资料（" + focus + "）。\n【薄弱点】\n" + weaknesses + "\n【近 " + str(days) + " 天错题】\n" + (material or "（无）")},
    ], temperature=0.5)
    title = str(args.get("title") or f"复习资料 · {datetime.utcnow().strftime('%m-%d')}")
    item = LibraryItem(user_id=user.id, subject=subject, kind="review",
                       title=title[:256], content=text, source="generated",
                       ocr_status="none")
    db.add(item)
    db.commit()
    db.refresh(item)
    change = record_change(db, user, ctx, skill="generate_review_material", action="create",
                           target_type="library", target_id=item.id,
                           description=f"生成复习资料「{title}」",
                           reason=str(args.get("reason") or focus), before=None,
                           after={"id": item.id, "title": title})
    db.commit()
    return {"summary": f"复习资料「{title}」已生成并存入档案库", "data": {"id": item.id},
            "changes": [change]}


PERSONA_BASE_FOR_REVIEW = (
    "你是资深备考教练。输出 Markdown 复习资料：## 知识清单 / ## 高频错点 / ## 例题精讲 / ## 自测清单 等板块"
    "（板块可自行调整），公式用 LaTeX（$...$/$$...$$），语气鼓励、结论先行。")

SKILLS.update({
    "search_library": {"kind": "read",
        "description": "基础搜索档案库（错题图片/笔记/附件/复习资料的文字索引）。参数：q、subject、kind(image|text|attachment|review|wrong_question)、source、limit",
        "executor": search_library},
    "read_library_item": {"kind": "read",
        "description": "读取档案库条目完整文字。参数：id",
        "executor": read_library_item},
    "read_attachment": {"kind": "read",
        "description": "读取附件文字内容（答案解析等）。参数：id",
        "executor": read_attachment},
    "read_book_page": {"kind": "read",
        "description": "按页读课本/笔记本（电子书页码）。参数：book_id+page_no 或 page_id",
        "executor": read_book_page},
    "library_books_overview": {"kind": "read",
        "description": "查看档案库的书本与板块结构。参数：subject(可选)",
        "executor": library_books_overview},
    "create_board": {"kind": "write",
        "description": "新建档案库板块。参数：subject、name、parent_id(可选)、reason",
        "executor": create_board},
    "update_library_item": {"kind": "write",
        "description": "修改档案库条目。参数：id、title、content、board_id、reason",
        "executor": update_library_item},
    "delete_library_item": {"kind": "write",
        "description": "删除档案库条目。参数：id、reason",
        "executor": delete_library_item},
    "move_library_item": {"kind": "write",
        "description": "移动资料到板块/书本。参数：id、board_id、book_id、page_no、reason",
        "executor": move_library_item},
    "read_conversations": {"kind": "read",
        "description": "查看历史对话列表。参数：limit",
        "executor": read_conversations},
    "read_conversation_content": {"kind": "read",
        "description": "读取某个历史对话的消息内容。参数：conversation_id、limit",
        "executor": read_conversation_content},
    "summarize_conversation": {"kind": "write",
        "description": "用独立 AI 请求总结某历史对话并保存为摘要（不会出现在当前对话里）。参数：conversation_id、focus(可选)",
        "executor": summarize_conversation_skill},
    "read_conversation_summaries": {"kind": "read",
        "description": "读取历史对话摘要。参数：conversation_id(可选)、limit",
        "executor": read_conversation_summaries},
    "generate_review_material": {"kind": "write",
        "description": "针对弱点/近 N 天错题生成复习资料并存入档案库。参数：subject(可选)、title、days(默认14)、focus(可选)",
        "executor": generate_review_material},
})
