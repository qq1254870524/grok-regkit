import time, json, urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
DEST=ROOT/'matrix_runs'/'_progress_pack_18r29.txt'
# wait until either +2 ok, or socks5 cell starts, or 8 min
start_ok=None
t0=time.time()
while time.time()-t0 < 480:
    rows=[]
    if (OUT/'summary.jsonl').exists():
        rows=[json.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    by=defaultdict(list)
    for r in rows: by[r.get('cell')].append(r)
    cells={}
    ok=0
    for c,items in by.items():
        best={}
        for it in items:
            ri=it.get('round'); prev=best.get(ri)
            if prev is None or (it.get('ok') and not prev.get('ok')): best[ri]=it
        o=sum(1 for v in best.values() if v.get('ok'))
        ok += o
        cells[c]={'ok':o,'n':len(best),'cls':dict(Counter(v.get('class') for v in best.values()))}
    if start_ok is None: start_ok=ok
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode('utf-8','replace'))
    except Exception as e:
        st={'error':str(e)}
    lines=[f'ts={datetime.now().isoformat(timespec="seconds")}', f'ok={ok} start_ok={start_ok} rows={len(rows)} report={(OUT/"REPORT.md").exists()}']
    for c,v in cells.items():
        lines.append(f"  {c}: {v['ok']}/{v['n']} {v['cls']}")
    lines.append(f"api running={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:160]}")
    cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
    if cl.exists():
        lines.append('console:')
        lines.extend(cl.read_text(encoding='utf-8',errors='replace').splitlines()[-8:])
    DEST.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # stop conditions
    if any('socks5' in c for c in cells) or ok>=start_ok+2 or (OUT/'REPORT.md').exists():
        break
    time.sleep(20)
print('pack done')
