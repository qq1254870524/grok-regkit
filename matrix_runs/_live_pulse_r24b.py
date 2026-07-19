import json, time, urllib.request
from datetime import datetime
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "_live_pulse_r24b.txt"
WEAK = ROOT / "matrix_runs" / "matrix_18r24_weak_20260719_033411"
while True:
    lines = []
    lines.append(datetime.now().isoformat(timespec="seconds"))
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            st = json.loads(r.read().decode("utf-8","replace"))
        lines.append(f"8092 running={st.get('running')} phase={st.get('phase')} sess_ok={st.get('session_success')} sess_fail={st.get('session_fail')} sess_p={st.get('session_pending_sso')} job={st.get('jobs_started')}/{st.get('jobs_finished')} ev={str(st.get('last_event') or '')[:160]}")
    except Exception as e:
        lines.append(f"8092 err={e}")
    rl = WEAK / "runner.log"
    if rl.is_file():
        tail = rl.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-12:]
        lines.append("RUNNER:")
        lines.extend(tail)
    sm = WEAK / "summary.jsonl"
    if sm.is_file():
        rows = []
        seen=set()
        for line in sm.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                d=json.loads(line)
            except Exception:
                continue
            k=(d.get("cell"), d.get("round"))
            if k in seen:
                continue
            seen.add(k)
            rows.append(f"{d.get('cell')} r{d.get('round')} {d.get('class')} ok={d.get('ok')}")
        lines.append(f"SUMMARY unique={len(rows)}")
        lines.extend(rows[-20:])
    OUT.write_text("\n".join(lines)+"\n", encoding="utf-8")
    # stop if weak done: no python matrix_rerun and not running for a while
    time.sleep(20)
