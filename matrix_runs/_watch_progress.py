import json, time, urllib.request, os
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
out=root/"matrix_runs"/"_watch_progress.txt"
weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"
last=None
for i in range(80):
    try:
        st=json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=6).read().decode())
    except Exception as e:
        st={"error":str(e)}
    rlog=(weak/"runner.log").read_text(encoding="utf-8",errors="replace") if (weak/"runner.log").exists() else ""
    lines=rlog.strip().splitlines()
    summary=""
    if (weak/"summary.jsonl").exists():
        rows=[json.loads(x) for x in (weak/"summary.jsonl").read_text(encoding="utf-8",errors="replace").splitlines() if x.strip()]
        uniq={}
        for r in rows: uniq[(r.get("cell"),r.get("round"))]=r
        summary=f"unique={len(uniq)} " + ", ".join(f"{k[0]}r{k[1]}={v.get('class')}" for k,v in sorted(uniq.items()))
    snap=f"{datetime.now().isoformat(timespec='seconds')} i={i} run={st.get('running')} phase={st.get('phase')} j={st.get('jobs_started')}/{st.get('jobs_finished')} ok={st.get('session_success')} p={st.get('session_pending_sso')} last={(st.get('last_event') or '')[:140]}\n{summary}\nRUNNER_LAST={(lines[-1] if lines else '')}\n"
    prev=out.read_text(encoding="utf-8",errors="replace") if out.exists() else ""
    # append only when change or every 4 ticks
    key=(st.get('phase'), st.get('jobs_finished'), st.get('last_event'), lines[-1] if lines else '')
    if key!=last or i%4==0:
        with out.open('a',encoding='utf-8') as f:
            f.write(snap+"---\n")
        last=key
    alive=True
    try: os.kill(156952,0)
    except OSError: alive=False
    if (not alive) and not st.get('running'):
        with out.open('a',encoding='utf-8') as f:
            f.write(f"DONE {datetime.now().isoformat(timespec='seconds')}\n")
        break
    time.sleep(20)
