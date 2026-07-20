import json, time, urllib.request
from pathlib import Path
out = Path('matrix_runs/_poll_18r28f.txt')
t0=time.time()
with out.open('w',encoding='utf-8') as f:
    while time.time()-t0 < 240:
        st=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5))
        logs=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/logs/snapshot?limit=40',timeout=15)).get('lines') or []
        f.write(f"t+{int(time.time()-t0)} run={st.get('running')} s={st.get('success')} f={st.get('fail')} ph={st.get('phase')} ev={st.get('last_event')}\n")
        for s in logs[-25:]:
            if any(k in s for k in ['get_oai_code route','code=','AOL missing','mail poll','VerifyEmail','sign-up','SSO','sso','success','fail','pending','Turnstile','NO re-fill','still on sign-in','re-fill path']):
                f.write(s[:300]+'\n')
        f.write('---\n'); f.flush()
        if not st.get('running') and time.time()-t0>15:
            f.write('JOB DONE\n'); break
        time.sleep(20)
print('done')
