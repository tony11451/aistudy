"""智学网同步（zhixuewang SDK）：作业/考试/错题本/原卷 → 档案库 + 错题本。

SDK 真实签名（1.5.1）：
- get_homeworks(size=20) -> [StuHomework(id,title,subject_name,begin_time,type)]
- get_homework_answer(hw) -> [HwAnswer(title,content)]（仅部分作业类型）
- get_homework_resources(hw) -> [HwResource(path=URL,name)]
- get_exams() -> [Exam(id,name,...)]
- get_subjects(exam) -> [Subject(id,name)]
- get_original(subject, exam) -> [图片URL str]
- get_errorbook(exam_id, subject_id) -> [ErrorBookTopic(...)]
下载图片需带登录 Cookie（部分资源需要鉴权）。
"""
import hashlib
import io
import re
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import IMAGES_DIR
from ..models import (LibraryBoard, LibraryItem, ProcessingQueue, User,
                      WrongQuestion, ZhixueAccount, ZhixueSyncRun)

ZXW = "zhixuewang"


def _sdk():
    try:
        from zhixuewang.account import login_cookie
        return login_cookie
    except ImportError:
        raise RuntimeError("未安装 zhixuewang 包，请先 pip install zhixuewang")


def login_check(cookie: str) -> tuple[bool, str]:
    try:
        login_cookie = _sdk()
        account = login_cookie(cookie)
        student = account.to_student()
        name = getattr(getattr(student, "person", None), "name", "") or "学生"
        return True, f"登录成功（{name}）"
    except Exception as e:
        return False, f"登录失败：{e}"


