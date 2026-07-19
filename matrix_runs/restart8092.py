import time, json, urllib.request, subprocess, os, signal
from pathlib import Path

def status():
    return json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5).read().decode())

# wait up to 180s for idle
for i in range(60):
    try:
        st = status()
        if not st.get('running'):
            break
    except Exception:
        break
    time.sleep(3)

# kill only web\server.py
import psutil
killed=[]
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        cl=p.info.get('cmdline') or []
        s=' '.join(cl)
        if 'web\\server.py' in s or 'web/server.py' in s:
            p.kill(); killed.append(p.pid)
    except Exception:
        pass
Path(r'C:\Users\zhang\grok-regkit\matrix_runs\restart8092.txt').write_text(f'killed={killed}\n', encoding='utf-8')
time.sleep(2)
# start server
creationflags = 0x00000008 | 0x00000200  # DETACHED | CREATE_NEW_PROCESS_GROUP
subprocess.Popen(
    ['C:\\Python312\\python.exe','-B','web\\server.py'],
    cwd=r'C:\Users\zhang\grok-regkit',
    stdout=open(r'C:\Users\zhang\grok-regkit\logs\web8092.out.log','a',encoding='utf-8'),
    stderr=open(r'C:\Users\zhang\grok-regkit\logs\web8092.err.log','a',encoding='utf-8'),
    creationflags=creationflags,
)
# wait health
ok=False
for i in range(30):
    try:
        st=status();
        if st.get('ok') is not False:
            ok=True
            Path(r'C:\Users\zhang\grok-regkit\matrix_runs\restart8092.txt').write_text(f'killed={killed}\nok={ok}\nst={st}\n', encoding='utf-8')
            break
    except Exception as e:
        Path(r'C:\Users\zhang\grok-regkit\matrix_runs\restart8092.txt').write_text(f'killed={killed}\nwait={i}\nerr={e}\n', encoding='utf-8')
    time.sleep(1)
