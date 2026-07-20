import urllib.request, json, time, subprocess
from pathlib import Path

for url in ["http://127.0.0.1:8092/api/status", "http://127.0.0.1:8092/api/config"]:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = r.read().decode("utf-8", errors="replace")
            print("===", url, "===")
            print(data[:3000])
    except Exception as e:
        print(url, "ERR", e)

# process list via PowerShell
ps = subprocess.check_output(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Depth 3"],
    text=True, errors="replace"
)
print("=== PYTHON PROCS ===")
try:
    procs = json.loads(ps) if ps.strip() else []
    if isinstance(procs, dict):
        procs = [procs]
    for p in procs:
        cmd = p.get("CommandLine") or ""
        if any(k in cmd.lower() for k in ["matrix", "server.py", "guardian", "hybrid", "web\\", "web/", "auto_publish", "snap", "regkit", "grok_register"]):
            print(p.get("ProcessId"), cmd[:400])
except Exception as e:
    print("parse err", e)
    print(ps[:2000])

outp = Path("matrix_runs/matrix_18r29_20260719_070041")
print("=== recent out ===")
for p in sorted(outp.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:8]:
    print(p.name, p.stat().st_size, time.ctime(p.stat().st_mtime))

# runner.log tail
rl = outp / "runner.log"
if rl.exists():
    print("=== runner.log tail ===")
    print(rl.read_text(encoding="utf-8", errors="replace")[-2000:])
