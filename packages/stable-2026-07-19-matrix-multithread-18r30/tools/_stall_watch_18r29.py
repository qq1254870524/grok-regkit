import time, json, urllib.request
from pathlib import Path
from datetime import datetime
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
ALERT=ROOT/'matrix_runs'/'_alerts_18r29.txt'
STALL=ROOT/'matrix_runs'/'_stall_watch_18r29.txt'
last_console_mtime=None
last_progress_ts=time.time()
last_ok=0
while True:
    now=datetime.now().isoformat(timespec='seconds')
    cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
    mt=cl.stat().st_mtime if cl.exists() else 0
    rows=0
    ok=0
    if (OUT/'summary.jsonl').exists():
        import json as J
        from collections import Counter,defaultdict
        rs=[J.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        rows=len(rs)
        by=defaultdict(list)
        for r in rs: by[r.get('cell')].append(r)
        for c,items in by.items():
            best={}
            for it in items:
                ri=it.get('round'); prev=best.get(ri)
                if prev is None or (it.get('ok') and not prev.get('ok')): best[ri]=it
            ok += sum(1 for v in best.values() if v.get('ok'))
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode('utf-8','replace'))
    except Exception as e:
        st={'error':str(e)}
    if ok!=last_ok or (last_console_mtime is not None and mt!=last_console_mtime):
        last_progress_ts=time.time()
        last_ok=ok
    last_console_mtime=mt
    stall_s=time.time()-last_progress_ts
    line=f"{now} ok={ok} rows={rows} stall_s={stall_s:.0f} running={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} report={(OUT/'REPORT.md').exists()} ev={(st.get('last_event') or st.get('error') or '')[:120]}"
    STALL.write_text(line+'\n',encoding='utf-8')
    # stall > 15 min while matrix should run
    if stall_s>900 and not (OUT/'REPORT.md').exists():
        with ALERT.open('a',encoding='utf-8') as f:
            f.write(f"[{now}] STALL {line}\n")
        last_progress_ts=time.time()  # avoid spam; re-alert next 15m
    if (OUT/'REPORT.md').exists():
        with ALERT.open('a',encoding='utf-8') as f:
            f.write(f"[{now}] REPORT ready from stall watch\n")
        break
    time.sleep(45)
