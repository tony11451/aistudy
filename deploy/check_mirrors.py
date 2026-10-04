"""测试各 Docker 加速源是否支持匿名拉取 python:3.12-slim。"""
import json
import urllib.request

ACCEPT = ("application/vnd.docker.distribution.manifest.list.v2+json, "
          "application/vnd.docker.distribution.manifest.v2+json, "
          "application/vnd.oci.image.index.v1+json")


def check(host: str) -> str:
    url = f"https://{host}/v2/library/python/manifests/3.12-slim"
    req = urllib.request.Request(url, headers={"Accept": ACCEPT})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return f"{host}: DIRECT OK {r.status}"
    except urllib.error.HTTPError as e:
        auth = e.headers.get("WWW-Authenticate", "")
        if e.code != 401 or "Bearer" not in auth:
            return f"{host}: FAIL {e.code} {auth[:80]}"
        realm = auth.split('realm="')[1].split('"')[0]
        try:
            svc = auth.split('service="')[1].split('"')[0]
        except IndexError:
            svc = ""
        sep = "&" if "?" in realm else "?"
        turl = f"{realm}{sep}service={svc}&scope=repository:library/python:pull"
        try:
            tok = json.load(urllib.request.urlopen(turl, timeout=15)).get("token", "")
            req2 = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok,
                                                        "Accept": ACCEPT})
            r2 = urllib.request.urlopen(req2, timeout=15)
            return f"{host}: ANON PULL OK {r2.status}"
        except Exception as e2:
            return f"{host}: TOKEN FAIL {e2}"
    except Exception as e:
        return f"{host}: ERROR {e}"


for h in ["docker.1ms.run", "docker.m.daocloud.io", "dockerproxy.net",
          "docker.1panel.live", "docker.fnnas.com"]:
    print(check(h), flush=True)
