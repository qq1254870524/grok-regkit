import json, urllib.request, time
from pathlib import Path
out = Path("matrix_runs/_pending_monitor_18r28d.txt")
keys = ("turnstile","Turnstile","force_fresh","already present","inject","fill_only","auth-error","mail_token","pre-rereg","outlook_token_cache","SSO","sso","pending-sso","fail","success","错误","密码","An error","re-register","skip_reregister","VerifyEmail","code=","hybrid")
def get(url):
    return json.load(urllib.request.urlopen(url, timeout=15))
with out.open("w", encoding="utf-8") as f:
    f.write("start\n"); f.flush()
    for i in range(60):
        try:
            st = get("http://127.0.0.1:8092/api/status")
            snap = get("http://127.0.0.1:8092/api/logs/snapshot?limit=600")
            lines = snap.get("lines") or []
            f.write(f"\n=== poll {i} running={st.get('running')} phase={st.get('phase')} ok={st.get('success')} fail={st.get('fail')} last={(st.get('last_event') or '')[:180]}\n")
            interesting = [ln for ln in lines if any(k.lower() in ln.lower() for k in keys)]
            for ln in interesting[-50:]:
                f.write(ln+"\n")
            f.write("--- raw last 15 ---\n")
            for ln in lines[-15:]:
                f.write(ln+"\n")
            f.flush()
            if not st.get("running") and i > 0:
                f.write("DONE\n"); break
        except Exception as e:
            f.write(f"ERR {e}\n"); f.flush()
        time.sleep(12)
    f.write("END\n")
print(out)
