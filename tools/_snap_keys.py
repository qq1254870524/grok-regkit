import json, time, urllib.request
from pathlib import Path
time.sleep(70)
st=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5))
logs=json.load(urllib.request.urlopen('http://127.0.0.1:8092/api/logs/snapshot?limit=180',timeout=20)).get('lines') or []
Path('matrix_runs/_snap_18r28f_b.txt').write_text('\n'.join(logs),encoding='utf-8')
Path('matrix_runs/_st_18r28f.json').write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding='utf-8')
keys=['NO re-fill','NO second','get_oai_code route','AOL missing','IMMEDIATE','re-fill path','closed sign-in','still on sign-in','code=','preflight route','mail poll','hybrid] code','SSO','success','page_err','re-register','VerifyEmail','sign-up try']
out=[s[:400] for s in logs if any(k.lower() in s.lower() for k in keys)]
Path('matrix_runs/_keys_18r28f_b.txt').write_text('\n'.join(out)+'\n\nSTATUS '+json.dumps({k:st.get(k) for k in ['running','success','fail','phase','last_event']},ensure_ascii=False),encoding='utf-8')
print('wrote', len(logs), 'keys', len(out), 'run', st.get('running'), st.get('phase'))
