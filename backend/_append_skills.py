"""一次性：向 skills.py 追加 档案库/对话/复习资料 技能（run 后自删）。"""
import io

BLOCK = '''

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
    dialogue = "\\n".join(f"{'学生' if m.role == 'user' else '导师'}：{(m.content or '')[:300]}"
                         for m in msgs)[-5000:]
    client = get_ai_client(db, user)
    focus = str(args.get("focus") or "重点总结：讨论过的知识点、学生的疑问点、达成的结论、后续行动。")
    text = await client.complete([
        {"role": "system", "content": "你是学习记录整理员。请用简洁的中文条目总结一段学习对话，不复述寒暄。"},
        {"role": "user", "content": f"{focus}\\n\\n【对话记录】\\n{dialogue}"},
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
    rows = q.filter(WrongQuestion.created_at >= datetime.utcnow() - timedelta(days=days)) \\
        .order_by(WrongQuestion.created_at.desc()).limit(30).all()
    material = "\\n".join(
        f"- [{w.subject}] {w.knowledge_points}：{(w.question_text or '')[:80]}｜错因：{(w.wrong_reason or '')[:80]}"
        for w in rows)
    nodes = progress_summary(db, user)
    weaknesses = "\\n".join(
        f"- {s}/{d.get('weak', [])}" for s, d in nodes.items() if d.get("weak"))
    client = get_ai_client(db, user)
    focus = str(args.get("focus") or "期中复习")
    text = await client.complete([
        {"role": "system", "content": f"{PERSONA_BASE_FOR_REVIEW}"},
        {"role": "user", "content": f"请为学生生成一份复习资料（{focus}）。\n【薄弱点】\n{weaknesses}\n【近 {days} 天错题】\n{material or '（无）'}"},
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
'''

p = 'backend/app/services/skills.py'
s = io.open(p, encoding='utf-8', newline='').read()
assert 'search_library' not in s
s += BLOCK

# 注册新技能进 SKILLS
reg = '''
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
'''
s += reg
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('skills.py appended; total SKILLS entries now includes', s.count('"executor"'))
