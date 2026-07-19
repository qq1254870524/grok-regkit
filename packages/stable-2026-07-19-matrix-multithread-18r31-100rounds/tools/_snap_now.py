import json, urllib.request, subprocess
from pathlib import Path
from datetime import datetime

out = Path("matrix_runs/matrix_18r29_20260719_070041")
sj = out / "summary.jsonl"
st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
lines = sj.read_text(encoding="utf-8", errors="replace").strip().splitlines() if sj.exists() else []
rows = [json.loads(x) for x in lines if x.strip()]
print("time", datetime.now())
print("n", len(rows))
if rows:
    print("last", rows[-1])
print("status keys", {k: st.get(k) for k in [
    "running", "success", "fail", "pending_sso", "session_success", "session_fail",
    "session_pending_sso", "phase", "jobs_started", "jobs_finished", "error", "job_kind"
]})
print("evt", (st.get("last_event") or "")[:240])
print("newest:")
for p in sorted(out.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
    print(" ", p.name, p.stat().st_size, datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S"))

ps = subprocess.check_output([
    "powershell", "-NoProfile", "-Command",
    "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_cross_run|auto_publish|final_guardian|unattended' } | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)))\" }"
], text=True, errors="replace")
print("procs:\n", ps)

# classify summary
from collections import defaultdict, Counter
by = defaultdict(list)
for r in rows:
    by[r.get("cell")].append(r)
for cell, items in by.items():
    c = Counter(x.get("class") for x in items)
    ok = sum(1 for x in items if x.get("ok"))
    print(f"CELL {cell}: total={len(items)} ok={ok} classes={dict(c)} max_round={max(x.get('round',0) for x in items)}")
