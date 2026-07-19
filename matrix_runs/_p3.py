import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit"); weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"; out=root/"matrix_runs"/"_p3.txt"
lines=[]
for i in range(200):
    ts=datetime.now().strftime('%H:%M:%S')
    try:
        s=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=4))
        row=f"{ts} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={str(s.get('last_event'))[:100]}"
    except Exception as e:
        row=f"{ts} err={e}"
    rt=''
    try:
        rt='\n'.join((weak/'runner.log').read_text(encoding='utf-8',errors='replace').splitlines()[-2:])
    except Exception:
        pass
    lines.append(row); lines.append('  '+rt)
    out.write_text('\n'.join(lines[-100:])+'\n', encoding='utf-8')
    # stop if runner contains pending_sso_recovery r2 and not running
    try:
        full=(weak/'runner.log').read_text(encoding='utf-8',errors='replace')
    except Exception:
        full=''
    if 'pending_sso_recovery__direct] r2/' in full and 'run=False' in row:
        break
    if 'DONE' in (root/'matrix_runs'/'_post_matrix_r25_release.log').read_text(encoding='utf-8',errors='replace') if (root/'matrix_runs'/'_post_matrix_r25_release.log').exists() else '':
        lines.append('POST DONE'); out.write_text('\n'.join(lines[-120:])+'\n', encoding='utf-8'); break
    time.sleep(20)
