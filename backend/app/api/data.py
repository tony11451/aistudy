"""数据导出/导入：ZIP 包（manifest + data.json + images），覆盖式恢复，向后兼容。"""
import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import (AIProvider, AppSettings, Bookmark, ChangeLog, Conversation,
                      ConversationSummary, ItemTag, KnowledgeNode, LibraryBoard,
                      LibraryBook, LibraryItem, LibraryLink, LibraryPage, Message,
                      MethodCard, NightlyRun, PracticeGoal, Report, StudyProfile,
                      TeacherNote, User, WrongQuestion, ZhixueAccount, ZhixueSyncRun)
from ..security import hash_password

router = APIRouter(prefix="/api/data", tags=["data"])

FORMAT = "ai-wrong-question-backup"
VERSION = 2

PERSONAL_TABLES = [
    ("wrong_questions", WrongQuestion, "user_id"),
    ("knowledge_nodes", KnowledgeNode, "user_id"),
    ("study_profiles", StudyProfile, "user_id"),
    ("conversations", Conversation, "user_id"),
    ("messages", Message, None),  # 按会话级联
    ("practice_goals", PracticeGoal, "user_id"),
    ("method_cards", MethodCard, "user_id"),
    ("reports", Report, "user_id"),
    ("change_log", ChangeLog, "user_id"),
    # v2 新增：档案库全量 + 教研/标签/夜间/智学网（备份完整性修复）
    ("library_books", LibraryBook, "user_id"),
    ("library_pages", LibraryPage, "user_id"),
    ("library_boards", LibraryBoard, "user_id"),
    ("library_items", LibraryItem, "user_id"),
    ("library_links", LibraryLink, None),
    ("bookmarks", Bookmark, "user_id"),
    ("conversation_summaries", ConversationSummary, "user_id"),
    ("teacher_notes", TeacherNote, "user_id"),
    ("item_tags", ItemTag, "user_id"),
    ("nightly_runs", NightlyRun, "user_id"),
    ("zhixue_accounts", ZhixueAccount, "user_id"),
    ("zhixue_sync_runs", ZhixueSyncRun, "user_id"),
]


def _rows_to_list(rows, model) -> list[dict]:
    out = []
    for r in rows:
        item = {}
        for col in model.__table__.columns.keys():
            v = getattr(r, col)
            if isinstance(v, datetime):
                v = v.isoformat()
            item[col] = v
        out.append(item)
    return out


def _collect_images(user_ids: list[int]) -> dict[str, bytes]:
    images = {}
    for f in IMAGES_DIR.glob("*.jpg"):
        for uid in user_ids:
            if f.name.startswith(f"u{uid}_"):
                images[f.name] = f.read_bytes()
                break
    return images


@router.get("/export")
def export_data(scope: str = "personal", user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    is_full = scope == "full"
    if is_full and user.role != "admin":
        raise HTTPException(status_code=403, detail="整机导出需要管理员权限")

    data: dict = {}
    if is_full:
        users = db.query(User).all()
        data["users"] = _rows_to_list(users, User)
        row = db.query(AppSettings).filter(AppSettings.id == 1).first()
        data["app_settings"] = _rows_to_list([row], AppSettings) if row else []
        data["ai_providers"] = _rows_to_list(db.query(AIProvider).all(), AIProvider)
        uid_list = [u.id for u in users]
    else:
        uid_list = [user.id]

    for name, model, owner_col in PERSONAL_TABLES:
        if name == "messages":
            conv_ids = [c.id for c in db.query(Conversation).filter(
                Conversation.user_id.in_(uid_list)).all()]
            rows = db.query(Message).filter(Message.conversation_id.in_(conv_ids)).all() if conv_ids else []
        else:
            q = db.query(model)
            if owner_col:
                q = q.filter(getattr(model, owner_col).in_(uid_list))
            rows = q.all()
        data[name] = _rows_to_list(rows, model)

    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "kind": "full" if is_full else "personal",
        "created_at": datetime.utcnow().isoformat(),
        "counts": {k: len(v) for k, v in data.items()},
    }
    images = _collect_images(uid_list)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("data.json", json.dumps(data, ensure_ascii=False))
        for fname, content in images.items():
            z.writestr(f"images/{fname}", content)
    buf.seek(0)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{'full' if is_full else 'personal'}_{stamp}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename={filename}"})


def _parse_dt(v):
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return v


def _insert_rows(db: Session, model, rows: list[dict], owner_map: dict[int, int] | None = None):
    """恢复式插入：保留原 ID（保证跨表外键一致），冲突时跳过该行。"""
    for item in rows:
        kwargs = {}
        for col in model.__table__.columns.keys():
            if col not in item:
                continue  # v1 老备份缺新列 → 用列默认值
            v = item.get(col)
            if v is None:
                continue
            if col.endswith("_at") or col in ("created_at", "updated_at", "reviewed_at", "last_seen", "first_seen"):
                v = _parse_dt(v)
            kwargs[col] = v
        if owner_map and "user_id" in kwargs and kwargs["user_id"] in owner_map:
            kwargs["user_id"] = owner_map[kwargs["user_id"]]
        # SAVEPOINT 逐行保护：单行失败不影响其余导入
        try:
            with db.begin_nested():
                db.add(model(**kwargs))
                db.flush()
        except Exception:
            pass


