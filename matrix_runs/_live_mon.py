import time, json, os, urllib.request
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
mdir = root / "matrix_runs" / "matrix_18r21_20260719_023216"
out = root / "matrix_runs" / "_live_status.txt"
done = root / "matrix_runs" / "_matrix_done.flag"
for i in range(240):  # up to ~2h at 30s
    lines = []
    lines.append(f"ts={datetime.now().isoformat(timespec='seconds')}")
    # matrix pid
    import subprocess
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command","Get-Process -Id 154288 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"], capture_output=True, text=True, timeout=10)
        alive = bool((r.stdout or "").strip())
    except Exception:
        alive = False
    lines.append(f"matrix_pid_154288_alive={alive}")
    summary = mdir / "summary.jsonl"
    cells = []
    if summary.exists():
        for ln in summary.read_text(encoding="utf-8", errors="replace").splitlines():
            ln=ln.strip()
            if not ln: continue
            try:
                o=json.loads(ln)
                cells.append(f"{o.get('cell')} r{o.get('round')} {o.get('class')} ok={o.get('ok')}")
            except Exception:
                pass
        lines.append(f"summary_rows={len(cells)}")
        lines.extend(cells[-8:])
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4) as resp:
            st=json.loads(resp.read().decode())
        lines.append(f"8092 running={st.get('running')} phase={st.get('phase')} s={st.get('success')} f={st.get('fail')} p={st.get('pending_sso')}")
    except Exception as e:
        lines.append(f"8092 err={e}")
    latest = sorted(mdir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    for p in latest:
        lines.append(f"log {p.name} size={p.stat().st_size} mtime={datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')}")
    out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    if done.exists() or (not alive and i>2):
        lines.append("EXIT_REASON=done_or_dead")
        out.write_text("\n".join(lines)+"\n", encoding="utf-8")
        break
    time.sleep(30)
