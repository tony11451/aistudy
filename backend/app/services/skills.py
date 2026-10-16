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


def execute_skill(db: Session, user: User, ctx: dict, name: str, args: dict) -> dict:
    spec = SKILLS.get(name)
    if not spec:
        raise SkillError(f"未知技能：{name}")
    result = spec["executor"](db, user, args or {}, ctx)
    result.setdefault("summary", "完成")
    result["skill"] = name
    result["kind"] = spec["kind"]
    return result


def skills_catalog_prompt() -> str:
    lines = []
    for name, spec in SKILLS.items():
        lines.append(f"- {name}（{'读' if spec['kind'] == 'read' else '写'}）：{spec['description']}")
    return "\n".join(lines)
