import json, time, urllib.request
from pathlib import Path
start=time.time(); st={}
while time.time()-start < 720:
    try:
        st=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/status', timeout=5))
    except Exception as e:
        st={'error':str(e),'running':True}
    line=f"t={time.strftime('%H:%M:%S')} run={st.get('running')} ok={st.get('success')} fail={st.get('fail')} phase={st.get('phase')} ev={str(st.get('last_event'))[:120]}"
    print(line, flush=True)
    Path('matrix_runs/_wait_18r28h_py.txt').write_text(line+'\n'+json.dumps(st,ensure_ascii=False), encoding='utf-8')
    if (not st.get('running')) and st.get('phase')=='finished' and time.time()-start>8:
        break
    time.sleep(15)
try:
    logs=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/logs/snapshot?limit=500', timeout=10))
except Exception:
    logs={'lines':[]}
keys=('ONE login','login_submit_done','IMMEDIATE','NO re-login','submit boost','page_err','re-register','auth_error','OK immediate','sso_len','web job thread','CF/sign-in','pending_sso 恢复')
hits=[ln for ln in (logs.get('lines') or []) if any(k in ln for k in keys)]
Path('matrix_runs/_hits_18r28h.txt').write_text('\n'.join(hits[-150:]), encoding='utf-8')
Path('matrix_runs/_status_final_18r28h.txt').write_text(json.dumps(st,ensure_ascii=False,indent=2), encoding='utf-8')
print('MONITOR_EXIT', flush=True)
