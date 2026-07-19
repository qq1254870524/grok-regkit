import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "_monitor_r24c.txt"
weak = root / "matrix_runs" / "matrix_18r24_weak_20260719_033411"
def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}
for i in range(24):
    st = status()
    logs = sorted(weak.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    lines = [
        f"=== {datetime.now().isoformat(timespec='seconds')} i={i} ===",
        f"8092 running={st.get('running')} phase={st.get('phase')} job={st.get('jobs_started')}/{st.get('jobs_finished')} sess_ok={st.get('session_success')} p={st.get('session_pending_sso')} last={st.get('last_event','')[:160]}",
    ]
    rlog = weak / "runner.log"
    if rlog.exists():
        lines.append("RUNNER_TAIL:")
        lines.extend(rlog.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    lines.append("LOGS:")
    for p in logs:
        lines.append(f"  {p.name} {p.stat().st_size} {datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')}")
    sumf = weak / "summary.jsonl"
    if sumf.exists():
        rows = [json.loads(x) for x in sumf.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
        uniq = {}
        for r in rows:
            uniq[(r.get("cell"), r.get("round"))] = r
        lines.append(f"SUMMARY unique={len(uniq)}")
        for k,r in sorted(uniq.items(), key=lambda x: (str(x[0][0]), x[0][1] or 0)):
            lines.append(f"  {k[0]} r{k[1]} {r.get('class')} ok={r.get('ok')}")
    out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    # exit early if runner dead and idle
    import os
    alive = True
    try:
        os.kill(156952, 0)
    except OSError:
        alive = False
    if (not alive) and not st.get("running"):
        lines.append("RUNNER_DEAD_AND_IDLE")
        out.write_text("\n".join(lines)+"\n", encoding="utf-8")
        break
    time.sleep(30)
