"""处理队列流水线：去重 → 日期识别 → 归类/打标 → OCR。

- 重复图片（SHA-256 命中）自动替换原条目并重跑索引/文字
- 日期：优先图片 EXIF/图上识别，回退上传日期
- 双模式：fast_ocr（仅文字）/ ai_smart（提取+归类+打标签）
- zip / tar.gz 压缩包解压后内容自动入队
"""
import hashlib
import io
import tarfile
import zipfile
from datetime import datetime

from PIL import Image, ExifTags
from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..models import ItemTag, LibraryItem, ProcessingQueue, User

TAG_TYPES = ["date", "term", "subject", "source", "chapter", "knowledge",
             "qtype", "difficulty", "importance", "content_type", "page", "custom"]


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_tags(db: Session, user: User, target_type: str, target_id: int,
             tags: dict[str, str]) -> None:
    for t, v in (tags or {}).items():
        if t not in TAG_TYPES or not v:
            continue
        exists = (db.query(ItemTag)
                  .filter(ItemTag.user_id == user.id, ItemTag.target_type == target_type,
                          ItemTag.target_id == target_id, ItemTag.tag_type == t,
                          ItemTag.tag_value == str(v)[:128])
                  .first())
        if not exists:
            db.add(ItemTag(user_id=user.id, target_type=target_type,
                           target_id=target_id, tag_type=t, tag_value=str(v)[:128]))


def exif_date(path) -> str:
    """从图片 EXIF 提取拍摄日期；失败返回空。"""
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
        for tag_id, v in exif.items():
            if ExifTags.TAGS.get(tag_id) == "DateTimeOriginal" and isinstance(v, str):
                m = v.replace(":", "-", 2)[:10]
                if len(m) == 10:
                    return m
    except Exception:
        pass
    return ""


def find_duplicate(db: Session, user: User, fhash: str, exclude_id: int = 0) -> LibraryItem | None:
    if not fhash:
        return None
    return (db.query(LibraryItem)
            .filter(LibraryItem.user_id == user.id, LibraryItem.file_hash == fhash,
                    LibraryItem.id != exclude_id)
            .first())


def extract_archive(path, dest_dir) -> list:
    """解压 zip/tar.gz（按魔数识别格式），返回文件路径列表。"""
    out = []
    try:
        head = path.read_bytes()[:4]
        if head[:2] == b"PK":
            with zipfile.ZipFile(path) as z:
                for n in z.namelist()[:200]:
                    if n.endswith("/"):
                        continue
                    target = dest_dir / (hashlib.md5(n.encode()).hexdigest()[:8] + "_" + n.split("/")[-1])
                    target.write_bytes(z.read(n))
                    out.append(target)
        elif head[:2] == b"\x1f\x8b" or path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(path) as t:
                members = [m for m in t.getmembers()[:200] if m.isfile()]
                for m in members:
                    target = dest_dir / (hashlib.md5(m.name.encode()).hexdigest()[:8] + "_" + m.name.split("/")[-1])
                    f = t.extractfile(m)
                    if f:
                        target.write_bytes(f.read())
                        out.append(target)
    except Exception:
        pass
    return out


def process_one(db: Session, user: User, task: ProcessingQueue) -> None:
    task.status = "processing"
    task.updated_at = datetime.utcnow()
    db.commit()
    try:
        item = None
        if task.item_id:
            item = db.query(LibraryItem).filter(LibraryItem.id == task.item_id).first()
        path = IMAGES_DIR / task.file_path.split("/")[-1] if task.file_path else None

        # 1) 日期：EXIF 优先，回退上传日期
        if item:
            date = ""
            if path and path.exists():
                date = exif_date(path)
            if not date:
                date = item.created_at.strftime("%Y-%m-%d") if item.created_at else datetime.now().strftime("%Y-%m-%d")
            item.item_date = date
            set_tags(db, user, "library_item", item.id, {"date": date})

        # 2) 基础标签
        if item:
            tags = {"source": "智学网" if item.source == "zhixuewang" else "上传"}
            if item.subject:
                tags["subject"] = item.subject
            if item.kind in ("image", "wrong_question"):
                tags.setdefault("content_type", "题目" if item.kind == "wrong_question" else "资料")
            elif item.kind == "attachment":
                tags["content_type"] = "答案"
            elif item.kind == "text":
                tags["content_type"] = "笔记"
            elif item.kind == "review":
                tags["content_type"] = "资料"
            set_tags(db, user, "library_item", item.id, tags)

        # 3) OCR / 文字提取
        task.stage = "ocr"
        db.commit()
        if item and item.ocr_status == "pending" and task.mode == "fast_ocr":
            if item.file_path and (IMAGES_DIR / item.file_path.split("/")[-1]).exists():
                item.ocr_status = "pending"  # 交给夜间/手动 AI OCR 批处理
        # ai_smart 模式的 AI 语义处理由 nightly/AI 调用接力（避免队列线程阻塞 AI 调用）

        task.status = "done"
        task.stage = "complete"
    except Exception as e:
        task.status = "failed"
        task.error = str(e)[:500]
    task.updated_at = datetime.utcnow()
    db.commit()


def run_pending(db: Session, limit: int = 20) -> int:
    """处理队列中的待办任务（手动/夜间触发均可）。"""
    tasks = (db.query(ProcessingQueue)
             .filter(ProcessingQueue.status == "pending")
             .order_by(ProcessingQueue.id)
             .limit(limit).all())
    for t in tasks:
        user = db.query(User).filter(User.id == t.user_id).first()
        if user:
            process_one(db, user, t)
    return len(tasks)
