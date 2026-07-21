import json, time, urllib.request
from pathlib import Path
from collections import defaultdict
OUT = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041")
FLAG = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_gate_hybrid_done_18r29.txt")
SUM = OUT / "summary.jsonl"
def cells():
    by=defaultdict(dict)
    if not SUM.exists(): return by,0
    rows=[json.loads(x) for x in SUM.read_text(encoding='utf-8').splitlines() if x.strip()]
    for r in rows:
        c=r.get('cell'); ri=r.get('round'); prev=by[c].get(ri)
        if prev is None or (r.get('ok') and not prev.get('ok')): by[c][ri]=r
    return by,len(rows)
last=-1
while True:
    by,n=cells()
    hsa=by.get('hybrid__socks5_list__aol',{})
    ok=sum(1 for v in hsa.values() if v.get('ok'))
    tot=len(hsa)
    st={}
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=4).read().decode())
    except Exception as e:
        st={'error':str(e)}
    line=f"{time.strftime('%H:%M:%S')} rows={n} hsa={ok}/{tot} phase={st.get('phase')} sess={st.get('session_success')} j={st.get('jobs_started')}/{st.get('jobs_finished')} report={(OUT/'REPORT.md').exists()}\n"
    if n!=last or ok>=10 or (OUT/'REPORT.md').exists():
        with FLAG.open('a',encoding='utf-8') as f: f.write(line)
        last=n
    # also write live
    FLAG.with_name('_gate_live_18r29.txt').write_text(line,encoding='utf-8')
    if ok>=10 and tot>=10:
        with FLAG.open('a',encoding='utf-8') as f: f.write('HYBRID_SOCKS5_AOL_DONE\n')
        break
    if (OUT/'REPORT.md').exists():
        with FLAG.open('a',encoding='utf-8') as f: f.write('REPORT_READY\n')
        break
    time.sleep(20)
