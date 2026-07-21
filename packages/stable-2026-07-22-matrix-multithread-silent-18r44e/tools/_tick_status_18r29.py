import json, time, urllib.request, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
OUT = Path('matrix_runs/matrix_18r29_20260719_070041')
end = time.time() + 8.0
last = ''
while time.time() < end:
    try:
        st = json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=3).read())
    except Exception as e:
        st = {'error': str(e)}
    rows=[]
    p=OUT/'summary.jsonl'
    if p.exists():
        rows=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    by=defaultdict(dict)
    for r in rows:
        c=r.get('cell'); ri=r.get('round'); prev=by[c].get(ri)
        if prev is None or (r.get('ok') and not prev.get('ok')):
            by[c][ri]=r
    parts=[]
    for c in sorted(by):
        ok=sum(1 for v in by[c].values() if v.get('ok'))
        short=''.join(x[:1] for x in c.split('__'))
        parts.append(f"{short}={ok}/{len(by[c])}")
    ev=(st.get('last_event') or '')
    ev=''.join(ch if ord(ch)<128 else '?' for ch in ev)[:90]
    line=f"{datetime.now().strftime('%H:%M:%S')} rows={len(rows)} run={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')} {','.join(parts)} ev={ev}"
    if line!=last:
        print(line, flush=True)
        last=line
    time.sleep(1.5)
# console tail
cl=Path('matrix_runs/matrix_18r29_runner_console.log')
if cl.exists():
    print('CONSOLE:', cl.read_text(encoding='utf-8',errors='replace').splitlines()[-3:])
print('tick_done')
