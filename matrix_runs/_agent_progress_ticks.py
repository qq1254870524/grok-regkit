import json, time, urllib.request, subprocess
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
ROOT=Path(r"C:\Users\zhang\grok-regkit")
OUT=ROOT/"matrix_runs"/"matrix_18r29_20260719_070041"
SNAP=ROOT/"matrix_runs"/"_agent_progress_ticks.txt"
last=None
while True:
    cells=defaultdict(list)
    if (OUT/"summary.jsonl").exists():
        for line in (OUT/"summary.jsonl").read_text(encoding="utf-8",errors="replace").splitlines():
            if line.strip():
                try:
                    r=json.loads(line); cells[r.get("cell")or"?"].append(r)
                except: pass
    try:
        st=json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status",timeout=5).read().decode())
    except Exception as e:
        st={"error":str(e)}
    key=(sum(len(v) for v in cells.values()), st.get("jobs_finished"), st.get("phase"), st.get("running"), (OUT/"REPORT.md").exists())
    if key!=last:
        last=key
        lines=[f"ts={datetime.now().isoformat(timespec='seconds')} key={key}"]
        for c,rows in sorted(cells.items()):
            lines.append(f"{c}: {len(rows)}/10 {dict(Counter(x.get('class') for x in rows))}")
        lines.append(f"evt={st.get('last_event')}")
        lines.append(f"session s={st.get('session_success')} f={st.get('session_fail')} p={st.get('session_pending_sso')}")
        lines.append(f"REPORT={(OUT/'REPORT.md').exists()} DONE={(ROOT/'matrix_runs'/'_agent_matrix_done.flag').exists()}")
        with SNAP.open("a",encoding="utf-8") as f:
            f.write("\n".join(lines)+"\n---\n")
        (ROOT/"matrix_runs"/"_agent_latest_progress.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
    if (OUT/"REPORT.md").exists() and (ROOT/"matrix_runs"/"_agent_matrix_done.flag").exists():
        break
    # also stop if package exists
    if (OUT/"REPORT.md").exists():
        # keep ticking until done flag or 2h
        pass
    time.sleep(20)
