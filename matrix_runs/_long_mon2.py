import json, time, urllib.request, subprocess
from pathlib import Path
md = Path(r'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216')
out = Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_monitor_out.txt')
lines = []
def snap(tag):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5) as r:
            st = json.loads(r.read().decode())
    except Exception as e:
        st = {'err': str(e)}
    try:
        with urllib.request.urlopen('http://127.0.0.1:8092/api/logs/snapshot?limit=25', timeout=5) as r:
            logs = json.loads(r.read().decode()).get('lines') or []
    except Exception:
        logs = []
    runner = (md/'runner.log').read_text(encoding='utf-8', errors='replace').splitlines()[-25:] if (md/'runner.log').exists() else []
    summ = (md/'summary.jsonl').read_text(encoding='utf-8', errors='replace').splitlines() if (md/'summary.jsonl').exists() else []
    block = [f'==== {tag} {time.strftime("%H:%M:%S")} ====']
    block.append(json.dumps(st, ensure_ascii=False)[:500])
    block.append('RUNNER:')
    block.extend(runner)
    block.append(f'SUMMARY n={len(summ)}:')
    block.extend(summ[-20:])
    block.append('LOGS:')
    block.extend(logs[-20:])
    text = '\n'.join(block) + '\n'
    out.write_text(text, encoding='utf-8')
    return st, summ

snap('start')
# poll up to 8 minutes
for i in range(48):
    time.sleep(10)
    st, summ = snap(f'poll{i}')
    # detect matrix done: no matrix process
    try:
        import psutil
        alive = False
        for p in psutil.process_iter(['cmdline']):
            cl = ' '.join(p.info.get('cmdline') or [])
            if 'matrix_cross_run' in cl:
                alive = True
                break
    except Exception:
        alive = True
    # done if summary has pending_sso recovery cells and not running and matrix dead
    cells = set()
    for ln in summ:
        try:
            o=json.loads(ln)
            cells.add(o.get('cell'))
        except Exception:
            pass
    if (not alive) and (not st.get('running')):
        snap('DONE')
        break
    if not alive:
        snap('matrix_dead')
        break
snap('end')
