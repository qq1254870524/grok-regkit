import json, time, urllib.request
from pathlib import Path
out = Path('matrix_runs/_watch_18r28e.txt')
def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read().decode('utf-8', 'replace')
def post(url, data=b'{}'):
    req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', 'replace')
lines_acc=[]
def log(s):
    lines_acc.append(s)
    out.write_text('\n'.join(lines_acc[-400:]), encoding='utf-8')
    print(s, flush=True)

# ensure job running
try:
    st=json.loads(get('http://127.0.0.1:8092/api/status'))
except Exception as e:
    log(f'status err {e}'); st={}
if not st.get('running'):
    log('restarting pending recover count=2')
    try:
        log(post('http://127.0.0.1:8092/api/pending-sso/recover', b'{"count":2}'))
    except Exception as e:
        log(f'start err {e}')
    time.sleep(3)

keys=('IMMEDIATE','preflight route','closed sign-in','STOP further','AOL missing','Outlook pre-login','auth_error','re-register','mail_token','Turnstile','forced_email','success','fail','sign-up','VerifyEmail','sso')
seen=set(); t0=time.time()
while time.time()-t0 < 420:
    try:
        st=json.loads(get('http://127.0.0.1:8092/api/status'))
        snap=json.loads(get('http://127.0.0.1:8092/api/logs/snapshot?limit=300'))
        interesting=[]
        for ln in snap.get('lines') or []:
            if any(k.lower() in ln.lower() for k in keys):
                if ln not in seen:
                    seen.add(ln); interesting.append(ln)
        if interesting:
            log(f'--- t+{int(time.time()-t0)}s status running={st.get("running")} succ={st.get("success")} fail={st.get("fail")} phase={st.get("phase")} last={st.get("last_event")}')
            for ln in interesting[-40:]:
                log(ln)
        elif int(time.time()-t0) % 30 < 8:
            log(f'heartbeat t+{int(time.time()-t0)}s running={st.get("running")} last={st.get("last_event")}')
        if not st.get('running') and time.time()-t0>15:
            log(f'JOB DONE {json.dumps(st, ensure_ascii=False)[:500]}')
            # dump final interesting
            for ln in (snap.get('lines') or [])[-80:]:
                log('FINAL|'+ln)
            break
    except Exception as e:
        log(f'poll {e}')
    time.sleep(8)
else:
    log('watch timeout')
log('watch exit')
