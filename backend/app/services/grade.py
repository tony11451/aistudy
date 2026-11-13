"""升年级（需求 11）：学年总结 → 旧内容归档 → 新年级学科设置。"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import KnowledgeNode, LibraryItem, Report, User
from .context import get_ai_client

GRADE_SUBJECTS = {
    "初一": ["语文", "数学", "英语", "生物", "历史", "地理", "道德与法治"],
    "初二": ["语文", "数学", "英语", "物理", "生物", "历史", "地理", "道德与法治"],
    "初三": ["语文", "数学", "英语", "物理", "化学", "历史", "道德与法治"],
    "高一": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治"],
    "高二": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治"],
    "高三": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治"],
}

NEXT_GRADE = {"初一": "初二", "初二": "初三", "初三": "高一", "高一": "高二", "高二": "高三"}


def suggested_subjects(new_grade: str) -> list[str]:
    return GRADE_SUBJECTS.get(new_grade, [])


async def grade_up(db: Session, user: User, new_grade: str,
                   new_subjects: list[str] | None = None,
                   keep_weak: bool = False) -> dict:
    """
    升年级：
    1) AI 生成学年总结（入档案库 + 报告）
    2) 旧图谱节点归档（archived=True、标已学完；keep_weak=True 时薄弱节点保留跟进）
    3) 更新年级与学科列表
    """
    old_grade = user.grade or ""
    old_nodes = (db.query(KnowledgeNode)
                 .filter(KnowledgeNode.user_id == user.id, KnowledgeNode.archived.is_(False))
                 .all())
    weak_names = [n.name for n in old_nodes if n.mastery == "weak"]

    # 1) 学年总结
    summary_text = ""
    try:
        client = get_ai_client(db, user)
        node_lines = "\n".join(
            f"- [{n.subject}] {n.name}（{n.mastery}/{n.confidence}）" for n in old_nodes[:40])
        summary_text = await client.complete([
            {"role": "system", "content":
             "你是学习总结员。为学生写一份学年总结（Markdown）：## 本学年收获 / ## 仍需巩固 / "
             "## 新年级衔接建议。语气鼓励，简洁。"},
            {"role": "user", "content": f"年级：{old_grade}\n【知识点图谱】\n{node_lines or '（暂无）'}"},
        ], temperature=0.5)
        rep = Report(user_id=user.id, kind="grade_up",
                     title=f"学年总结 · {old_grade}", content=summary_text)
        db.add(rep)
        item = LibraryItem(user_id=user.id, subject="", kind="review",
                           title=f"{old_grade}学年总结", content=summary_text,
                           source="generated", ocr_status="none")
        db.add(item)
    except Exception:
        pass

    # 2) 归档旧节点
    archived = 0
    for n in old_nodes:
        if keep_weak and n.mastery == "weak":
            continue  # 薄弱节点带入新年级继续跟进
        n.archived = True
        n.learning_state = "learned"
        archived += 1

    # 3) 新年级学科
    subjects = [s for s in (new_subjects or []) if s] or suggested_subjects(new_grade)
    user.grade = new_grade
    user.subjects = subjects
    db.commit()

    return {
        "old_grade": old_grade,
        "new_grade": new_grade,
        "archived_nodes": archived,
        "kept_weak": len(weak_names) if keep_weak else 0,
        "subjects": subjects,
        "summary_saved": bool(summary_text),
    }
