import time, json, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "_pulse.txt"
for i in range(120):
    lines = [datetime.now().isoformat(timespec="seconds")]
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=6).read().decode())
        lines.append(
            f"run={st.get('running')} kind={st.get('job_kind')} phase={st.get('phase')} "
            f"s={st.get('success')} f={st.get('fail')} p={st.get('pending_sso')} ev={st.get('last_event')}"
        )
    except Exception as e:
        lines.append(f"status_err={e}")
    r = subprocess.run(["tasklist", "/FI", "PID eq 154288", "/NH"], capture_output=True, text=True, timeout=8)
    lines.append("matrix=" + ("alive" if "154288" in (r.stdout or "") else "dead"))
    summ = root / "matrix_runs" / "matrix_18r21_20260719_023216" / "summary.jsonl"
    if summ.exists():
        rows = summ.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        lines.append(f"summary_rows={len(rows)}")
        if rows:
            lines.append("last=" + rows[-1][:300])
    pl = root / "matrix_runs" / "_post_matrix_r24_actions.log"
    if pl.exists():
        ls = pl.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if ls:
            lines.append("post=" + ls[-1])
    done = root / "matrix_runs" / "_matrix_r24_pipeline.flag"
    lines.append("r24_done=" + str(done.exists()))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if "matrix=dead" in "\n".join(lines) and i > 2:
        # keep a bit more for post pipeline
        if done.exists():
            break
        if i > 10:
            # still wait for r24 pipeline
            pass
    if done.exists() and i > 3:
        break
    time.sleep(35)
