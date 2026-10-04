"""AI 管线端到端测试：mock OpenAI 兼容服务 → 分析/对话/进度/目标/报告。"""
import json
import os
import sys
import tempfile
import threading

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="st_ai_")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ---------- mock AI ----------
mock = FastAPI()
CALLS = []


@mock.post("/v1/chat/completions")
async def chat_completions(req: Request):
    body = await req.json()
    CALLS.append(body)
    system = body["messages"][0]["content"]
    user_last = body["messages"][-1]["content"]
    text = user_last if isinstance(user_last, str) else json.dumps(user_last, ensure_ascii=False)

    if "错题分析导师" in system:
        answer = json.dumps({
            "question_text": "解方程 x^2-5x+6=0",
            "subject": "数学", "unit": "一元二次方程",
            "knowledge_points": ["因式分解"], "difficulty": "中等",
            "wrong_reason": "因式分解时符号弄反了",
            "correct_solution": "1. 因式分解 (x-2)(x-3)=0\n2. 得 x=2 或 x=3",
            "key_points": ["注意符号"], "extensions": "变式：x^2-5x+k=0 有整数根",
            "learning_content": "一元二次方程的因式分解解法",
            "method": {"specific": "先判别式", "general": "解方程先化标准型"},
        }, ensure_ascii=False)
    elif "逐题识别" in system:
        answer = json.dumps([
            {"question_text": "题1", "unit": "u", "knowledge_points": ["k1"],
             "wrong_reason": "r1", "correct_solution": "s1"},
            {"question_text": "题2", "unit": "u", "knowledge_points": ["k2"],
             "wrong_reason": "r2", "correct_solution": "s2"},
        ], ensure_ascii=False)
    elif "学习档案管理员" in system:
        answer = "薄弱点：因式分解符号易错；建议强化基础训练。"
    elif "进度识别" in system or "正在学习什么" in system or "正在学习什么" in text:
        answer = json.dumps({
            "learning_items": [{"knowledge_point": "一元二次方程", "unit": "一元二次方程",
                                "learning_state": "learning", "evidence": "作业多为该章节"}],
            "summary": "正在学习一元二次方程解法"}, ensure_ascii=False)
    elif "刷题规划师" in system:
        answer = json.dumps([{"subject": "数学", "title": "专攻因式分解",
                              "question_type": "因式分解", "description": "每天10题",
                              "reason": "错题集中", "due_date": "本周日"}], ensure_ascii=False)
    elif "答题方法教练" in system:
        answer = json.dumps({"specific_method": "本题先看设问",
                             "general_method": "是什么-为什么-怎么做",
                             "knowledge_point": "材料题", "question_type": "材料分析"}, ensure_ascii=False)
    elif "学习分析师" in system:
        answer = "# 学习报告\n- 本周错题集中在因式分解\n- 下一步：每天10题"
    else:
        answer = "这是关于「" + text[:20] + "」的详细讲解。第一步…第二步…"

    if body.get("stream"):
        async def gen():
            for ch in [answer[i:i + 8] for i in range(0, len(answer), 8)]:
                yield f'data: {json.dumps({"choices": [{"delta": {"content": ch}}]}, ensure_ascii=False)}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return {"choices": [{"message": {"content": answer}}]}


def run_mock():
    uvicorn.run(mock, host="127.0.0.1", port=8901, log_level="error")


threading.Thread(target=run_mock, daemon=True).start()
import time  # noqa: E402
time.sleep(1.2)

# ---------- 被测应用 ----------
from app.main import app  # noqa: E402

c = TestClient(app)
ok = []


def check(name, cond, extra=""):
    ok.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")


r = c.post("/api/auth/setup", json={"username": "admin", "password": "123456", "display_name": "我"})
H = {"Authorization": f"Bearer {r.json()['access_token']}"}
c.put("/api/settings/global", headers=H, json={
    "api_base_url": "http://127.0.0.1:8901/v1", "api_key": "sk-mock",
    "chat_model": "mock-chat", "vision_model": "mock-vision",
    "temperature": 0.5, "system_extra_prompt": "extra-hint"})

# 1. 单题分析（文本）
r = c.post("/api/wrong-questions/analyze", headers=H, json={
    "subject": "数学", "mode": "single", "text": "我做错了 x^2-5x+6=0",
    "my_question": "为什么因式分解"})
body = r.json()
check("analyze_single", r.status_code == 200, r.text[:300])
items = body.get("items", [])
check("analyze_parsed", items and items[0]["knowledge_points"] == ["因式分解"], str(items)[:200])
check("analyze_mastery", items[0]["mastery"] == "weak")

# 2. 档案已由分析触发更新
r = c.get("/api/profile", headers=H)
check("profile_auto_updated", r.json() and "因式分解" in r.json()[0]["content"], str(r.json())[:200])

# 3. 批量多题
r = c.post("/api/wrong-questions/analyze", headers=H, json={
    "subject": "数学", "mode": "batch", "text": "一整页"})
