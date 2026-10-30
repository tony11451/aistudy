"""档案库 API：书本/笔记本、板块、条目、附件、搜索、下载。"""
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..database import get_db
from ..deps import get_current_user
from ..models import (Bookmark, LibraryBoard, LibraryBook, LibraryItem,
                      LibraryLink, LibraryPage, User, WrongQuestion)
from ..security import hash_password  # noqa: F401
from .settings import DEFAULT_SUBJECTS

router = APIRouter(prefix="/api/library", tags=["library"])


def _book_dict(b: LibraryBook) -> dict:
    return {"id": b.id, "subject": b.subject, "kind": b.kind, "name": b.name,
            "cover_image": b.cover_image,
            "created_at": b.created_at.isoformat() if b.created_at else None}


def _board_dict(b: LibraryBoard) -> dict:
    return {"id": b.id, "subject": b.subject, "parent_id": b.parent_id,
            "name": b.name, "sort_order": b.sort_order}


def _item_dict(it: LibraryItem, with_text: bool = False) -> dict:
    d = {
        "id": it.id, "subject": it.subject, "board_id": it.board_id,
        "book_id": it.book_id, "page_no": it.page_no, "kind": it.kind,
        "title": it.title, "content": (it.content if with_text else (it.content or "")[:200]),
        "file_path": it.file_path, "file_name": it.file_name, "file_type": it.file_type,
        "source": it.source, "ocr_status": it.ocr_status,
        "ocr_preview": (it.ocr_text or "")[:160],
        "created_at": it.created_at.isoformat() if it.created_at else None,
    }
    if with_text:
        d["ocr_text"] = it.ocr_text
    return d


