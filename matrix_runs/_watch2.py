import json, urllib.request, time
from pathlib import Path
out = Path("matrix_runs/_pending_watch2.txt")
def get(u):
    return json.load(urllib.request.urlopen(u, timeout=15))
with out.open("w", encoding="utf-8") as f:
  for i in range(50):
    st=get("http://127.0.0.1:8092/api/status")
    snap=get("http://127.0.0.1:8092/api/logs/snapshot?limit=700")
    lines=snap.get("lines") or []
    # only lines after 05:12
    recent=[ln for ln in lines if ln.startswith("[05:1") or ln.startswith("[05:2") or ln.startswith("[05:3") or ln.startswith("[06:")]
    keys=("force_fresh","cleared for force","already present","outlook_token_cache","pre-rereg","mail_token","turnstile OK","bad_password","auth_error","re-register","SSO","sso len","success","fail","VerifyEmail","code=","错误","An error","skip_reregister","hybrid")
    inter=[ln for ln in recent if any(k.lower() in ln.lower() for k in keys)]
    f.write(f"poll{i} run={st.get('running')} phase={st.get('phase')} ok={st.get('success')} fail={st.get('fail')} last={(st.get('last_event') or '')[:160]}\n")
    for ln in inter[-40:]:
      f.write(ln+"\n")
    f.write("--raw--\n")
    for ln in recent[-12:]:
      f.write(ln+"\n")
    f.write("\n"); f.flush()
    if not st.get("running") and i>1:
      f.write("DONE\n"); break
    time.sleep(15)
print("done", out)
