import json, time, urllib.request, subprocess, os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT/"matrix_runs"/"matrix_18r29_20260719_070041"
SNAP = ROOT/"matrix_runs"/"_agent_poll_18r29h.txt"
os.chdir(ROOT)

def get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def board():
    cells=defaultdict(list)
    sj=OUT/"summary.jsonl"
    if not sj.exists():
        return "no summary", 0, 0
    for line in sj.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try: r=json.loads(line)
        except Exception:
            continue
        cells[r.get("cell") or "?"].append(r)
    lines=[]; ge=0
    for c,rows in sorted(cells.items()):
        n=len(rows)
        ok=sum(1 for x in rows if x.get("ok") or x.get("class") in ("success","pending_sso"))
        if n>=10: ge+=1
        lines.append(f"{c}: {n}/10 ok={ok} {dict(Counter(x.get('class') for x in rows))}")
    total=sum(len(v) for v in cells.values())
    lines.append(f"rows={total} cells_ge10={ge} report={(OUT/'REPORT.md').exists()}")
    return "\n".join(lines), total, ge

def matrix_alive():
    try:
        out=subprocess.check_output(["powershell","-NoProfile","-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_cross_run' } | Select-Object -ExpandProperty ProcessId"],
            text=True, encoding="utf-8", errors="replace", timeout=10)
        return bool(out.strip())
    except Exception:
        return False

stall_n=0
last_jobs=None
while True:
    try:
        st=json.loads(get("http://127.0.0.1:8092/api/status"))
    except Exception as e:
        st={"error":str(e)}
    b,total,ge=board()
    try:
        logs=json.loads(get("http://127.0.0.1:8092/api/logs/snapshot?limit=12"))
        last="\n".join((logs.get("lines") or [])[-10:])
    except Exception as e:
        last=str(e)
    console=ROOT/"matrix_runs"/"matrix_18r29_runner_console.log"
    ct="\n".join(console.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]) if console.exists() else ""
    alive=matrix_alive()
    jobs=f"{st.get('jobs_started')}/{st.get('jobs_finished')} phase={st.get('phase')} run={st.get('running')} evt={st.get('last_event')}"
    if jobs==last_jobs and st.get("running"):
        stall_n += 1
    else:
        stall_n = 0
    last_jobs=jobs
    msg=(f"ts={datetime.now().isoformat(timespec='seconds')}\n"
         f"matrix_alive={alive} stall_ticks={stall_n}\n"
         f"STATUS={json.dumps(st, ensure_ascii=False)}\nBOARD\n{b}\nLOGS\n{last}\nCONSOLE\n{ct}\n")
    SNAP.write_text(msg, encoding="utf-8")
    (ROOT/"matrix_runs"/"_progress_board_18r29.txt").write_text(b+"\n", encoding="utf-8")
    if (OUT/"REPORT.md").exists():
        SNAP.write_text(msg+"REPORT_READY\n", encoding="utf-8")
        break
    # if matrix dead and job not running for a while, mark need_resume
    if not alive and not st.get("running") and not (OUT/"REPORT.md").exists():
        (ROOT/"matrix_runs"/"_need_resume_18r29.flag").write_text(msg, encoding="utf-8")
        # don't break immediately; wait a bit in case restarting
        time.sleep(30)
        if not matrix_alive() and not (OUT/"REPORT.md").exists():
            break
    # if job stalled > 12 ticks (~3min) while running with same phase message
    if stall_n >= 12 and st.get("running"):
        (ROOT/"matrix_runs"/"_stall_job_18r29.flag").write_text(msg, encoding="utf-8")
    time.sleep(15)
