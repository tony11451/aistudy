"""v3 E2E：真实 HTTP 全链路（模型/学科/节点树/位置持久化/筛选）。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

PORT = 18021
BASE = f"http://127.0.0.1:{PORT}"
DATA_DIR = tempfile.mkdtemp(prefix="st_e2e_")


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


env = {**os.environ, "DATA_DIR": DATA_DIR}
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
try:
    ok = []
    def check(name, cond, extra=""):
        ok.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), name, extra if not cond else "")

    setup = req("/api/auth/setup", "POST", {"username": "admin", "password": "123456",
                                            "display_name": "管理员", "grade": "初三"})
    H = setup["access_token"]
    req("/api/settings/models", "PUT", {"models": ["ma", "mb"],
        "assign": {"chat": "ma", "vision": "mb", "analysis": "ma"}}, H)
    s = req("/api/settings", token=H)
    check("models_list", s["models"] == ["ma", "mb"] and s["assign"]["chat"] == "ma", str(s.get("models")))
    req("/api/settings/subjects", "PUT", {"subjects": ["语文", "数学", "英语"]}, H)
    s = req("/api/settings", token=H)
    check("subjects_custom", s["subjects"] == ["语文", "数学", "英语"])

    n1 = req("/api/knowledge/nodes", "POST", {"subject": "数学", "name": "因式分解"}, H)
    n2 = req("/api/knowledge/nodes", "POST",
             {"subject": "数学", "name": "十字相乘法", "parent_id": n1["id"]}, H)
    check("node_tree", n2["parent_id"] == n1["id"])
    mp = req("/api/knowledge/mindmap?subject=数学", token=H)
    check("mindmap", len(mp["nodes"]) >= 3 and len(mp["edges"]) >= 2,
          f"nodes={len(mp['nodes'])} edges={len(mp['edges'])}")
    check("mindmap_hierarchy", any(e["source"] == f"n{n1['id']}" for e in mp["edges"]))

    req("/api/knowledge/nodes/positions", "POST",
        {"positions": [{"id": n1["id"], "x": 123, "y": 456}]}, H)
    nodes = req("/api/knowledge/nodes?subject=数学", token=H)
    t = [n for n in nodes if n["id"] == n1["id"]][0]
    check("positions_persisted", t["pos_x"] == 123 and t["pos_y"] == 456, str(t["pos_x"]))

    req("/api/knowledge/nodes", "POST",
        {"subject": "数学", "name": "符号错误", "node_type": "weakness"}, H)
    mp_w = req("/api/knowledge/mindmap?subject=数学&kind=weakness", token=H)
    labels = [n["label"] for n in mp_w["nodes"]]
    check("filter_weakness", "符号错误" in labels and "因式分解" not in labels, str(labels))

    req("/api/knowledge/nodes/%d/resummarize" % n1["id"], "POST", {}, H) if False else None
    # 级联删除
    req(f"/api/knowledge/nodes/{n1['id']}", "DELETE", None, H)
    nodes = req("/api/knowledge/nodes?subject=数学", token=H)
    names = [n["name"] for n in nodes]
    check("cascade_delete", "因式分解" not in names and "十字相乘法" not in names, str(names))

    # 会话模型
    conv = req("/api/chat/conversations", "POST", {"title": "t", "subject": "数学"}, H)
    c2 = req(f"/api/chat/conversations/{conv['id']}", "PUT", {"model_name": "mb"}, H)
    check("conv_model", c2["model_name"] == "mb")

    # 前端构建产物
    spa = urllib.request.urlopen(BASE + "/").read().decode()
    check("spa", "root" in spa)

    failed = [n for n, o in ok if not o]
    print(f"\n=== {len(ok)-len(failed)}/{len(ok)} passed ===")
    sys.exit(1 if failed else 0)
finally:
    proc.terminate()
