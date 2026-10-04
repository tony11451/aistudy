import re
from pathlib import Path

root = Path("D:/Projects/ST")
for name in ["Dockerfile", "Dockerfile.full"]:
    text = (root / name).read_text(encoding="utf-8")
    froms = re.findall(r"^FROM\s+(\S+)", text, re.M)
    for f in froms:
        ok = f.startswith("${") or "." in f.split("/")[0]
        assert ok, (name, f)
    print(name, "FROM lines:", froms)
    for m in re.finditer(r"^ARG\s+(\w+)=(\S+)", text, re.M):
        host = m.group(2).split("/")[0]
        assert host == "docker.1ms.run", (name, m.group(0))
        print("  ARG", m.group(1), "=", m.group(2))
    assert "pypi.tuna.tsinghua.edu.cn" in text, name + " missing pip mirror"
print("DOCKERFILE CHECKS OK")
