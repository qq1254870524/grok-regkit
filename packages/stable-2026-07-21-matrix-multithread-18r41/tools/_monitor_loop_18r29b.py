import json, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
ALERT=ROOT/'matrix_runs'/'_alerts_18r29.txt'
PULSE=ROOT/'matrix_runs'/'_monitor_18r29.txt'
last_rows=0
last_fail_sig=''
while True:
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5).read().decode('utf-8','replace'))
    except Exception as e:
        st={'error':str(e),'running':False}
    rows=[]
    if (OUT/'summary.jsonl').exists():
        rows=[json.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    from collections import Counter, defaultdict
    by=defaultdict(list)
    for r in rows:
        by[r.get('cell')].append(r)
    # unique best per round
    cells={}
    for c,items in by.items():
        best={}
        for it in items:
            ri=it.get('round')
            prev=best.get(ri)
            if prev is None or (it.get('ok') and not prev.get('ok')):
                best[ri]=it
        ok=sum(1 for v in best.values() if v.get('ok'))
        cls=dict(Counter(v.get('class') for v in best.values()))
        cells[c]={'ok':ok,'n':len(best),'cls':cls}
    fails=[r for r in rows if not r.get('ok') and r.get('class')!='empty_log']
    new_fails=fails
    lines=[]
    lines.append(f"ts={datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:160]}")
    lines.append(f"summary_rows={len(rows)} report={(OUT/'REPORT.md').exists()}")
    for c,v in cells.items():
        lines.append(f"  {c}: {v['ok']}/{v['n']} {v['cls']}")
    if fails:
        last=fails[-1]
        lines.append(f"LAST_FAIL cell={last.get('cell')} r={last.get('round')} class={last.get('class')} err={(last.get('error') or '')[:200]}")
        sig=f"{last.get('cell')}|{last.get('round')}|{last.get('class')}|{last.get('finished')}"
        if sig!=last_fail_sig:
            last_fail_sig=sig
            with ALERT.open('a',encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat(timespec='seconds')}] FAIL {sig} err={(last.get('error') or '')[:300]}\n")
    # console tail
    cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
    if cl.exists():
        tail='\n'.join(cl.read_text(encoding='utf-8',errors='replace').splitlines()[-8:])
        lines.append('console:')
        lines.append(tail)
    PULSE.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # stop if report
    if (OUT/'REPORT.md').exists():
        with ALERT.open('a',encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] REPORT ready\n")
        break
    # matrix process check
    time.sleep(25)