def _txt(obj, *keys, default=""):
    for k in keys:
        v = getattr(obj, k, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return default


def _strip_html(html: str) -> str:
    """HTML → 纯文本：去标签 + 实体解码（&deg; &nbsp; 等）+ 空白归一。"""
    import html as _html
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = _html.unescape(t)
    t = t.replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _meaningless(text: str) -> bool:
    """判定伪内容：'略'、'无'、'答案：略' 等。"""
    t = re.sub(r"[\s:：。．,.，]", "", text or "")
    return t in ("", "略", "无", "暂无", "答案略", "解析略", "见解析", "见答案", "本题略")


def _ms_date(ms) -> str:
    try:
        n = int(ms)
        if n > 10 ** 12:
            n //= 1000
        return datetime.fromtimestamp(n).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _download(url: str, cookie: str) -> bytes | None:
    """带 Cookie 下载图片（部分资源需鉴权）。"""
    if not url or not str(url).startswith("http"):
        return None
    try:
        import httpx
        r = httpx.get(url, timeout=30, follow_redirects=True,
                      headers={"Cookie": cookie, "Referer": "https://edc.zhixue.com/"})
        if r.status_code == 200 and len(r.content) > 500:
            return r.content
    except Exception:
        pass
    return None


def _save_image_bytes(db: Session, user: User, blob: bytes, ext_id: str,
                      title: str, subject: str, item_date: str,
                      board_id=None, source_url: str = "") -> bool:
    """下载的图片存为档案图片条目（幂等）；source_url 供坏图重下。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob)).convert("RGB")
    except Exception:
        return False
    exists = (db.query(LibraryItem)
              .filter(LibraryItem.user_id == user.id, LibraryItem.external_id == ext_id)
              .first())
    if exists:
        return False
    iid = int(hashlib.md5(ext_id.encode()).hexdigest()[:8], 16) % 1_000_000_000
    fname = f"u{user.id}_{iid}.jpg"
    img.save(IMAGES_DIR / fname, format="JPEG", quality=88)
    db.add(LibraryItem(user_id=user.id, subject=subject or "", board_id=board_id,
                       kind="image", title=title[:256], file_path=fname,
                       file_name=fname, file_type="image/jpeg", source=ZXW,
                       external_id=ext_id, item_date=item_date,
                       source_url=(source_url or "")[:512],
                       ocr_status="pending"))
    return True


def _get_or_create_board(db: Session, user: User, name: str, subject: str = "") -> int:
    b = (db.query(LibraryBoard)
         .filter(LibraryBoard.user_id == user.id, LibraryBoard.name == name)
         .first())
    if not b:
        b = LibraryBoard(user_id=user.id, subject=subject, name=name)
        db.add(b)
        db.flush()
    return b.id


def _upsert_item(db: Session, user: User, ext_id: str, defaults: dict) -> tuple[LibraryItem, bool]:
    it = (db.query(LibraryItem)
          .filter(LibraryItem.user_id == user.id, LibraryItem.external_id == ext_id)
          .first())
    if it:
        for k, v in defaults.items():
            if v not in (None, ""):
                setattr(it, k, v)
        return it, False
    it = LibraryItem(user_id=user.id, external_id=ext_id, source=ZXW, **defaults)
    db.add(it)
    db.flush()
    return it, True


def sync_homeworks(db: Session, user: User, student, cookie: str) -> tuple[int, int, int]:
    added = updated = 0
    board_id = _get_or_create_board(db, user, "智学网作业")
    try:
        hw_list = student.get_homeworks(size=50) or []
    except Exception:
        return 0, 0, 1
    for hw in hw_list[:100]:
        try:
            ext = f"zxw-hw-{_txt(hw, 'id', 'stu_hwid') or _txt(hw, 'title')[:20]}"
            title = _txt(hw, "title", default="").strip()
            if not title or title in ("无", "暂无", "无标题"):
                continue  # 无效作业数据，跳过
            subject = _txt(hw, "subject_name", "subject")
            item_date = _ms_date(getattr(hw, "begin_time", 0) or getattr(hw, "create_time", 0))
            it, is_new = _upsert_item(db, user, ext, {
                "board_id": board_id, "subject": subject,
                "kind": "text", "title": f"作业·{title}"[:256],
                "content": title[:20000], "item_date": item_date,
                "ocr_status": "none",
            })
            added += is_new
            updated += (not is_new)
            # 答案（HwAnswer 列表）
            try:
                answers = student.get_homework_answer(hw) or []
                texts = [f"{a.title}\n{a.content}" for a in answers if getattr(a, "content", "")]
                if texts:
                    _upsert_item(db, user, f"{ext}-ans", {
                        "subject": subject, "kind": "attachment",
                        "title": f"{title}·答案"[:256],
                        "content": "\n\n".join(texts)[:20000],
                        "item_date": item_date, "ocr_status": "done",
                        "file_type": "text",
                    })
            except Exception:
                pass
            # 资源（HwResource 列表：path=下载URL）
            try:
                resources = student.get_homework_resources(hw) or []
                for ri, res in enumerate(resources[:6]):
                    url = getattr(res, "path", "") or ""
                    blob = _download(url, cookie)
                    if not blob:
                        continue
                    name = getattr(res, "name", "") or f"res{ri}"
                    _save_image_bytes(db, user, blob, f"{ext}-res{ri}",
                                      f"{title}·{name}"[:256], subject, item_date, board_id,
                                      source_url=url)
            except Exception:
                pass
        except Exception:
            continue
    return added, updated, 0


def sync_exams(db: Session, user: User, student, cookie: str) -> tuple[int, int, int]:
    added = updated = 0
    board_id = _get_or_create_board(db, user, "智学网考试")
    try:
        exams = student.get_exams() or []
    except Exception:
        return 0, 0, 1
    for exam in exams[:50]:
        try:
            exam_id = _txt(exam, "id") or _txt(exam, "examId")
            ext = f"zxw-exam-{exam_id or _txt(exam, 'name')[:20]}"
            name = _txt(exam, "name", "title", default="考试")
            exam_time = getattr(exam, "exam_time", 0) or getattr(exam, "create_time", 0)
            item_date = _ms_date(exam_time) if exam_time else datetime.now().strftime("%Y-%m-%d")
            # 成绩
            score_text = ""
            try:
                mark = student.get_self_mark(exam)
                lines = []
                for s in (mark or []):
                    subj = getattr(getattr(s, "subject", None), "name", "") or _txt(s, "subject")
                    sc = getattr(s, "score", None)
                    lines.append(f"{subj}: {sc}")
                score_text = "\n".join(lines)
            except Exception:
                pass
            _, is_new = _upsert_item(db, user, ext, {
                "board_id": board_id, "kind": "text",
                "title": f"考试·{name}"[:256],
                "content": (score_text or name)[:20000],
                "item_date": item_date, "ocr_status": "none",
            })
            added += is_new
            updated += (not is_new)
            # 原卷图片（按学科逐份拉取）
            try:
                subjects = student.get_subjects(exam) or []
            except Exception:
                subjects = []
            for subj in subjects[:10]:
                try:
                    urls = student.get_original(subj, exam) or []
                except Exception:
                    continue
                subj_name = _txt(subj, "name")
                for oi, url in enumerate(list(urls)[:6]):
                    blob = _download(url, cookie)
                    if not blob:
                        continue
                    if _save_image_bytes(db, user, blob, f"{ext}-{getattr(subj, 'id', oi)}-img{oi}",
                                         f"原卷·{name}·{subj_name} #{oi + 1}"[:256],
                                         subj_name, item_date, board_id, source_url=url):
                        added += 1
        except Exception:
            continue
    return added, updated, 0


def sync_errorbook(db: Session, user: User, student, cookie: str) -> tuple[int, int, int]:
    added = updated = 0
    board_id = _get_or_create_board(db, user, "智学网错题")
    try:
        exams = student.get_exams() or []
    except Exception:
        return 0, 0, 1
    for exam in exams[:30]:
        exam_id = _txt(exam, "id") or _txt(exam, "examId")
        exam_name = _txt(exam, "name", "title", default="考试")
        try:
            subjects = student.get_subjects(exam) or []
        except Exception:
            continue
        for subj in subjects[:10]:
            subj_id = getattr(subj, "id", "") or ""
            subj_name = _txt(subj, "name")
            try:
                topics = student.get_errorbook(exam_id, subj_id) or []
            except Exception:
                continue
            for e in topics[:50]:
                try:
                    ext = f"zxw-err-{_txt(e, 'paper_id')}-{_txt(e, 'dis_title_number')}"
                    if not _txt(e, "paper_id"):
                        ext = f"zxw-err-{hashlib.md5((exam_id + subj_id + _txt(e, 'content_html')[:80]).encode()).hexdigest()[:16]}"
                    qtext = _strip_html(_txt(e, "content_html"))
                    if not qtext and not _txt(e, "topic_img_url"):
                        continue  # 无题干无图 = 无效错题
                    qtext = qtext or "错题图"
                    analysis = _strip_html(_txt(e, "analysis_html", "answer_html", "standard_answer"))
                    if _meaningless(analysis):
                        analysis = ""  # "略"等伪内容置空，交给 AI 整理补全
                    it, is_new = _upsert_item(db, user, ext, {
                        "board_id": board_id, "subject": _txt(e, "subject_name") or subj_name,
                        "kind": "wrong_question", "title": qtext[:256],
                        "content": analysis[:20000], "item_date": "",
                        "ocr_status": "none",
                    })
                    added += is_new
                    updated += (not is_new)
                    # 题目图片
                    topic_img = _txt(e, "topic_img_url")
                    img_urls = []
                    if topic_img:
                        blob = _download(topic_img, cookie)
                        if blob:
                            fname = f"u{user.id}_{int(hashlib.md5((ext + 'q').encode()).hexdigest()[:8], 16) % 1_000_000_000}.jpg"
                            try:
                                from PIL import Image
                                Image.open(io.BytesIO(blob)).convert("RGB").save(
                                    IMAGES_DIR / fname, format="JPEG", quality=88)
                                img_urls.append(f"/api/images/{fname}")
                                _save_image_bytes(db, user, blob, f"{ext}-img",
                                                  f"错题图·{qtext[:20]}"[:256],
                                                  _txt(e, "subject_name") or subj_name,
                                                  "", board_id, source_url=topic_img)
                            except Exception:
                                pass
                    if is_new:
                        wq = WrongQuestion(
                            user_id=user.id,
                            subject=_txt(e, "subject_name") or subj_name or "综合",
                            question_text=qtext[:4000],
                            correct_solution=analysis[:4000],
                            wrong_reason=f"来自智学网错题本（{_txt(e, 'topic_source_paper_name') or exam_name}）",
                            difficulty = {1: "简单", 2: "简单", 3: "中等", 4: "较难", 5: "较难"}
                                .get(getattr(e, "difficulty", 3) or 3, "中等"),
                            source="photo" if img_urls else "text",
                            images=img_urls, original_images=img_urls,
                            mastery="weak",
                        )
                        db.add(wq)
                except Exception:
                    continue
    return added, updated, 0


def sync_user(db: Session, user: User, scope: str = "all") -> dict:
    acc = db.query(ZhixueAccount).filter(ZhixueAccount.user_id == user.id).first()
    if not acc or not acc.enabled:
        raise RuntimeError("智学网集成未启用")
    if not acc.cookie:
        raise RuntimeError("未配置 Cookie，请先登录智学网")
    login_cookie = _sdk()
    try:
        account = login_cookie(acc.cookie)
        student = account.to_student()
    except Exception as e:
        acc.status = "cookie_expired"
        db.commit()
        raise RuntimeError(f"Cookie 登录失败（可能已过期）：{e}")

    acc.status = "ok"
    added = updated = failed = 0
    tasks = []
    if scope in ("all", "homework"):
        tasks.append(("homework", sync_homeworks))
    if scope in ("all", "exam"):
        tasks.append(("exam", sync_exams))
    if scope in ("all", "errorbook"):
        tasks.append(("errorbook", sync_errorbook))
    messages = []
    for name, fn in tasks:
        try:
            a, u, f = fn(db, user, student, acc.cookie)
            added += a
            updated += u
            failed += f
            messages.append(f"{name}: +{a}/~{u}")
        except Exception as e:
            failed += 1
            messages.append(f"{name} 失败: {e}")
    db.commit()

    run = ZhixueSyncRun(user_id=user.id, scope=scope, added=added,
                        updated=updated, failed=failed,
                        message="; ".join(messages)[:1000])
    db.add(run)
    acc.last_sync_at = datetime.utcnow()
    acc.last_sync_summary = f"+{added}/~{updated}/✗{failed}"
    db.commit()
    return {"added": added, "updated": updated, "failed": failed,
            "message": "; ".join(messages)[:1000]}
