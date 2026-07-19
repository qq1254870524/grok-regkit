import json, time, urllib.request, subprocess, sys, os
from pathlib import Path
ROOT = Path(r'C:\Users\zhang\grok-regkit')
os.chdir(ROOT)
flag = ROOT/'matrix_runs'/'_restarted_r23b.flag'
logp = ROOT/'matrix_runs'/'_restart_r23b.log'

def w(msg):
    line=f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with logp.open('a',encoding='utf-8') as f:
        f.write(line+'\n')

def status():
    with urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5) as r:
        return json.loads(r.read().decode())

# wait until running False for 8s stable
stable=0
while True:
    try:
        st=status()
        run=bool(st.get('running'))
        w(f"watch running={run} phase={st.get('phase')} jobs_finished={st.get('jobs_finished')}")
        if not run:
            stable += 1
        else:
            stable = 0
        if stable >= 3:  # ~9s idle
            break
    except Exception as e:
        w(f'status err {e}')
        stable = 0
    time.sleep(3)

if flag.exists():
    w('already restarted flag present; exit')
    sys.exit(0)

w('idle confirmed; restart 8092 for r23b')
# stop job just in case
try:
    req=urllib.request.Request('http://127.0.0.1:8092/api/stop', data=b'{}', method='POST', headers={'Content-Type':'application/json'})
    urllib.request.urlopen(req, timeout=5).read()
except Exception:
    pass
time.sleep(1)

import psutil
for p in psutil.process_iter(['pid','cmdline']):
    try:
        cl=' '.join(p.info.get('cmdline') or [])
        if 'web\\server.py' in cl or 'web/server.py' in cl:
            w(f'kill {p.pid}')
            p.kill()
    except Exception:
        pass
time.sleep(2)
logf=open(ROOT/'logs'/'web_server_r23b.log','a',encoding='utf-8')
proc=subprocess.Popen([sys.executable,'-B','web\\server.py'], cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT,
                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
w(f'started pid={proc.pid}')
time.sleep(3)
try:
    st=status()
    w(f'new status running={st.get("running")}')
    flag.write_text('ok\n',encoding='utf-8')
except Exception as e:
    w(f'health fail {e}')
