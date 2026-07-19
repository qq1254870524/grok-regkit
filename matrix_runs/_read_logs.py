import json, urllib.request
from pathlib import Path
d=json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=100", timeout=10))
lines=d.get("lines") or []
Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_last_logs.txt").write_text("\n".join(str(x) for x in lines), encoding="utf-8")
print("wrote", len(lines))
