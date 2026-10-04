"""确认 docker.1ms.run 上 node/python 基础镜像可匿名拉取。"""
import json
import urllib.request

ACCEPT = ("application/vnd.docker.distribution.manifest.list.v2+json, "
          "application/vnd.oci.image.index.v1+json")


def check_image(host: str, repo: str, tag: str) -> str:
    url = f"https://{host}/v2/library/{repo}/manifests/{tag}"
    req = urllib.request.Request(url, headers={"Accept": ACCEPT})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return f"{host} {repo}:{tag} -> DIRECT OK {r.status}"
    except urllib.error.HTTPError as e:
        auth = e.headers.get("WWW-Authenticate", "")
        realm = auth.split('realm="')[1].split('"')[0]
        svc = auth.split('service="')[1].split('"')[0]
        tok_url = f"{realm}?service={svc}&scope=repository:library/{repo}:pull"
        tok = json.load(urllib.request.urlopen(tok_url, timeout=15))["token"]
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers={"Authorization": "Bearer " + tok, "Accept": ACCEPT}),
            timeout=15)
        return f"{host} {repo}:{tag} -> ANON OK {r.status}"


for host in ["docker.1ms.run", "docker.m.daocloud.io", "dockerproxy.net"]:
    for repo, tag in [("python", "3.12-slim"), ("node", "22-alpine")]:
        try:
            print(check_image(host, repo, tag), flush=True)
        except Exception as e:
            print(f"{host} {repo}:{tag} -> ERROR {e}", flush=True)
