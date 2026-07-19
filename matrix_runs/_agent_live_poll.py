import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root = Path(r'C:\Users\zhang\grok-regkit')
mr = root / 'matrix_runs'
out = mr / 'matrix_18r29_20260719_070041'
snap = mr / '_agent_live_poll.txt'
logp = mr / '_agent_live_poll.log'

def ts():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

def status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def board():
    p = mr / '_progress_board_18r29.txt'
    return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

def console_tail(n=12):
    p = mr / 'matrix_18r29_runner_console.log'
    if not p.exists():
        return ''
    lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    return '\n'.join(lines[-n:])

def summary_tail(n=5):
    p = out / 'summary.jsonl'
    if not p.exists():
        return ''
    lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    return '\n'.join(lines[-n:])

def latest_log_tail(n=25):
    logs = sorted(out.glob('browser__socks5_list__*_r*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    # prefer most recent of any unfinished cell
    all_logs = sorted(out.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
    for cand in all_logs:
        if cand.name in ('runner.log',):
            continue
        if 'browser__' in cand.name or 'hybrid__' in cand.name or 'pending' in cand.name:
            txt = cand.read_text(encoding='utf-8', errors='replace').splitlines()
            return cand.name, '\n'.join(txt[-n:])
    return '', ''

def matrix_alive():
    # cheap: console mtime or summary
    c = mr / 'matrix_18r29_runner_console.log'
    s = out / 'summary.jsonl'
    mt = max(c.stat().st_mtime if c.exists() else 0, s.stat().st_mtime if s.exists() else 0)
    return mt

last_mt = 0
stall = 0
for i in range(240):  # up to ~2h at 30s
    st = status()
    b = board()
    ct = console_tail()
    sm = summary_tail()
    ln, lt = latest_log_tail()
    mt = matrix_alive()
    if mt <= last_mt and not st.get('running'):
        stall += 1
    elif mt > last_mt:
        stall = 0
        last_mt = mt
    elif st.get('running'):
        stall = 0
        last_mt = max(last_mt, mt)
    report = (out / 'REPORT.md').exists()
    done = (mr / '_agent_matrix_done.flag').exists()
    body = [
        f'tag=poll ts={ts()} i={i} stall={stall} report={report} done={done}',
        f'STATUS={json.dumps(st, ensure_ascii=False)}',
        'BOARD', b.strip(),
        'CONSOLE', ct,
        'SUMMARY', sm,
        f'LATEST_LOG={ln}', lt,
    ]
    text = '\n'.join(body) + '\n'
    snap.write_text(text, encoding='utf-8')
    with logp.open('a', encoding='utf-8') as f:
        f.write(f'[{ts()}] running={st.get("running")} phase={st.get("phase")} jobs={st.get("jobs_started")}/{st.get("jobs_finished")} session_s={st.get("session_success")} p={st.get("session_pending_sso")} report={report} done={done}\n')
    if done or (report and not st.get('running') and 'cells_ge10=10' in b):
        break
    # if report exists and matrix not running, still wait a bit for publish
    if report and not st.get('running'):
        # keep polling until done flag or 20 more min
        pass
    time.sleep(30)
