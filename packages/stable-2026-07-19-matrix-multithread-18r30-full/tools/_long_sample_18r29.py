import time, json, urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
for i in range(24):  # ~24 * 150s ~= 60min of samples
    time.sleep(150)
    rows=[]
    if (OUT/'summary.jsonl').exists():
        rows=[json.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    by=defaultdict(list)
    for r in rows: by[r.get('cell')].append(r)
    lines=[f'=== sample {i+1} ts={datetime.now().isoformat(timespec="seconds")} rows={len(rows)} report={(OUT/"REPORT.md").exists()} ===']
    for c,items in sorted(by.items()):
        best={}
        for it in items:
            ri=it.get('round'); prev=best.get(ri)
            if prev is None or (it.get('ok') and not prev.get('ok')): best[ri]=it
        ok=sum(1 for v in best.values() if v.get('ok'))
        fails=[v for v in best.values() if not v.get('ok')]
        cls=dict(Counter(v.get('class') for v in best.values()))
        lines.append(f'{c}: {ok}/{len(best)} {cls}')
        for fr in fails:
            if fr.get('class')!='empty_log':
                lines.append(f'  FAIL r{fr.get("round")} class={fr.get("class")} err={(fr.get("error") or "")[:180]}')
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode('utf-8','replace'))
        lines.append(f"api running={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} p={st.get('session_pending_sso')} ev={(st.get('last_event') or '')[:160]}")
    except Exception as e:
        lines.append(f'api err {e}')
    cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
    if cl.exists():
        lines.append('console_tail:')
        lines.extend(cl.read_text(encoding='utf-8',errors='replace').splitlines()[-6:])
    text='\n'.join(lines)+'\n'
    (ROOT/'matrix_runs'/'_long_sample_18r29.txt').write_text(text, encoding='utf-8')
    with (ROOT/'matrix_runs'/'_long_sample_18r29_hist.txt').open('a',encoding='utf-8') as f:
        f.write(text+'\n')
    if (OUT/'REPORT.md').exists():
        break
print('long sampler done')
