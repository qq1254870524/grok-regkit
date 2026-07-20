import json, time, urllib.request, traceback
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
ROOT = Path(r'C:\Users\zhang\grok-regkit')
OUT = ROOT / 'matrix_runs' / 'matrix_18r29_20260719_070041'
LOG = ROOT / 'matrix_runs' / '_long_monitor_18r29.txt'

def w(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')

def cell_parts(rows):
    by = defaultdict(dict)
    for r in rows:
        c = r.get('cell'); ri = r.get('round'); prev = by[c].get(ri)
        if prev is None or (r.get('ok') and not prev.get('ok')):
            by[c][ri] = r
    parts = []
    for c in sorted(by):
        ok = sum(1 for v in by[c].values() if v.get('ok'))
        cls = dict(Counter((v.get('class') or '?') for v in by[c].values()))
        parts.append(f"{c}:{ok}/{len(by[c])}:{cls}")
    return parts

w('long monitor start')
last_rows = -1
last_ev = None
while True:
    try:
        if (OUT / 'REPORT.md').exists():
            w('REPORT ready')
            break
        try:
            st = json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5).read())
        except Exception as e:
            st = {'error': str(e)}
        rows = []
        if (OUT / 'summary.jsonl').exists():
            rows = [json.loads(x) for x in (OUT / 'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
        ev = st.get('last_event') or ''
        if len(rows) != last_rows or ev[:100] != (last_ev or '')[:100]:
            parts = cell_parts(rows)
            w(f"rows={len(rows)} run={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')}")
            w('cells ' + ' | '.join(parts))
            w('ev=' + str(ev)[:240])
            last_rows = len(rows)
            last_ev = ev
        sj = OUT / 'summary.jsonl'
        age = time.time() - sj.stat().st_mtime if sj.exists() else 9999
        if age > 1000 and not st.get('running'):
            w(f'ALERT stall age={int(age)}')
        time.sleep(20)
    except Exception:
        w('exc ' + traceback.format_exc()[-500:])
        time.sleep(10)
w('long monitor exit')