check("analyze_batch", r.status_code == 200 and len(r.json()["items"]) == 2, r.text[:200])

# 4. 图谱：知识点入图
r = c.get("/api/knowledge/mindmap?subject=数学", headers=H)
labels = [n["label"] for n in r.json()["nodes"]]
check("mindmap_has_kp", "因式分解" in labels, str(labels))
check("mindmap_mastery_weak", any(n.get("mastery") == "weak" and n["label"] == "因式分解"
                                  for n in r.json()["nodes"]))

# 5. 对话流式（含上下文注入）
r = c.post("/api/chat/conversations", headers=H, json={"title": "t", "subject": "数学", "grade": "初三"})
cid = r.json()["id"]
r = c.post(f"/api/chat/conversations/{cid}/messages", headers=H,
           json={"content": "给我讲讲因式分解", "image_ids": []})
check("chat_stream_ok", "event: done" in r.text and "event: error" not in r.text, r.text[:300])
r = c.get(f"/api/chat/conversations/{cid}", headers=H)
check("chat_delta", "详细讲解" in r.json()["messages"][-1]["content"],
      r.json()["messages"][-1]["content"][:100])
sys_prompt = [m for m in CALLS if m.get("stream")][-1]["messages"][0]["content"]
check("chat_injects_profile", "薄弱点" in sys_prompt or "档案" in sys_prompt, sys_prompt[:200])
check("chat_injects_extra", "extra-hint" in sys_prompt)
r = c.get(f"/api/chat/conversations/{cid}", headers=H)
check("chat_saved", len(r.json()["messages"]) == 2)

# 6. 知识点深聊会话
r = c.post("/api/chat/conversations", headers=H, json={
    "title": "深聊", "subject": "数学", "context_kind": "knowledge", "context_ref": "因式分解"})
cid2 = r.json()["id"]
r = c.post(f"/api/chat/conversations/{cid2}/messages", headers=H,
           json={"content": "概念是什么", "image_ids": []})
check("kp_chat_ok", "event: done" in r.text, r.text[:200])
sys_prompt = [m for m in CALLS if m.get("stream")][-1]["messages"][0]["content"]
check("kp_chat_context", "因式分解" in sys_prompt and "知识点" in sys_prompt)

# 7. 作业扫描 → 进度（真实 JPEG）
import io  # noqa: E402
from PIL import Image  # noqa: E402

buf = io.BytesIO()
Image.new("RGB", (320, 240), (200, 210, 255)).save(buf, format="JPEG")
r = c.post("/api/wrong-questions/upload", headers=H,
           files=[("files", ("h.jpg", buf.getvalue(), "image/jpeg"))])
check("upload_ok", r.status_code == 200 and r.json().get("image_ids"), r.text[:200])
iid = r.json()["image_ids"][0]
r = c.post("/api/knowledge/scan-homework", headers=H,
           json={"subject": "数学", "image_ids": [iid]})
check("scan_homework", r.status_code == 200 and "一元二次方程" in r.json()["summary"], r.text[:200])
r = c.get("/api/knowledge/progress", headers=H)
check("progress_learning", "一元二次方程" in json.dumps(r.json(), ensure_ascii=False))

# 8. 刷题目标生成
r = c.post("/api/goals/generate", headers=H, json={"subject": "数学"})
check("goals_generate", r.status_code == 200 and r.json()["items"][0]["title"] == "专攻因式分解", r.text[:200])

# 9. 方法总结
r = c.post("/api/methods/summarize", headers=H, json={
    "subject": "道德与法治", "question": "材料：某地发展经济… 请分析原因"})
check("method_summarize", r.status_code == 200 and "是什么" in r.json()["general_method"], r.text[:200])
r = c.get("/api/methods", headers=H)
check("method_saved", len(r.json()) >= 1)

# 10. 学习报告
r = c.post("/api/reports/generate", headers=H, json={})
check("report_generate", r.status_code == 200 and "学习报告" in r.json()["content"], r.text[:200])

# 11. 视觉模型被调用（分析用 vision_model）
vision_calls = [m for m in CALLS if m.get("model") == "mock-vision"]
check("vision_model_used", len(vision_calls) >= 2, str(len(vision_calls)))

# 12. 图片以 base64 进入视觉请求 + 错题记录图片引用
has_image_url = any(
    isinstance(m.get("content"), list)
    and any(p.get("type") == "image_url" for p in m["content"])
    for call in vision_calls for m in call["messages"]
)
check("vision_image_payload", has_image_url)
r = c.post("/api/wrong-questions/analyze", headers=H, json={
    "subject": "数学", "mode": "single", "text": "看图", "image_ids": [iid]})
item = r.json()["items"][0]
check("wq_image_saved", item.get("images") and item["images"][0].startswith("/api/images/"),
      str(item.get("images")))
r = c.get(item["images"][0])
check("image_served", r.status_code == 200 and len(r.content) > 100)

failed = [n for n, o in ok if not o]
print(f"\n=== {len(ok) - len(failed)}/{len(ok)} passed ===")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
