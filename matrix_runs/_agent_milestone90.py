import json, time, urllib.request
from pathlib import Path
from datetime import datetime
MR = Path(r'C:\Users\zhang\grok-regkit\matrix_runs')
OUT = MR / 'matrix_18r29_20260719_070041'
LOG = MR / '_agent_milestone90.log'
SNAP = MR / '_agent_milestone90.txt'

def st():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5) as r:
            return json.loads(r.read().decode('utf-8','replace'))
    except Exception as e:
        return {'error': str(e)}

def board():
    p = MR/'_progress_board_18r29.txt'
    return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

def console_tail():
    p = MR/'matrix_18r29_runner_console.log'
    if not p.exists():
        return ''
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace').splitlines()[-8:])

last = ''
for i in range(80):
    s = st()
    b = board()
    rep = (OUT/'REPORT.md').exists()
    done = (MR/'_agent_matrix_done.flag').exists()
    line = f"[{datetime.now().strftime('%H:%M:%S')}] i={i} run={s.get('running')} phase={s.get('phase')} js={s.get('jobs_started')}/{s.get('jobs_finished')} ss={s.get('session_success')} sp={s.get('session_pending_sso')} le={(s.get('last_event') or '')[:120]} rep={rep} done={done}"
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line+'\n')
    body = line+'\nBOARD\n'+b+'\nCONSOLE\n'+console_tail()+'\n'
    if body != last:
        SNAP.write_text(body, encoding='utf-8')
        last = body
    if done or (rep and not s.get('running')):
        # keep a few more ticks for publish
        if done:
            break
    time.sleep(90)
