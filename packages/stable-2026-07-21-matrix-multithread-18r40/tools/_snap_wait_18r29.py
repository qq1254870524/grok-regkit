import time, json, urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
SNAP=ROOT/'matrix_runs'/'_snap_wait_18r29.txt'
time.sleep(200)
rows=[]
if (OUT/'summary.jsonl').exists():
    rows=[json.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
by=defaultdict(list)
for r in rows: by[r.get('cell')].append(r)
lines=[f'ts={datetime.now().isoformat(timespec="seconds")}', f'rows={len(rows)} report={(OUT/"REPORT.md").exists()}']
for c,items in by.items():
    best={}
    for it in items:
        ri=it.get('round'); prev=best.get(ri)
        if prev is None or (it.get('ok') and not prev.get('ok')): best[ri]=it
    ok=sum(1 for v in best.values() if v.get('ok'))
    cls=dict(Counter(v.get('class') for v in best.values()))
    lines.append(f'{c}: {ok}/{len(best)} {cls}')
try:
    st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode('utf-8','replace'))
    lines.append(f"api running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:180]}")
except Exception as e:
    lines.append(f'api err {e}')
cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
if cl.exists():
    lines.append('console:')
    lines.extend(cl.read_text(encoding='utf-8',errors='replace').splitlines()[-12:])
SNAP.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('wrote', SNAP)
