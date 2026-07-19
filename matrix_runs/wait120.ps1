Start-Sleep -Seconds 120
python -B -c @"
import urllib.request,json,pathlib
m=pathlib.Path(r'C:\\Users\\zhang\\grok-regkit\\matrix_runs\\matrix_18r21_20260719_023216')
st=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/status',timeout=5).read().decode())
snap=json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/logs/snapshot',timeout=5).read().decode())
out=[]
out.append(str({k:st.get(k) for k in ['running','phase','success','fail','pending_sso','jobs_started','jobs_finished']}))
out += (snap.get('lines') or [])[-15:]
out.append('---RUNNER---')
out += (m/'runner.log').read_text(encoding='utf-8',errors='replace').splitlines()[-15:]
out.append('---SUMMARY---')
out += (m/'summary.jsonl').read_text(encoding='utf-8',errors='replace').splitlines()
pathlib.Path(r'C:\\Users\\zhang\\grok-regkit\\matrix_runs\\t2.txt').write_text('\n'.join(out),encoding='utf-8')
"@
