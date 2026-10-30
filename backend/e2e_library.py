"""档案库 E2E：书本/板块/条目/搜索/书签/下载/错题自动归档。"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

PORT = 8051
BASE = f"http://127.0.0.1:{PORT}"
DATA_DIR = tempfile.mkdtemp(prefix="st_lib_")
env = {**os.environ, "DATA_DIR": DATA_DIR}
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)

ok = []


def check(name, cond, extra=""):
    ok.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")


def req(path, method="GET", body=None, token=None):
    if "?" in path:
        base, qs = path.split("?", 1)
        pairs = urllib.parse.parse_qsl(qs, keep_blank_values=True)
        path = base + "?" + urllib.parse.urlencode(pairs, quote_via=urllib.parse.quote)
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def multipart(path, fields, files, token):
    if "?" in path:
        base, qs = path.split("?", 1)
        pairs = urllib.parse.parse_qsl(qs, keep_blank_values=True)
        path = base + "?" + urllib.parse.urlencode(pairs, quote_via=urllib.parse.quote)
    boundary = "----stlib"
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, (fname, content, ctype) in files.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
            + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    r = urllib.request.Request(BASE + path, data=body, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


try:
    setup = req("/api/auth/setup", "POST",
                {"username": "lib", "password": "123456", "display_name": "lib", "grade": "初三"})
    H = setup["access_token"]

    # 书本
    book = req("/api/library/books", "POST",
               {"name": "物理八年级上", "subject": "物理", "kind": "textbook"}, H)
    check("book_create", book["id"] > 0 and book["kind"] == "textbook", str(book))
    ov = req("/api/library/overview", token=H)
    check("overview_books", ov["counts"]["textbook"] == 1, str(ov["counts"]))

    # 页面（真实 JPEG）
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (220, 230, 255)).save(buf, format="JPEG")
    res = multipart(f"/api/library/books/{book['id']}/pages?page_no=1",
                    {}, {"file": ("p1.jpg", buf.getvalue(), "image/jpeg")}, H)
    check("book_page", res.get("page_no") == 1, str(res))
    pages = req(f"/api/library/books/{book['id']}/pages", token=H)
    check("book_pages_sorted", pages["pages"][0]["page_no"] == 1, str(pages))

    # 板块 + 模板分板块
    board = req("/api/library/boards", "POST", {"name": "第一次物理作业", "subject": "物理"}, H)
    check("board_create", board["id"] > 0)
    t = req(f"/api/library/boards/{board['id']}/templates", "POST", {}, H)
    check("board_templates", len(t["created"]) == 5, str(t))
    bl = req("/api/library/boards?subject=物理", token=H)
    check("board_tree", any(b["parent_id"] == board["id"] for b in bl))

    # 图片上传入库 + 挂板块
    buf2 = io.BytesIO()
    Image.new("RGB", (300, 200), (255, 230, 220)).save(buf2, format="JPEG")
    up = multipart("/api/library/items/upload?subject=物理&kind=image&board_id=" + str(board["id"]),
                   {}, {"files": ("hw1.jpg", buf2.getvalue(), "image/jpeg")}, H)
    item_id = up["items"][0]["id"]
    check("item_upload", up["items"][0]["board_id"] == board["id"], str(up)[:200])

    # 文字录入
    txt = req("/api/library/items/text", "POST",
              {"title": "课堂笔记", "content": "牛顿第一定律：一切物体在没有受到力的作用时…", "subject": "物理"}, H)
    check("text_item", txt["kind"] == "text")

    # 附件（txt 提取文字）
    att = multipart("/api/library/items/upload?subject=物理&kind=attachment", {},
                    {"files": ("answer.txt", "答案：B\n解析：略".encode(), "text/plain")}, H)
    att_id = att["items"][0]["id"]
    check("attachment_upload", att["items"][0]["kind"] == "attachment"
          and "答案" in att["items"][0]["content"], str(att)[:200])
    lk = req(f"/api/library/items/{att_id}/link", "POST", {"board_id": board["id"]}, H)
    check("attachment_link", lk["ok"])

    # 搜索（基础索引：正文/OCR/标题）
    s = req("/api/library/items?q=" + urllib.parse.quote("牛顿"), token=H)
    check("search_text", any("课堂笔记" in it["title"] for it in s["items"]), str(s)[:200])
    s2 = req("/api/library/items?kind=attachment", token=H)
    check("search_filter_kind", s2["total"] == 1, str(s2["total"]))

    # 书签
    bm = req("/api/library/bookmarks", "POST",
             {"target_type": "library_item", "target_id": item_id, "label": "重点作业"}, H)
    check("bookmark_create", bm["id"] > 0)
    bl2 = req("/api/library/bookmarks", token=H)
    check("bookmark_list", len(bl2) == 1)

    # 下载
    with urllib.request.urlopen(urllib.request.Request(
            BASE + f"/api/library/items/{att_id}/download",
            headers={"Authorization": "Bearer " + H}), timeout=30) as r2:
        dl = r2.read()
    check("download", "答案".encode("utf-8") in dl)

    # 错题自动归档：直接调分析接口需要 AI——改为校验 analyze 后归档逻辑已存在（mock_ai_test 覆盖）
    # 这里校验 items 接口对 wrong_question kind 的检索
    s3 = req("/api/library/items?kind=wrong_question", token=H)
    check("wrong_q_slot_ready", s3["total"] == 0)

    failed = [n for n, o in ok if not o]
    print(f"\n=== {len(ok) - len(failed)}/{len(ok)} passed ===")
    sys.exit(1 if failed else 0)
finally:
    proc.terminate()
