"""OCR 文字提取：用视觉模型从图片提取文字（档案库索引用）。"""
from sqlalchemy.orm import Session

from ..models import LibraryItem, LibraryPage, User
from .context import get_vision_client

OCR_PROMPT = """你是一个 OCR 助手。请提取这张图片中的全部文字内容（包括印刷体和手写体），保持原有分段顺序。
要求：
- 只输出提取到的文字本身，不要任何解释、不要加引号。
- 看不清的字用〔?〕标注。
- 如果包含页码（通常在页脚/页眉），在最后一行单独输出：[页码: N]。"""


async def extract_text_from_image(user: User, image_path_name: str, db: Session) -> tuple[str, int | None]:
    """提取图片文字；返回 (文字, 页码|None)。image_path_name 形如 u{id}_{iid}.jpg。"""
    import re
    from ..config import IMAGES_DIR
    from .ai_client import image_to_data_uri

    client = get_vision_client(db, user)
    path = IMAGES_DIR / image_path_name
    if not path.exists():
        return "", None
    stem = image_path_name.rsplit("_", 1)[-1].rsplit(".", 1)[0]
    if not stem.isdigit():
        return "", None
    try:
        uri = image_to_data_uri(int(stem), user.id)
    except Exception:
        return "", None
    messages = [
        {"role": "system", "content": OCR_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "请提取图中文字。"},
            {"type": "image_url", "image_url": {"url": uri}},
        ]},
    ]
    text = await client.complete(messages, temperature=0.0)
    page_no = None
    m = re.search(r"\[页码:\s*(\d+)\]", text)
    if m:
        page_no = int(m.group(1))
        text = text[:m.start()].strip()
    return text.strip(), page_no


async def process_pending(db: Session, user: User, limit: int = 10) -> dict:
    """处理待 OCR 的档案条目与书页；返回处理统计。"""
    done = failed = 0
    items = (db.query(LibraryItem)
             .filter(LibraryItem.user_id == user.id,
                     LibraryItem.ocr_status == "pending",
                     LibraryItem.file_path != "")
             .limit(limit).all())
    for it in items:
        try:
            fname = it.file_path.split("/")[-1]
            text, page_no = await extract_text_from_image(user, fname, db)
            it.ocr_text = text
            it.ocr_status = "done" if text else "failed"
            if page_no and not it.page_no:
                it.page_no = page_no
            done += 1
        except Exception:
            it.ocr_status = "failed"
            failed += 1
    pages = (db.query(LibraryPage)
             .filter(LibraryPage.user_id == user.id,
                     LibraryPage.ocr_status == "pending",
                     LibraryPage.image_path != "")
             .limit(limit).all())
    for pg in pages:
        try:
            fname = pg.image_path.split("/")[-1]
            text, page_no = await extract_text_from_image(user, fname, db)
            pg.ocr_text = text
            pg.ocr_status = "done" if text else "failed"
            if page_no and not pg.page_no:
                pg.page_no = page_no
            done += 1
        except Exception:
            pg.ocr_status = "failed"
            failed += 1
    db.commit()
    return {"done": done, "failed": failed}
