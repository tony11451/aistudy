"""v6 E2E：教研组 / 智学网(模拟SDK) / 队列去重 / 标签 / 夜间审核 / 小组件 / 备份 v2。"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="st_v6_"))

# ---------- mock AI ----------
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402

mock = FastAPI()


@mock.post("/v1/chat/completions")
async def chat(req: Request):
    b = await req.json()
    sysmsg = b["messages"][0]["content"]
    if "学习进度分析员" in sysmsg:
        ans = json.dumps({"learning_items": [{"knowledge_point": "一元二次方程",
                                              "unit": "一元二次方程",
                                              "learning_state": "learning",
                                              "evidence": "新资料"}]}, ensure_ascii=False)
    elif "学习助理" in sysmsg:
        ans = "- 简报要点一\n- 简报要点二"
    elif "学习资料整理员" in sysmsg:
        user_txt = json.dumps(b["messages"][-1], ensure_ascii=False)
        if "垃圾内容" in user_txt:
            ans = json.dumps({"is_junk": True, "title": "", "question_text": "",
                              "correct_solution": "", "wrong_reason": "", "content": ""},
                             ensure_ascii=False)
        else:
            ans = json.dumps({
                "is_junk": False,
                "title": "清洗后标题",
                "question_text": "如图，已知 AD // BC，∠ADP=90°，…",
                "correct_solution": "证明：\n1. 由角平分线性质得…\n$$AP=BP$$",
                "wrong_reason": "易错点：角平分线+平行线构等腰模型",
                "content": "清洗后正文",
            }, ensure_ascii=False)
    else:
        ans = "这是一条老师回复。## 要点\n- 内容"
    if b.get("stream"):
        async def gen():
            yield f'data: {json.dumps({"choices": [{"delta": {"content": ans}}]}, ensure_ascii=False)}\n\n'
            yield "data: [DONE]\n\n"
        from fastapi.responses import StreamingResponse
        return StreamingResponse(gen(), media_type="text/event-stream")
    return {"choices": [{"message": {"content": ans}}]}


def run_mock():
    uvicorn.run(mock, host="127.0.0.1", port=18911, log_level="error")


threading.Thread(target=run_mock, daemon=True).start()
time.sleep(1.5)

# ---------- mock zhixuewang SDK ----------
class _FakeSubject:
    def __init__(self, id="s1", name="数学"):
        self.id = id
        self.name = name


class _FakeHW:
    id = "hw001"
    stu_hwid = "hw001"
    title = "数学作业1"
    subject_name = "数学"
    begin_time = 1756665600000
    create_time = 1756665600000


class _FakeAnswer:
    title = "答案"
    content = "答案：略"


class _FakeRes:
    path = "http://fake.local/res1.jpg"
    name = "res1.jpg"


class _FakeExam:
    id = "ex001"
    name = "月考"
    exam_time = 1757011200000
    create_time = 1757011200000


class _FakeMark:
    def __init__(self):
        self.subject = _FakeSubject(name="数学")
        self.score = 120


class _FakeErrTopic:
    analysis_html = "<p>因式分解得 x=2 或 3</p>"
    answer_html = "<p>x1=2, x2=3</p>"
    answer_type = "1"
    is_correct = False
    class_score_rate = 0.6
    content_html = "<p>解方程 x^2-5x+6=0</p>"
    difficulty = 3
    dis_title_number = "18"
    paper_id = "paper001"
    subject_name = "数学"
    score = 5
    standard_answer = "x=2 或 3"
    standard_score = 5
    topic_set_id = "s1"
    topic_img_url = "http://fake.local/topic.jpg"
    topic_source_paper_name = "月考卷"
    image_answer = []
    topic_analysis_img_url = ""


class _FakeStudent:
    def get_homeworks(self, size=20, is_complete=False):
        return [_FakeHW()]

    def get_homework_answer(self, hw):
        return [_FakeAnswer()]

    def get_homework_resources(self, hw):
        return [_FakeRes()]

    def get_exams(self):
        return [_FakeExam()]

    def get_self_mark(self, exam, has_total_score=True):
        return [_FakeMark()]

    def get_subjects(self, exam):
        return [_FakeSubject(id="s1", name="数学")]

    def get_original(self, subject, exam=""):
        # 真实签名：(subject, exam) → List[图片URL]
        return ["http://fake.local/orig1.jpg", "http://fake.local/orig2.jpg"]

    def get_errorbook(self, exam_id, topic_set_id):
        # 真实签名：(exam_id, subject_id) → List[ErrorBookTopic]
        return [_FakeErrTopic()]


class _FakeAccount:
    def to_student(self):
        return _FakeStudent()


import types  # noqa: E402

fake_mod = types.ModuleType("zhixuewang")
fake_acc = types.ModuleType("zhixuewang.account")
fake_acc.login_cookie = lambda cookie: _FakeAccount() if cookie == "good-cookie" else (_ for _ in ()).throw(ValueError("bad cookie"))
fake_mod.account = fake_acc
fake_mod.login_cookie = fake_acc.login_cookie
sys.modules["zhixuewang"] = fake_mod
sys.modules["zhixuewang.account"] = fake_acc
from app.services import zhixue as _zxw_mod
from PIL import Image as _Img
_buf = io.BytesIO()
_Img.new("RGB", (60, 40), (220, 230, 255)).save(_buf, format="JPEG")
_FAKE_IMG = _buf.getvalue()
_zxw_mod._download = lambda url, cookie: _FAKE_IMG if str(url).startswith("http") else None

# ---------- 被测应用 ----------
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
ok = []


def check(name, cond, extra=""):
    ok.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")


try:
    setup = req = c.post("/api/auth/setup", json={"username": "v6", "password": "123456",
                                                  "display_name": "v6", "grade": "初三"})
    H = {"Authorization": f"Bearer {setup.json()['access_token']}", "Content-Type": "application/json"}
    HU = {"Authorization": f"Bearer {setup.json()['access_token']}"}  # 上传用（不带 Content-Type）
    c.put("/api/settings/global", headers=H, json={
        "api_base_url": "http://127.0.0.1:18911/v1", "api_key": "sk-mock",
        "chat_model": "mock-chat", "vision_model": "mock-vision",
        "temperature": 0.5, "system_extra_prompt": ""})

    # 1) 老师常驻流
    t = c.post("/api/chat/teacher-thread", headers=H, json={"subject": "数学"})
    tid = t.json()["id"]
    check("teacher_thread_create", t.json()["kind"] == "teacher" and t.json()["context_ref"] == "数学")
    t2 = c.post("/api/chat/teacher-thread", headers=H, json={"subject": "数学"})
    check("teacher_thread_reuse", t2.json()["id"] == tid)
    c.post(f"/api/chat/conversations/{tid}/messages", headers=H,
           json={"content": "老师好", "image_ids": []})
    hist = c.get(f"/api/chat/conversations/{tid}", headers=H)
    check("teacher_thread_msg", len(hist.json()["messages"]) == 2)
    tl = c.get("/api/chat/teachers", headers=H)
    check("teachers_list", tl.json()["coordinator"]["kind"] == "coordinator")

    # 2) 教研记录技能（走 chat 协议太绕，直接调 skill 执行器）
    from app.database import SessionLocal
    from app.models import User
    from app.services.skills import execute_skill
    import asyncio
    db = SessionLocal()
    u = db.query(User).filter(User.username == "v6").first()
    r = asyncio.run(execute_skill(db, u, {}, "post_teacher_note",
                                  {"content": "数学计算失误影响物理", "subject": "数学",
                                   "confidence": "likely", "author": "数学"}))
    check("teacher_note", "观察" in r["summary"])
    r2 = asyncio.run(execute_skill(db, u, {}, "read_teacher_notes", {"subject": "数学"}))
    check("teacher_notes_read", len(r2["data"]) == 1)

    # 3) 智学网：登录校验 + 全量同步
    r = c.post("/api/zhixue/login", headers=H, json={"cookie": "bad"})
    check("zxw_bad_cookie", r.json()["ok"] is False)
    r = c.post("/api/zhixue/login", headers=H, json={"cookie": "good-cookie"})
    check("zxw_login", r.json()["ok"] is True, r.text[:120])
    r = c.post("/api/zhixue/sync", headers=H, json={"scope": "all"})
    res = r.json()
    check("zxw_sync", res["added"] >= 3, str(res))
    items = c.get("/api/library/items?q=" + urllib.parse.quote("数学作业"), headers=H)
    check("zxw_homework_in_library", items.json()["total"] >= 1, str(items.json()["total"]))
    wq = c.get("/api/wrong-questions", headers=H)
    wq_items = wq.json()["items"]
    check("zxw_errorbook_in_wq", wq.json()["total"] >= 1)
    check("zxw_errorbook_has_image", any(it.get("images") for it in wq_items),
          str([it.get("images") for it in wq_items])[:160])
    lib_all = c.get("/api/library/items?limit=60", headers=H)
    img_items = [it for it in lib_all.json()["items"] if it["kind"] == "image"]
    check("zxw_original_images_loaded", len(img_items) >= 3,
          f"image items: {len(img_items)}")
    runs = c.get("/api/zhixue/sync-runs", headers=H)
    check("zxw_sync_recorded", len(runs.json()) == 1)

    # 4) 去重替换
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (255, 200, 200)).save(buf, format="JPEG")
    img_bytes = buf.getvalue()
    up = c.post("/api/library/items/upload?kind=image", headers=HU,
                files=[("files", ("t.jpg", img_bytes, "image/jpeg"))])
    if "items" not in up.json():
        print("DEBUG upload resp:", up.status_code, up.text[:500])
    iid = up.json()["items"][0]["id"]
    check("upload_first", up.json()["items"][0]["replaced"] is False)
    up2 = c.post("/api/library/items/upload?kind=image", headers=HU,
                 files=[("files", ("t.jpg", img_bytes, "image/jpeg"))])
    check("upload_dedup_replace", up2.json()["items"][0]["replaced"] is True
          and up2.json()["items"][0]["id"] == iid, str(up2.json())[:160])

    # 5) 标签与队列
    from app.models import ItemTag, ProcessingQueue
    tags = db.query(ItemTag).filter(ItemTag.user_id == u.id, ItemTag.target_id == iid).all()
    check("tags_created", any(t.tag_type == "date" for t in tags) and any(t.tag_type == "source" for t in tags),
          str([(t.tag_type, t.tag_value) for t in tags]))
    pq = db.query(ProcessingQueue).filter(ProcessingQueue.user_id == u.id).all()
    check("queue_enqueued", len(pq) >= 1)
    from app.services.pipeline import run_pending
    run_pending(db)
    check("queue_processed", all(t.status == "done" for t in pq))

    # 6) 压缩包入队
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        ib = io.BytesIO()
        Image.new("RGB", (50, 50), (200, 255, 200)).save(ib, format="JPEG")
        z.writestr("a.jpg", ib.getvalue())
        z.writestr("b.txt", "hello text")
    up3 = c.post("/api/library/items/upload?kind=attachment", headers=HU,
                 files=[("files", ("pack.zip", zbuf.getvalue(), "application/zip"))])
    check("archive_extract", len(up3.json()["items"]) == 2, str(up3.json())[:160])

    # 7) 夜间整理（未开自动审核 → pending）+ 审核
    c.put("/api/settings/nightly", headers=H, json={
        "nightly_time": "23:00", "nightly_enabled": True,
        "nightly_mode": "ai_smart", "auto_approve_nightly": False})
    r = c.post("/api/library/nightly/run", headers=H, json={})
    check("nightly_run", r.status_code == 200)
    runs = c.get("/api/settings/nightly/runs", headers=H)
    check("nightly_run_recorded", len(runs.json()) >= 1 and runs.json()[0]["status"] == "pending",
          str(runs.json()[:1]))
    rid = runs.json()[0]["id"]
    ch = c.get("/api/changes?status=pending", headers=H)
    check("nightly_changes_pending", len(ch.json()) >= 1)
    r = c.post(f"/api/settings/nightly/runs/{rid}/review", headers=H, json={"action": "approve"})
    check("nightly_approve", r.json()["status"] == "approved")
    ch2 = c.get("/api/changes?status=pending", headers=H)
    check("changes_after_approve", len(ch2.json()) == 0)

    # 8) 小组件
    r = c.put("/api/auth/widgets", headers=H, json={"widgets": ["weak", "recent"]})
    check("widgets_save", r.json()["widgets"] == ["weak", "recent"])
    me = c.get("/api/auth/me", headers=H)
    check("widgets_in_me", me.json()["widgets"] == ["weak", "recent"])

    # 9) 备份 v2 往返（含档案库）
    exp = c.get("/api/data/export?scope=personal", headers=H)
    z = zipfile.ZipFile(io.BytesIO(exp.content))
    manifest = json.loads(z.read("manifest.json"))
    data = json.loads(z.read("data.json"))
    check("backup_v2", manifest["version"] == 2)
    check("backup_has_library", "library_items" in data and len(data["library_items"]) >= 1,
          str(list(data.keys())))
    imp = c.post("/api/data/import?scope=personal", headers=HU,
                 files={"file": ("b.zip", exp.content, "application/zip")})
    check("backup_v2_roundtrip", imp.json()["ok"] and imp.json()["counts"].get("library_items", 0) >= 1,
          str(imp.json())[:200])
    # v1 向下兼容：构造 v1 格式（无 library 表）导入
    v1 = {"wrong_questions": data.get("wrong_questions", [])}
    z2 = io.BytesIO()
    with zipfile.ZipFile(z2, "w") as zz:
        zz.writestr("manifest.json", json.dumps({"format": "ai-wrong-question-backup",
                                                 "version": 1, "kind": "personal"}))
        zz.writestr("data.json", json.dumps(v1))
    imp2 = c.post("/api/data/import?scope=personal", headers=HU,
                  files={"file": ("v1.zip", z2.getvalue(), "application/zip")})
    check("backup_v1_compat", imp2.json()["ok"], str(imp2.json())[:160])

    # 10) read_book_range / search_by_tags 技能
    from app.models import LibraryBook, LibraryPage, LibraryItem as LI
    bk = LibraryBook(user_id=u.id, subject="物理", kind="textbook", name="物理课本")
    db.add(bk)
    db.flush()
    for pn, txt in [(1, "第一页内容"), (2, "第二页内容")]:
        db.add(LibraryPage(user_id=u.id, book_id=bk.id, page_no=pn, ocr_text=txt,
                           ocr_status="done", image_path=""))
    # 自建带标签的条目（此前的备份导入为覆盖式，旧标签已清空）
    fresh = LI(user_id=u.id, subject="化学", kind="text", title="实验笔记",
               content="氧气制取", ocr_status="none", source="manual")
    db.add(fresh)
    db.flush()
    from app.services.pipeline import set_tags as _set_tags
    _set_tags(db, u, "library_item", fresh.id, {"source": "上传", "date": "2025-09-10"})
    db.commit()
    r = asyncio.run(execute_skill(db, u, {}, "read_book_range",
                                  {"book_id": bk.id, "from_page": 1, "to_page": 2}))
    check("read_book_range", "第一页内容" in r["data"]["text"] and "第二页内容" in r["data"]["text"])
    r = asyncio.run(execute_skill(db, u, {}, "search_by_tags",
                                  {"tags": {"source": "上传"}}))
    check("search_by_tags", r["summary"].startswith("标签检索到") and len(r["data"]) >= 1, r["summary"])
    db.close()


    # 11) 智学网整理：坏图修复 / 无效清理 / 去重 / 可撤销
    from app.models import LibraryItem as LZI
    # 无效条目（空内容无文件）
    junk = LZI(user_id=u.id, kind="text", title="暂无", content="", source="zhixuewang",
               ocr_status="none", item_date="2025-09-01")
    db.add(junk)
    # 坏图条目（文件缺失但有 source_url 可重下）
    bad = LZI(user_id=u.id, kind="image", title="坏图", file_path="u999_12345.jpg",
              source="zhixuewang", source_url="http://fake.local/fix.jpg",
              ocr_status="pending", item_date="2025-09-02")
    db.add(bad)
    # 重复条目
    d1 = LZI(user_id=u.id, kind="text", title="考试·月考", content="数学: 120",
             subject="数学", source="zhixuewang", item_date="2025-09-05", ocr_status="none")
    d2 = LZI(user_id=u.id, kind="text", title="考试·月考", content="数学: 120",
             subject="数学", source="zhixuewang", item_date="2025-09-05", ocr_status="none")
    db.add(d1)
    db.add(d2)
    # 无效错题（题干空无图）
    from app.models import WrongQuestion as WQ2
    empty_wq = WQ2(user_id=u.id, subject="数学", question_text="", images=[])
    db.add(empty_wq)
    db.commit()
    junk_id = junk.id
    bad_id = bad.id
    empty_wq_id = empty_wq.id
    dup_ids = sorted([d1.id, d2.id])

    r = c.post("/api/zhixue/tidy", headers=H)
    t = r.json()
    check("tidy_runs", r.status_code == 200 and t["ok"], str(t)[:200])
    check("tidy_junk_removed", t["junk_removed"] >= 2, str(t))
    check("tidy_dup_removed", t["dup_removed"] >= 1, str(t))
    check("tidy_image_fixed", t["images_fixed"] >= 1, str(t))
    remaining = db.query(LZI).filter(LZI.id.in_([junk_id, bad_id] + dup_ids)).all()
    remaining_ids = [x.id for x in remaining]
    check("tidy_effect", junk_id not in remaining_ids and dup_ids[0] not in remaining_ids,
          str(remaining_ids))
    fixed = db.query(LZI).filter(LZI.id == bad_id).first()
    check("tidy_image_now_exists", fixed is not None and fixed.file_path
          and (__import__('pathlib').Path(__import__('app.config', fromlist=['IMAGES_DIR']).IMAGES_DIR)
               / fixed.file_path.split('/')[-1]).exists(), str(fixed.file_path if fixed else None))

    # 撤销整理的删除（无效条目恢复）
    ch = c.get("/api/changes?source=&limit=50", headers=H)
    del_changes = [x for x in ch.json() if x["action"] == "delete" and x["target_type"] == "library"]
    if del_changes:
        cid = del_changes[0]["id"]
        c.post(f"/api/changes/{cid}/undo", headers=H)
        ch2 = c.get("/api/changes?limit=50", headers=H)
        undone = [x for x in ch2.json() if x["id"] == cid]
        check("tidy_undo", undone and undone[0]["undone"], str(undone)[:120])
    else:
        check("tidy_undo", False, "no delete change recorded")


    # 12) AI 深度整理：伪内容清洗 / 补解法 / 判无效（可撤销）
    from app.models import WrongQuestion as WQ3
    raw_q = WQ3(user_id=u.id, subject="数学", question_text="题目&nbsp;已知∠ADP＝90&deg;",
                correct_solution="略", wrong_reason="来自智学网错题本（卷）", images=[])
    junk_q = WQ3(user_id=u.id, subject="数学", question_text="垃圾内容 xx",
                 correct_solution="", images=[])
    db.add(raw_q)
    db.add(junk_q)
    db.commit()
    raw_id, junk_id2 = raw_q.id, junk_q.id

    r = c.post("/api/zhixue/tidy", headers=H, json={"ai": True})
    t = r.json()
    check("ai_tidy_runs", r.status_code == 200 and "ai_cleaned" in t, str(t)[:200])
    check("ai_tidy_cleaned", t["ai_cleaned"] >= 1 and t["ai_solutions_filled"] >= 1, str(t))
    check("ai_tidy_junk", t["ai_junk_removed"] >= 1, str(t))
    db.rollback()  # 结束旧读事务，避免 WAL 快照读到旧数据
    fixed_q = db.query(WQ3).filter(WQ3.id == raw_id).first()
    check("ai_tidy_solution_filled", fixed_q is not None and fixed_q.correct_solution
          and "略" not in fixed_q.correct_solution and "&deg;" not in (fixed_q.question_text or ""),
          f"sol={str(fixed_q.correct_solution[:60]) if fixed_q else None} stats_ok={'ai_cleaned' in t}")
    gone = db.query(WQ3).filter(WQ3.id == junk_id2).first()
    check("ai_tidy_junk_deleted", gone is None)
    # 撤销 AI 删除
    chx = c.get("/api/changes?limit=60", headers=H).json()
    dels = [x for x in chx if x["action"] == "delete" and x["target_type"] == "wrong_question"
            and x["skill"] == "zhixue_ai_tidy"]
    if dels:
        c.post(f"/api/changes/{dels[0]['id']}/undo", headers=H)
        back = db.query(WQ3).filter(WQ3.question_text.like("%垃圾%")).first()
        check("ai_tidy_undo", back is not None)
    else:
        check("ai_tidy_undo", False, "no ai delete change")

    failed = [n for n, o in ok if not o]
    print(f"\n=== {len(ok) - len(failed)}/{len(ok)} passed ===")
    sys.exit(1 if failed else 0)
finally:
    pass
