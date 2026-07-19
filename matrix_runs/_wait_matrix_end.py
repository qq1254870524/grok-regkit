import time, subprocess, json, urllib.request
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "_wait_matrix_end.txt"
for i in range(50):
    r = subprocess.run(["tasklist", "/FI", "PID eq 154288", "/NH"], capture_output=True, text=True, timeout=8)
    alive = "154288" in (r.stdout or "")
    line = f"{datetime.now().isoformat(timespec='seconds')} matrix_alive={alive}"
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
        line += f" run={st.get('running')} kind={st.get('job_kind')} phase={st.get('phase')} ev={str(st.get('last_event'))[:80]}"
    except Exception as e:
        line += f" st_err={e}"
    runner = root / "matrix_runs" / "matrix_18r21_20260719_023216" / "runner.log"
    if runner.exists():
        ls = runner.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if ls:
            line += " | " + ls[-1][:160]
    out.write_text(line + "\n", encoding="utf-8")
    if not alive:
        out.write_text(line + "\nENDED\n", encoding="utf-8")
        break
    time.sleep(20)
