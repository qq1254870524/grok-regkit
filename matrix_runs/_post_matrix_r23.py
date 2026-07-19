import json, time, urllib.request, subprocess, sys, os
from pathlib import Path
ROOT = Path(r'C:\Users\zhang\grok-regkit')
os.chdir(ROOT)
logp = ROOT/'matrix_runs'/'_post_matrix_actions.log'

def w(msg):
    line=f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with logp.open('a',encoding='utf-8') as f:
        f.write(line+'\n')

def matrix_alive():
    try:
        import psutil
        for p in psutil.process_iter(['cmdline']):
            cl=' '.join(p.info.get('cmdline') or [])
            if 'matrix_cross_run' in cl:
                return True
    except Exception:
        return True
    return False

def status():
    with urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5) as r:
        return json.loads(r.read().decode())

w('waiting matrix finish...')
while matrix_alive():
    try:
        st=status()
        w(f'matrix alive running={st.get("running")} phase={st.get("phase")}')
    except Exception as e:
        w(f'status {e}')
    time.sleep(15)

w('matrix finished; wait idle')
for _ in range(20):
    try:
        st=status()
        if not st.get('running'):
            break
    except Exception:
        break
    time.sleep(2)

# restart 8092
import psutil
for p in psutil.process_iter(['pid','cmdline']):
    try:
        cl=' '.join(p.info.get('cmdline') or [])
        if 'web\\server.py' in cl or 'web/server.py' in cl:
            w(f'kill web {p.pid}')
            p.kill()
    except Exception:
        pass
time.sleep(2)
logf=open(ROOT/'logs'/'web_server_r23b.log','a',encoding='utf-8')
proc=subprocess.Popen([sys.executable,'-B','web\\server.py'], cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT,
                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
w(f'web restarted pid={proc.pid}')
time.sleep(3)
try:
    st=status(); w(f'health ok running={st.get("running")}')
except Exception as e:
    w(f'health fail {e}')

# write summary report
md=ROOT/'matrix_runs'/'matrix_18r21_20260719_023216'
summ=(md/'summary.jsonl').read_text(encoding='utf-8') if (md/'summary.jsonl').exists() else ''
(ROOT/'matrix_runs'/'_matrix_final_report.txt').write_text(summ, encoding='utf-8')
w('wrote final report; ready for git')
# marker
(ROOT/'matrix_runs'/'_matrix_done.flag').write_text('1',encoding='utf-8')
