"""接口冒烟测试：初始化、登录、设置、错题 CRUD、图谱、对话。"""
import os
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="st_test_")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")


# 1. health + setup
check("health", c.get("/api/health").json().get("ok") is True)
check("need_setup", c.get("/api/auth/status").json()["need_setup"] is True)
r = c.post("/api/auth/setup", json={"username": "admin", "password": "123456",
                                    "display_name": "管理员", "grade": "初三"})
check("setup", r.status_code == 200, r.text[:200])
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
check("setup_grade_saved", r.json()["user"]["grade"] == "初三", r.text[:200])

# 1.5 开放注册（学生/家长）
r = c.post("/api/auth/register", json={"username": "stu1", "password": "123456",
                                       "grade": "初三", "role": "student"})
check("register_student", r.status_code == 200 and r.json()["user"]["grade"] == "初三", r.text[:200])
r = c.post("/api/auth/register", json={"username": "parent1", "password": "123456",
                                       "grade": "高一", "role": "parent"})
check("register_parent", r.status_code == 200 and r.json()["user"]["identity"] == "家长", r.text[:200])
r = c.post("/api/auth/register", json={"username": "stu1", "password": "123456", "role": "student"})
check("register_dup_rejected", r.status_code == 400, r.text[:200])

# 2. settings
r = c.get("/api/settings", headers=H)
check("settings_get", r.status_code == 200 and "effective" in r.json(), r.text[:200])
r = c.put("/api/settings/global", headers=H, json={
    "api_base_url": "https://api.example.com/v1", "api_key": "sk-test-1234567890",
    "chat_model": "demo-chat", "vision_model": "demo-vision", "temperature": 0.5,
    "system_extra_prompt": "extra"})
check("settings_put", r.status_code == 200, r.text[:200])
r = c.get("/api/settings", headers=H)
check("key_masked", "sk-t" in r.json()["global"]["api_key_masked"], r.text[:200])

# 3. users
r = c.post("/api/auth/users", headers=H, json={"username": "stu2", "password": "123456", "grade": "初三"})
check("create_user", r.status_code == 200, r.text[:200])
r2 = c.post("/api/auth/login", json={"username": "stu1", "password": "123456"})
check("login_user", r2.status_code == 200, r2.text[:200])
H2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}

# 4. wrong question CRUD（写入后查询）
from app.database import SessionLocal  # noqa: E402
from app.models import WrongQuestion  # noqa: E402
db = SessionLocal()
wq = WrongQuestion(user_id=2, subject="数学", grade="初三", unit="一元二次方程",
                   knowledge_points=["因式分解", "配方法"], difficulty="中等",
                   question_text="解方程 x^2-5x+6=0", wrong_reason="因式分解符号错误",
                   correct_solution="(x-2)(x-3)=0", mastery="weak")
db.add(wq)
db.commit()
db.close()

r = c.get("/api/wrong-questions", headers=H2)
check("list_wq", r.status_code == 200 and r.json()["total"] == 1, r.text[:200])
wid = r.json()["items"][0]["id"]
r = c.get(f"/api/wrong-questions/{wid}", headers=H2)
check("get_wq", r.json()["question_text"].startswith("解方程"))
r = c.put(f"/api/wrong-questions/{wid}", headers=H2, json={"is_reviewed": True, "mastery": "improving"})
check("update_wq", r.json()["is_reviewed"] is True)

# 5. 知识点触达 + 图谱 + 进度
from app.services.knowledge import touch_knowledge, build_mindmap, progress_summary  # noqa: E402
from app.models import User  # noqa: E402
db = SessionLocal()
u = db.query(User).filter(User.username == "stu1").first()
touch_knowledge(db, u, "数学", ["因式分解", "配方法"], unit="一元二次方程")
touch_knowledge(db, u, "数学", ["不等式"], unit="不等式")
mp = build_mindmap(db, u, "数学")
db.close()
check("mindmap_nodes", len(mp["nodes"]) >= 4, str(len(mp["nodes"])))
check("mindmap_has_kp", any(n["kind"] == "kp" for n in mp["nodes"]))
r = c.get("/api/knowledge/mindmap?subject=数学", headers=H2)
check("mindmap_api", r.status_code == 200 and len(r.json()["nodes"]) >= 4)
r = c.get("/api/knowledge/progress", headers=H2)
check("progress_api", r.status_code == 200 and "数学" in r.json())

# 6. 对话创建 + 消息历史（无真实 AI Key，验证 502 路径与错误处理）
r = c.post("/api/chat/conversations", headers=H2,
           json={"title": "测试", "subject": "数学", "grade": "初三"})
check("create_conv", r.status_code == 200, r.text[:200])
cid = r.json()["id"]
r = c.post(f"/api/chat/conversations/{cid}/messages", headers=H2,
           json={"content": "你好", "image_ids": []})
body = r.text
check("chat_stream_errors_gracefully", r.status_code == 200 and ("event: error" in body or "event: done" in body), body[:300])
r = c.get(f"/api/chat/conversations/{cid}", headers=H2)
check("conv_history_saved", len(r.json()["messages"]) >= 1)

# 7. 档案 / 方法 / 目标 / 报告 CRUD（无 AI 部分）
r = c.post("/api/profile", headers=H2, json={"subject": "数学", "content": "薄弱：因式分解"})
check("profile_upsert", r.status_code == 200)
r = c.get("/api/profile", headers=H2)
check("profile_get", r.json()[0]["content"].startswith("薄弱"))
r = c.post("/api/methods", headers=H2, json={"subject": "历史", "knowledge_point": "材料题",
                                             "specific_method": "分层概括", "general_method": "是什么-为什么-怎么做"})
check("method_create", r.status_code == 200)
r = c.get("/api/methods", headers=H2)
check("method_list", len(r.json()) == 1)
r = c.post("/api/goals", headers=H2, json={"subject": "数学", "title": "专攻因式分解",
                                           "question_type": "因式分解", "description": "每天5题"})
check("goal_create", r.status_code == 200)
r = c.put(f"/api/goals/{r.json()['id']}", headers=H2, json={"status": "done"})
check("goal_update", r.status_code == 200)

# 8. 权限：普通用户不可改全局设置
r = c.put("/api/settings/global", headers=H2, json={"api_base_url": "x", "api_key": "y",
                                                    "chat_model": "z", "vision_model": "",
                                                    "temperature": 0.5, "system_extra_prompt": ""})
check("non_admin_forbidden", r.status_code == 403)

# 9. SPA 静态托管
r = c.get("/")
check("spa_index", r.status_code == 200 and "root" in r.text)

failed = [n for n, ok, _ in results if not ok]
print(f"\n=== {len(results) - len(failed)}/{len(results)} passed ===")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
