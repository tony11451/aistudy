"""v4 真实 HTTP 抽验：供应商切换 + 整机导出 + 变更日志。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 8041
BASE = f"http://127.0.0.1:{PORT}"
env = {**os.environ, "DATA_DIR": tempfile.mkdtemp(prefix="st_v4_")}
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)


def req(path, method="GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


try:
    setup = req("/api/auth/setup", "POST",
                {"username": "a", "password": "123456", "display_name": "a", "grade": "初三"})
    H = setup["access_token"]
    p1 = req("/api/providers", "POST",
             {"name": "xiaomi-mimo", "base_url": "http://x/v1", "api_key": "sk-m",
              "models": ["mimo-a", "mimo-b"]}, H)
    p2 = req("/api/providers", "POST",
             {"name": "deepseek", "base_url": "http://y/v1", "api_key": "sk-d",
              "models": ["deepseek-chat"]}, H)
    lst = req("/api/providers", token=H)
    names = [p["name"] for p in lst["providers"]]
    assert names == ["xiaomi-mimo", "deepseek"], names
    # key 不回明文：掩码存在且原始 key 不出现
    assert lst["providers"][0]["has_key"] and lst["providers"][0]["api_key_masked"], lst["providers"][0]
    assert "sk-m" not in json.dumps(lst), "api_key 不应明文回显"
    print("PASS providers_list", names)

    ref = f"{p2['id']}::deepseek-chat"
    req("/api/providers/current/model", "PUT", {"model_ref": ref}, H)
    lst = req("/api/providers", token=H)
    assert lst["current_model_ref"] == ref, lst["current_model_ref"]
    print("PASS current_model_switch", lst["current_model_ref"])

    exp = urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/data/export?scope=full",
        headers={"Authorization": "Bearer " + H}), timeout=30).read()
    assert exp[:2] == b"PK" and len(exp) > 500
    print("PASS full_export", len(exp), "bytes")

    exp2 = urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/data/export?scope=personal",
        headers={"Authorization": "Bearer " + H}), timeout=30).read()
    boundary = b"----stbound"
    body = b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"b.zip\"\r\nContent-Type: application/zip\r\n\r\n" + exp2 + b"\r\n--" + boundary + b"--\r\n"
    r = urllib.request.Request(BASE + "/api/data/import?scope=personal", data=body, method="POST")
    r.add_header("Content-Type", "multipart/form-data; boundary=" + boundary.decode())
    r.add_header("Authorization", "Bearer " + H)
    with urllib.request.urlopen(r, timeout=30) as resp:
        res = json.loads(resp.read().decode())
    assert res["ok"], res
    print("PASS import_overwrite", res.get("counts"))

    ch = req("/api/changes", token=H)
    assert isinstance(ch, list)
    print("PASS changes_api", len(ch))
    print("=== ALL OK ===")
finally:
    proc.terminate()
