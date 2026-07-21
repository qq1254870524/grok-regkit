import time, json, urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
ROOT=Path(r'C:\Users\zhang\grok-regkit')
OUT=ROOT/'matrix_runs'/'matrix_18r29_20260719_070041'
DEST=ROOT/'matrix_runs'/'_progress_pack2_18r29.txt'
ALERT=ROOT/'matrix_runs'/'_alerts_18r29.txt'
t0=time.time()
last_sig=''
while time.time()-t0 < 1200:  # up to 20 min
    rows=[]
    if (OUT/'summary.jsonl').exists():
        rows=[json.loads(x) for x in (OUT/'summary.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    by=defaultdict(list)
    for r in rows: by[r.get('cell')].append(r)
    cells={}; ok=0; fails=[]
    for c,items in by.items():
        best={}
        for it in items:
            ri=it.get('round'); prev=best.get(ri)
            if prev is None or (it.get('ok') and not prev.get('ok')): best[ri]=it
        o=sum(1 for v in best.values() if v.get('ok'))
        ok+=o
        cells[c]={'ok':o,'n':len(best),'cls':dict(Counter(v.get('class') for v in best.values()))}
        for v in best.values():
            if not v.get('ok') and v.get('class')!='empty_log':
                fails.append(v)
    try:
        st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode('utf-8','replace'))
    except Exception as e:
        st={'error':str(e)}
    lines=[f'ts={datetime.now().isoformat(timespec="seconds")}', f'ok={ok} rows={len(rows)} report={(OUT/"REPORT.md").exists()} fails={len(fails)}']
    for c,v in sorted(cells.items()):
        lines.append(f"  {c}: {v['ok']}/{v['n']} {v['cls']}")
    for fr in fails[-5:]:
        lines.append(f"  FAIL {fr.get('cell')} r{fr.get('round')} {fr.get('class')} {(fr.get('error') or '')[:160]}")
    lines.append(f"api running={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} p={st.get('session_pending_sso')} ev={(st.get('last_event') or '')[:160]}")
    cl=ROOT/'matrix_runs'/'matrix_18r29_runner_console.log'
    if cl.exists():
        lines.append('console:')
        lines.extend(cl.read_text(encoding='utf-8',errors='replace').splitlines()[-10:])
    DEST.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # alert new fails
    for fr in fails:
        sig=f"{fr.get('cell')}|{fr.get('round')}|{fr.get('class')}|{fr.get('finished')}"
        if sig!=last_sig and sig not in getattr(urllib,'__x',set()):
            pass
    # break if browser cells start or report or socks5 both done 10
    so=cells.get('hybrid__socks5_list__outlook',{}).get('ok',0)
    sa=cells.get('hybrid__socks5_list__aol',{}).get('ok',0)
    if any(c.startswith('browser__') for c in cells) or (so>=10 and sa>=10) or (OUT/'REPORT.md').exists():
        break
    if fails:
        # keep going but mark
        with ALERT.open('a',encoding='utf-8') as f:
            fr=fails[-1]
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] pack2 fail {fr.get('cell')} r{fr.get('round')} {fr.get('class')} {(fr.get('error') or '')[:200]}\n")
    time.sleep(25)
print('pack2 done')
