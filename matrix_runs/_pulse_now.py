import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
weak = root / "matrix_runs" / "matrix_18r24_weak_20260719_033411"
out = root / "matrix_runs" / "_pulse_now.txt"
lines=[]
for i in range(12):
    ts=datetime.now().strftime("%H:%M:%S")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            s=json.loads(r.read().decode())
        last=(s.get("last_event") or "")[:120]
        line=f"{ts} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={last}"
    except Exception as e:
        line=f"{ts} status_err={e}"
    rl=weak/"runner.log"
    m=rl.stat().st_mtime if rl.exists() else 0
    line += f" runner_m={datetime.fromtimestamp(m).strftime('%H:%M:%S') if m else '-'}"
    lines.append(line)
    out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    time.sleep(20)
# final dump
tail=rl.read_text(encoding="utf-8", errors="replace").splitlines()[-20:] if rl.exists() else []
lines.append("---runner---")
lines.extend(tail)
out.write_text("\n".join(lines)+"\n", encoding="utf-8")
