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
    elif "知识图谱整理员" in system and "重新完善" in system:
        answer = json.dumps({
            "name": "因式分解", "node_type": "knowledge", "confidence": "confirmed",
            "description": "把多项式化为乘积形式，是解方程的基础工具。",
            "children": [{"name": "十字相乘法"}, {"name": "公式法"}],
            "reason": "结合错题发现方法类子方向缺失"}, ensure_ascii=False)
    elif "知识图谱整理员" in system:
        answer = json.dumps({"proposals": [
            {"action": "add", "subject": "数学", "parent_name": "", "name": "因式分解",
             "node_type": "knowledge", "confidence": "suspected", "reason": "对话重点讨论",
             "children": [{"name": "十字相乘法", "node_type": "knowledge"},
                          {"name": "公式法", "node_type": "knowledge"}]},
            {"action": "add", "subject": "数学", "parent_name": "", "name": "符号错误",
             "node_type": "weakness", "confidence": "suspected", "reason": "学生两次提到符号问题"},
        ]}, ensure_ascii=False)
    elif "数据技能调用协议" in system:
        first_user = next((m.get("content") for m in body["messages"]
                           if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        rounds = sum(1 for m in body["messages"]
                     if m.get("role") == "user" and isinstance(m.get("content"), str)
                     and "[技能执行结果]" in m["content"])
        if "整理弱点" not in first_user:
            answer = "这是关于「" + text[:20] + "」的详细讲解。第一步…第二步…"
        elif rounds == 0:
            answer = json.dumps({"skill": "read_mindmap", "args": {"subject": "数学"}},
                                ensure_ascii=False)
        elif rounds == 1:
            answer = json.dumps({"skill": "update_node", "args": {
                "subject": "数学", "name": "因式分解", "confidence": "confirmed",
                "reason": "3 道错题印证"}}, ensure_ascii=False)
        else:
            answer = "已整理完成：把「因式分解」升级为已确认（依据 3 道错题）。变更可在变更卡中撤销。"
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
    uvicorn.run(mock, host="127.0.0.1", port=18901, log_level="error")


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
    "api_base_url": "http://127.0.0.1:18901/v1", "api_key": "sk-mock",
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

r = c.post("/api/wrong-questions/analyze", headers=H, json={
    "subject": "数学", "mode": "single", "text": "看图", "image_ids": [iid]})
item = r.json()["items"][0]
check("wq_image_saved", item.get("images") and item["images"][0].startswith("/api/images/"),
      str(item.get("images")))
check("wq_original_saved", bool(item.get("original_images")))

# 11. 图片任务跟随当前模型（v4 决策），且视觉请求携带图片
vision_calls = [m for m in CALLS
                if any(isinstance(msg.get("content"), list)
                       and any(p.get("type") == "image_url" for p in msg["content"])
                       for msg in m["messages"])]
check("vision_image_payload", len(vision_calls) >= 1, str(len(vision_calls)))
check("vision_follows_current_model", all(m.get("model") == "mock-chat" for m in vision_calls),
      str(set(m.get("model") for m in vision_calls)))

r = c.get(item["images"][0])
check("image_served", r.status_code == 200 and len(r.content) > 100)

# 13. 对话总结 → 节点提案 → 应用入库（v3 提问/图谱链路）
conv = c.post("/api/chat/conversations", headers=H,
              json={"title": "讨论因式分解", "subject": "数学", "grade": "初三"}).json()
c.post(f"/api/chat/conversations/{conv['id']}/messages", headers=H,
       json={"content": "因式分解怎么写", "image_ids": []})
r = c.post(f"/api/chat/conversations/{conv['id']}/summarize", headers=H, json={})
props = r.json().get("proposals", [])
check("summarize_proposals", r.status_code == 200 and len(props) >= 2, r.text[:200])
check("proposal_granularity", props[0]["name"] == "因式分解" and len(props[0].get("children") or []) == 2,
      str(props)[:200])
r = c.post("/api/knowledge/nodes/apply", headers=H, json={"proposals": props})
check("apply_summarized", len(r.json()["applied"]) >= 4, r.text[:200])
r = c.get("/api/knowledge/nodes?subject=数学", headers=H)
names = [n["name"] for n in r.json()]
check("nodes_in_graph", "因式分解" in names and "十字相乘法" in names and "符号错误" in names, str(names))

# 14. 节点 AI 重新总结
target = next(n for n in r.json() if n["name"] == "因式分解")
r = c.post(f"/api/knowledge/nodes/{target['id']}/resummarize", headers=H, json={})
check("node_resummarize", r.status_code == 200 and "乘积" in r.json()["description"], r.text[:200])
check("resummarize_children", r.json()["id"] == target["id"])

# 15. 多模型设置 + 会话模型
c.put("/api/settings/models", headers=H,
      json={"models": ["ma", "mb"], "assign": {"chat": "ma", "vision": "mb", "analysis": "ma"}})
r = c.put(f"/api/chat/conversations/{conv['id']}", headers=H, json={"model_name": "mb"})
check("conv_model_set", r.json()["model_name"] == "mb")
r = c.post(f"/api/chat/conversations/{conv['id']}/messages", headers=H,
           json={"content": "继续", "image_ids": [], "model": "mb"})
check("chat_model_override", "event: done" in r.text, r.text[:100])

# 16. 供应商体系（v4）：多供应商共存 + 模型切换
r = c.post("/api/providers", headers=H, json={
    "name": "xiaomi-mimo", "base_url": "http://127.0.0.1:18901/v1",
    "api_key": "sk-mimo", "models": ["mimo-a", "mimo-b"]})
check("provider_create", r.status_code == 200 and len(r.json()["models"]) == 2, r.text[:200])
pid = r.json()["id"]
r = c.post("/api/providers", headers=H, json={
    "name": "deepseek", "base_url": "http://127.0.0.1:18901/v1",
    "api_key": "sk-ds", "models": ["deepseek-chat"]})
pid2 = r.json()["id"]
r = c.get("/api/providers", headers=H)
check("providers_list", len(r.json()["providers"]) >= 2, r.text[:200])
r = c.put("/api/providers/current/model", headers=H, json={"model_ref": f"{pid}::mimo-a"})
check("current_model_set", r.status_code == 200)
conv3 = c.post("/api/chat/conversations", headers=H, json={"title": "switch", "subject": "数学"}).json()
c.post(f"/api/chat/conversations/{conv3['id']}/messages", headers=H,
       json={"content": "hi", "image_ids": []})
last_call = [m for m in CALLS if m.get("stream")][-1]
check("chat_uses_selected_model", last_call.get("model") == "mimo-a", str(last_call.get("model")))
c.put(f"/api/chat/conversations/{conv3['id']}", headers=H,
      json={"model_name": f"{pid2}::deepseek-chat"})
c.post(f"/api/chat/conversations/{conv3['id']}/messages", headers=H,
       json={"content": "hi2", "image_ids": []})
last_call = [m for m in CALLS if m.get("stream")][-1]
check("conv_model_switch", last_call.get("model") == "deepseek-chat", str(last_call.get("model")))

# 17. Skill 调用循环：读技能 → 写技能 → 最终回答
skill_conv = c.post("/api/chat/conversations", headers=H,
                    json={"title": "整理弱点", "subject": "数学", "grade": "初三"}).json()
r = c.post(f"/api/chat/conversations/{skill_conv['id']}/messages", headers=H,
           json={"content": "帮我整理弱点并升级因式分解", "image_ids": []})
body = r.text
check("skill_event", "event: skill" in body, body[:300])
check("skill_read_round", "read_mindmap" in body)
check("skill_write_round", "update_node" in body)
check("change_event", "event: change" in body)
check("skill_final_text", "已整理完成" in body)

# 18. 变更记录 + 撤销
r = c.get("/api/changes", headers=H)
changes = r.json()
check("change_log", len(changes) >= 1 and bool(changes[0]["description"]), str(changes[:1]))
cid_change = changes[0]["id"]
r = c.post(f"/api/changes/{cid_change}/undo", headers=H)
check("change_undo", r.status_code == 200, r.text[:200])
r = c.get("/api/changes", headers=H)
check("undo_marked", any(x["id"] == cid_change and x["undone"] for x in r.json()))

# 19. 导出 / 导入（覆盖式，个人范围）
exp = c.get("/api/data/export?scope=personal", headers=H)
check("export_zip", exp.status_code == 200 and exp.content[:2] == b"PK", str(exp.status_code))
import io as _io
import zipfile as _zipfile
z = _zipfile.ZipFile(_io.BytesIO(exp.content))
check("export_manifest", "manifest.json" in z.namelist() and "data.json" in z.namelist())
manifest = json.loads(z.read("manifest.json"))
check("export_version", manifest["version"] == 1 and manifest["kind"] == "personal", str(manifest))
r = c.post("/api/data/import?scope=personal", headers=H,
           files={"file": ("backup.zip", exp.content, "application/zip")})
check("import_ok", r.status_code == 200 and r.json()["ok"], r.text[:300])
check("import_counts", r.json()["counts"].get("wrong_questions", 0) >= 1, r.text[:300])
r = c.get("/api/wrong-questions", headers=H)
check("import_roundtrip", r.json()["total"] >= 1)


# 20. 对话摘要（独立 Agent，不进消息流）
sum_conv = c.post("/api/chat/conversations", headers=H,
                  json={"title": "summary-conv", "subject": "数学"}).json()
c.post(f"/api/chat/conversations/{sum_conv['id']}/messages", headers=H,
       json={"content": "因式分解怎么写", "image_ids": []})
r = c.post(f"/api/chat/conversations/{sum_conv['id']}/summary", headers=H, json={})
check("summary_generate", r.status_code == 200 and bool(r.json()["content"]), r.text[:200])
r2 = c.get(f"/api/chat/conversations/{sum_conv['id']}/summaries", headers=H)
check("summary_list", len(r2.json()) == 1)
hist = c.get(f"/api/chat/conversations/{sum_conv['id']}", headers=H)
check("summary_not_in_messages", all("学习记录整理员" not in (m.get("content") or "") for m in hist.json()["messages"]))

# 21. 夜间整理设置 + 手动触发
r = c.put("/api/settings/nightly", headers=H, json={"nightly_time": "22:30", "nightly_enabled": True})
check("nightly_settings", r.status_code == 200)
r = c.get("/api/settings/nightly", headers=H)
check("nightly_get", r.json()["nightly_time"] == "22:30")
r = c.post("/api/library/nightly/run", headers=H, json={})
check("nightly_run", r.status_code == 200 and r.json()["ok"], r.text[:200])

# 22. 复习资料生成
r = c.post("/api/library/review/generate", headers=H,
           json={"subject": "数学", "focus": "期中复习", "days": 14})
check("review_generate", r.status_code == 200 and bool(r.json().get("data")), r.text[:200])
items = c.get("/api/library/items?kind=review", headers=H)
check("review_in_library", items.json()["total"] >= 1)


# 23. 全局搜索（需求 23）：普通 + AI 高级
r = c.get("/api/search?q=" + "因式分解", headers=H)
gs = r.json()
check("search_unified", "wrong_questions" in gs and "library" in gs
      and "nodes" in gs and "conversations" in gs, str(list(gs.keys())))
total_hits = sum(len(v) for k, v in gs.items() if isinstance(v, list))
check("search_hits", total_hits >= 1, str(total_hits))
r = c.post("/api/search/ai", headers=H, json={"q": "因式分解以前出现过吗", "subject": "数学"})
check("search_ai", r.status_code == 200 and bool(r.json()["answer"]), r.text[:200])

failed = [n for n, o in ok if not o]
print(f"\n=== {len(ok) - len(failed)}/{len(ok)} passed ===")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