@router.post("/import")
async def import_data(scope: str = "personal", file: UploadFile = File(...),
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    is_full = scope == "full"
    if is_full and user.role != "admin":
        raise HTTPException(status_code=403, detail="整机导入需要管理员权限")

    raw = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="不是有效的备份 ZIP")
    if "manifest.json" not in z.namelist() or "data.json" not in z.namelist():
        raise HTTPException(status_code=400, detail="备份包缺少 manifest.json / data.json")
    manifest = json.loads(z.read("manifest.json").decode("utf-8"))
    if manifest.get("format") != FORMAT:
        raise HTTPException(status_code=400, detail="备份格式不匹配")
    if int(manifest.get("version") or 0) > VERSION:
        raise HTTPException(status_code=400, detail="备份版本过新，请升级应用后再导入")
    data = json.loads(z.read("data.json").decode("utf-8"))

    # —— 覆盖式：先清空对应范围 ——
    if is_full:
        uid_list = [u.id for u in db.query(User).all()]
        conv_ids = [c.id for c in db.query(Conversation).all()]
    else:
        uid_list = [user.id]
        conv_ids = [c.id for c in db.query(Conversation).filter(
            Conversation.user_id == user.id).all()]

    if conv_ids:
        db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
    # 按外键依赖顺序删除（先子后父），避免 FK 冲突
    db.query(ConversationSummary).filter(ConversationSummary.user_id.in_(uid_list)).delete(synchronize_session=False)
    db.query(ChangeLog).filter(ChangeLog.user_id.in_(uid_list)).delete(synchronize_session=False)
    item_ids = [it.id for it in db.query(LibraryItem)
                .filter(LibraryItem.user_id.in_(uid_list)).all()]
    if item_ids:
        db.query(LibraryLink).filter(LibraryLink.item_id.in_(item_ids)).delete(synchronize_session=False)
        db.query(ItemTag).filter(ItemTag.target_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(LibraryItem).filter(LibraryItem.user_id.in_(uid_list)).delete(synchronize_session=False)
    book_ids = [b.id for b in db.query(LibraryBook)
                .filter(LibraryBook.user_id.in_(uid_list)).all()]
    if book_ids:
        db.query(LibraryPage).filter(LibraryPage.book_id.in_(book_ids)).delete(synchronize_session=False)
    db.query(LibraryBook).filter(LibraryBook.user_id.in_(uid_list)).delete(synchronize_session=False)
    db.query(LibraryBoard).filter(LibraryBoard.user_id.in_(uid_list)).delete(synchronize_session=False)
    # 知识节点自引用：先断父子关系再删
    db.query(KnowledgeNode).filter(KnowledgeNode.user_id.in_(uid_list)).update(
        {"parent_id": None}, synchronize_session=False)
    db.query(KnowledgeNode).filter(KnowledgeNode.user_id.in_(uid_list)).delete(synchronize_session=False)
    for model in (WrongQuestion, StudyProfile, Conversation, PracticeGoal,
                  MethodCard, Report, Bookmark, TeacherNote, NightlyRun,
                  ZhixueAccount, ZhixueSyncRun):
        q = db.query(model)
        if hasattr(model, "user_id"):
            q = q.filter(model.user_id.in_(uid_list))
        q.delete(synchronize_session=False)

    owner_map = None
    if is_full:
        db.query(AIProvider).delete(synchronize_session=False)
        db.query(User).delete(synchronize_session=False)
        db.flush()
    else:
        # 个人导入：备份中的 user_id 映射到当前用户
        src_users = data.get("users") or []
        owner_map = {int(u.get("id")): user.id for u in src_users} or {user.id: user.id}
        owner_map.setdefault(user.id, user.id)

    if is_full:
        _insert_rows(db, User, data.get("users") or [])
        if data.get("app_settings"):
            db.query(AppSettings).delete(synchronize_session=False)
            _insert_rows(db, AppSettings, data["app_settings"])
        _insert_rows(db, AIProvider, data.get("ai_providers") or [])

    for name, model, _ in PERSONAL_TABLES:
        _insert_rows(db, model, data.get(name) or [], owner_map)
    db.commit()

    # —— 图片 ——
    restored = 0
    for item in z.namelist():
        if not item.startswith("images/"):
            continue
        fname = item.split("/", 1)[1]
        if not fname or "/" in fname:
            continue
        target = IMAGES_DIR / fname
        target.write_bytes(z.read(item))
        restored += 1

    return {
        "ok": True,
        "kind": manifest.get("kind"),
        "version": manifest.get("version"),
        "counts": {k: len(v) for k, v in data.items()},
        "images_restored": restored,
    }