# ---------- 总览 ----------
@router.get("/overview")
def overview(subject: str = Query(""), user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    bq = db.query(LibraryBook).filter(LibraryBook.user_id == user.id)
    iq = db.query(LibraryItem).filter(LibraryItem.user_id == user.id)
    brq = db.query(LibraryBoard).filter(LibraryBoard.user_id == user.id)
    if subject:
        bq = bq.filter(LibraryBook.subject == subject)
        iq = iq.filter(LibraryItem.subject == subject)
        brq = brq.filter(LibraryBoard.subject == subject)
    books = bq.order_by(LibraryBook.created_at.desc()).all()
    boards = brq.order_by(LibraryBoard.sort_order, LibraryBoard.id).all()
    counts = {
        "textbook": sum(1 for b in books if b.kind == "textbook"),
        "notebook": sum(1 for b in books if b.kind == "notebook"),
        "boards": len(boards),
        "images": iq.filter(LibraryItem.kind.in_(["image", "wrong_question"])).count(),
        "attachments": iq.filter(LibraryItem.kind == "attachment").count(),
        "texts": iq.filter(LibraryItem.kind == "text").count(),
        "reviews": iq.filter(LibraryItem.kind == "review").count(),
    }
    return {
        "counts": counts,
        "books": [_book_dict(b) for b in books],
        "boards": [_board_dict(b) for b in boards],
    }


# ---------- 书本 / 页面 ----------
@router.post("/books")
def create_book(payload: dict, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少书名")
    kind = payload.get("kind") if payload.get("kind") in ("textbook", "notebook") else "textbook"
    b = LibraryBook(user_id=user.id, subject=payload.get("subject") or "",
                    kind=kind, name=name[:128])
    db.add(b)
    db.commit()
    db.refresh(b)
    return _book_dict(b)


@router.put("/books/{bid}")
def update_book(bid: int, payload: dict, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    b = db.query(LibraryBook).filter(LibraryBook.id == bid, LibraryBook.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="书本不存在")
    if payload.get("name"):
        b.name = str(payload["name"])[:128]
    if payload.get("subject") is not None:
        b.subject = str(payload["subject"])
    if payload.get("cover_image") is not None:
        b.cover_image = str(payload["cover_image"])
    db.commit()
    return _book_dict(b)


@router.delete("/books/{bid}")
def delete_book(bid: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    b = db.query(LibraryBook).filter(LibraryBook.id == bid, LibraryBook.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="书本不存在")
    db.query(LibraryPage).filter(LibraryPage.book_id == bid).delete(synchronize_session=False)
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/books/{bid}/pages")
def list_pages(bid: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    b = db.query(LibraryBook).filter(LibraryBook.id == bid, LibraryBook.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="书本不存在")
    pages = (db.query(LibraryPage)
             .filter(LibraryPage.book_id == bid, LibraryPage.user_id == user.id)
             .order_by(LibraryPage.page_no, LibraryPage.id).all())
    return {"book": _book_dict(b), "pages": [{
        "id": p.id, "page_no": p.page_no, "image_path": p.image_path,
        "ocr_status": p.ocr_status, "ocr_preview": (p.ocr_text or "")[:200],
    } for p in pages]}


@router.post("/books/{bid}/pages")
async def add_page(bid: int, page_no: int = 0, file: UploadFile = File(...),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.query(LibraryBook).filter(LibraryBook.id == bid, LibraryBook.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="书本不存在")
    fname = await _save_image(user, file)
    if page_no <= 0:
        max_p = (db.query(LibraryPage.page_no)
                 .filter(LibraryPage.book_id == bid).all())
        page_no = (max([p[0] for p in max_p], default=0) + 1)
    pg = LibraryPage(user_id=user.id, book_id=bid, page_no=page_no,
                     image_path=fname, ocr_status="pending")
    db.add(pg)
    if not b.cover_image:
        b.cover_image = fname
    db.commit()
    db.refresh(pg)
    return {"id": pg.id, "page_no": pg.page_no, "image_path": pg.image_path}


async def _save_image(user: User, file: UploadFile) -> str:
    data = await file.read()
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="不是有效图片")
    iid = int(uuid.uuid4().int % 1_000_000_000)
    fname = f"u{user.id}_{iid}.jpg"
    img.save(IMAGES_DIR / fname, format="JPEG", quality=88)
    return fname


# ---------- 板块 ----------
BOARD_TEMPLATES = ["题目版", "答案版", "解析版", "知识点版", "订正版"]


@router.get("/boards")
def list_boards(subject: str = Query(""), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    q = db.query(LibraryBoard).filter(LibraryBoard.user_id == user.id)
    if subject:
        q = q.filter(LibraryBoard.subject == subject)
    boards = q.order_by(LibraryBoard.sort_order, LibraryBoard.id).all()
    items_q = db.query(LibraryItem).filter(LibraryItem.user_id == user.id)
    item_counts = {}
    for it in items_q.all():
        if it.board_id:
            item_counts[it.board_id] = item_counts.get(it.board_id, 0) + 1
    link_counts = {}
    for lk in db.query(LibraryLink).filter(LibraryLink.board_id.in_(
            [b.id for b in boards])).all() if boards else []:
        link_counts[lk.board_id] = link_counts.get(lk.board_id, 0) + 1
    return [{
        **_board_dict(b),
        "item_count": item_counts.get(b.id, 0) + link_counts.get(b.id, 0),
    } for b in boards]


@router.post("/boards")
def create_board(payload: dict, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少板块名")
    parent_id = payload.get("parent_id")
    b = LibraryBoard(user_id=user.id, subject=payload.get("subject") or "",
                     parent_id=int(parent_id) if parent_id else None,
                     name=name[:128])
    db.add(b)
    db.commit()
    db.refresh(b)
    return _board_dict(b)


@router.post("/boards/{bid}/templates")
def create_board_templates(bid: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """在大板块下按预设词创建分板块（题目版/答案版…）。"""
    parent = db.query(LibraryBoard).filter(LibraryBoard.id == bid,
                                          LibraryBoard.user_id == user.id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="板块不存在")
    created = []
    for name in BOARD_TEMPLATES:
        child = LibraryBoard(user_id=user.id, subject=parent.subject,
                             parent_id=parent.id, name=name)
        db.add(child)
        created.append(name)
    db.commit()
    return {"ok": True, "created": created}


@router.put("/boards/{bid}")
def update_board(bid: int, payload: dict, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    b = db.query(LibraryBoard).filter(LibraryBoard.id == bid, LibraryBoard.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="板块不存在")
    if payload.get("name"):
        b.name = str(payload["name"])[:128]
    if payload.get("subject") is not None:
        b.subject = str(payload["subject"])
    db.commit()
    return _board_dict(b)


@router.delete("/boards/{bid}")
def delete_board(bid: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    b = db.query(LibraryBoard).filter(LibraryBoard.id == bid, LibraryBoard.user_id == user.id).first()
    if not b:
        raise HTTPException(status_code=404, detail="板块不存在")
    kids = db.query(LibraryBoard).filter(LibraryBoard.parent_id == bid).all()
    for k in kids:
        k.parent_id = b.parent_id
    db.query(LibraryItem).filter(LibraryItem.board_id == bid).update({"board_id": None})
    db.query(LibraryLink).filter(LibraryLink.board_id == bid).delete(synchronize_session=False)
    db.delete(b)
    db.commit()
    return {"ok": True}


# ---------- 条目 ----------
@router.get("/items")
def list_items(subject: str = Query(""), kind: str = Query(""),
               source: str = Query(""), board_id: int = Query(0),
               book_id: int = Query(0), q: str = Query(""),
               limit: int = Query(60, le=200), offset: int = 0,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(LibraryItem).filter(LibraryItem.user_id == user.id)
    if subject:
        query = query.filter(LibraryItem.subject == subject)
    if kind:
        query = query.filter(LibraryItem.kind == kind)
    if source:
        query = query.filter(LibraryItem.source == source)
    if board_id:
        linked = [lk.item_id for lk in db.query(LibraryLink)
                  .filter(LibraryLink.board_id == board_id).all()]
        query = query.filter(or_(LibraryItem.board_id == board_id,
                                 LibraryItem.id.in_(linked) if linked else False))
    if book_id:
        query = query.filter(LibraryItem.book_id == book_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(LibraryItem.title.like(like),
                                 LibraryItem.content.like(like),
                                 LibraryItem.ocr_text.like(like),
                                 LibraryItem.file_name.like(like)))
    total = query.count()
    rows = query.order_by(LibraryItem.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_item_dict(it) for it in rows]}


@router.get("/items/{iid}")
def get_item(iid: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    it = db.query(LibraryItem).filter(LibraryItem.id == iid,
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise HTTPException(status_code=404, detail="条目不存在")
    return _item_dict(it, with_text=True)


@router.post("/items/upload")
async def upload_items(subject: str = "", kind: str = "image", board_id: int = 0,
                       book_id: int = 0, page_no: int = 0,
                       files: list[UploadFile] = File(...),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind = kind if kind in ("image", "attachment", "text", "review", "wrong_question") else "image"
    saved = []
    for f in files[:12]:
        raw = await f.read()
        if kind in ("image", "wrong_question", "review"):
            try:
                img = Image.open(io.BytesIO(raw)).convert("RGB")
            except (UnidentifiedImageError, OSError):
                raise HTTPException(status_code=400, detail=f"{f.filename} 不是有效图片")
            iid = int(uuid.uuid4().int % 1_000_000_000)
            fname = f"u{user.id}_{iid}.jpg"
            img.save(IMAGES_DIR / fname, format="JPEG", quality=88)
            item = LibraryItem(user_id=user.id, subject=subject or "",
                               board_id=board_id or None,
                               book_id=book_id or None,
                               page_no=page_no or None,
                               kind=kind, title=f.filename or "图片",
                               file_path=fname, file_name=f.filename or fname,
                               file_type="image/jpeg", source="upload",
                               ocr_status="pending")
        else:
            # 附件/文本：保存原始文件（.txt/.md 直接读文字；其余提取文本）
            ext = (f.filename or "").rsplit(".", 1)[-1].lower()
            iid = int(uuid.uuid4().int % 1_000_000_000)
            fname = f"u{user.id}_{iid}.bin"
            (IMAGES_DIR / fname).write_bytes(raw)
            text = ""
            if ext in ("txt", "md", "csv", "json", "srt"):
                text = raw.decode("utf-8", errors="ignore")[:20000]
            elif ext == "pdf":
                text = _extract_pdf_text(raw)[:20000]
            elif ext == "docx":
                text = _extract_docx_text(raw)[:20000]
            item = LibraryItem(user_id=user.id, subject=subject or "",
                               board_id=board_id or None,
                               kind="attachment", title=f.filename or "附件",
                               content=text, file_path=fname,
                               file_name=f.filename or fname,
                               file_type=ext or "bin", source="upload",
                               ocr_status="done" if text else "none")
        db.add(item)
        db.flush()
        saved.append(_item_dict(item))
    db.commit()
    return {"items": saved}


@router.post("/items/text")
def create_text_item(payload: dict, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    content = str(payload.get("content") or "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="内容为空")
    it = LibraryItem(user_id=user.id, subject=payload.get("subject") or "",
                     board_id=int(payload["board_id"]) if payload.get("board_id") else None,
                     kind="text", title=str(payload.get("title") or "文字笔记")[:256],
                     content=content[:20000], source="manual", ocr_status="none")
    db.add(it)
    db.commit()
    db.refresh(it)
    return _item_dict(it)


@router.put("/items/{iid}")
def update_item(iid: int, payload: dict, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    it = db.query(LibraryItem).filter(LibraryItem.id == iid,
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise HTTPException(status_code=404, detail="条目不存在")
    for field in ("title", "content", "subject"):
        if field in payload:
            setattr(it, field, str(payload[field] or "")[:2000] if field != "title" else str(payload[field])[:256])
    if "board_id" in payload:
        it.board_id = int(payload["board_id"]) if payload["board_id"] else None
    if "book_id" in payload:
        it.book_id = int(payload["book_id"]) if payload["book_id"] else None
    if "page_no" in payload:
        it.page_no = int(payload["page_no"]) if payload["page_no"] else None
    db.commit()
    db.refresh(it)
    return _item_dict(it)


@router.delete("/items/{iid}")
def delete_item(iid: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    it = db.query(LibraryItem).filter(LibraryItem.id == iid,
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise HTTPException(status_code=404, detail="条目不存在")
    db.query(LibraryLink).filter(LibraryLink.item_id == iid).delete(synchronize_session=False)
    db.delete(it)
    db.commit()
    return {"ok": True}


@router.post("/items/{iid}/link")
def link_item(iid: int, payload: dict, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """把条目（常为附件）挂载到板块。"""
    it = db.query(LibraryItem).filter(LibraryItem.id == iid,
                                      LibraryItem.user_id == user.id).first()
    board_id = int(payload.get("board_id") or 0)
    board = db.query(LibraryBoard).filter(LibraryBoard.id == board_id,
                                          LibraryBoard.user_id == user.id).first()
    if not it or not board:
        raise HTTPException(status_code=404, detail="条目或板块不存在")
    exists = db.query(LibraryLink).filter(LibraryLink.item_id == iid,
                                          LibraryLink.board_id == board_id).first()
    if not exists:
        db.add(LibraryLink(item_id=iid, board_id=board_id))
        db.commit()
    return {"ok": True}


@router.delete("/items/{iid}/link/{board_id}")
def unlink_item(iid: int, board_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    db.query(LibraryLink).filter(LibraryLink.item_id == iid,
                                 LibraryLink.board_id == board_id).delete()
    db.commit()
    return {"ok": True}


# ---------- 下载 ----------
@router.get("/items/{iid}/download")
def download_item(iid: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    it = db.query(LibraryItem).filter(LibraryItem.id == iid,
                                      LibraryItem.user_id == user.id).first()
    if not it:
        raise HTTPException(status_code=404, detail="条目不存在")
    if not it.file_path:
        raise HTTPException(status_code=400, detail="该条目没有文件")
    path = IMAGES_DIR / it.file_path.split("/")[-1]
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=it.file_name or path.name,
                        media_type="application/octet-stream")


@router.get("/books/{bid}/pages/{pid}/download")
def download_page(bid: int, pid: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    pg = db.query(LibraryPage).filter(LibraryPage.id == pid,
                                      LibraryPage.user_id == user.id).first()
    if not pg or not pg.image_path:
        raise HTTPException(status_code=404, detail="页面不存在")
    path = IMAGES_DIR / pg.image_path.split("/")[-1]
    return FileResponse(path, filename=path.name, media_type="image/jpeg")


# ---------- 书签 ----------
@router.get("/bookmarks")
def list_bookmarks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Bookmark).filter(Bookmark.user_id == user.id)
            .order_by(Bookmark.created_at.desc()).limit(200).all())
    return [{
        "id": b.id, "target_type": b.target_type, "target_id": b.target_id,
        "label": b.label, "note": b.note,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    } for b in rows]


@router.post("/bookmarks")
def create_bookmark(payload: dict, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    b = Bookmark(user_id=user.id,
                 target_type=str(payload.get("target_type") or "library_item"),
                 target_id=int(payload.get("target_id") or 0),
                 label=str(payload.get("label") or "")[:128],
                 note=str(payload.get("note") or "")[:1000])
    db.add(b)
    db.commit()
    db.refresh(b)
    return {"id": b.id}


@router.delete("/bookmarks/{bid}")
def delete_bookmark(bid: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    db.query(Bookmark).filter(Bookmark.id == bid, Bookmark.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


# ---------- 文本提取辅助 ----------
def _extract_pdf_text(raw: bytes) -> str:
    try:
        import pypdf  # 可选依赖
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:50])
    except Exception:
        return ""


def _extract_docx_text(raw: bytes) -> str:
    try:
        import zipfile
        import re as _re
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        return _re.sub(r"<[^>]+>", " ", xml)[:20000]
    except Exception:
        return ""


# ---------- OCR 手动触发 ----------
@router.post("/ocr/run")
async def run_ocr(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..services.ocr import process_pending
    try:
        result = await process_pending(db, user, limit=20)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OCR 失败：{e}")
    return result
