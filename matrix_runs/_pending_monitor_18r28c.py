import json, urllib.request, time
from pathlib import Path
out = Path("matrix_runs/_pending_monitor_18r28c.txt")
out.parent.mkdir(parents=True, exist_ok=True)
def get(url):
    return json.load(urllib.request.urlopen(url, timeout=12))
keys = ("turnstile","Turnstile","inject","fill_only","auth-error","SSO","sso","pending-sso","fail","success","cloudflare","bad_password","auth_error","re-register","mail_token","error occurred","错误","密码","登录")
with out.open("w", encoding="utf-8") as f:
    f.write("start\n"); f.flush()
    for i in range(40):
        try:
            st = get("http://127.0.0.1:8092/api/status")
            snap = get("http://127.0.0.1:8092/api/logs/snapshot?limit=500")
            lines = snap.get("lines") or []
            f.write(f"\n=== poll {i} running={st.get('running')} phase={st.get('phase')} ok={st.get('success')} fail={st.get('fail')} pending={st.get('pending_sso')} last={(st.get('last_event') or '')[:160]}\n")
            interesting = [ln for ln in lines if any(k.lower() in ln.lower() for k in keys)]
            for ln in interesting[-40:]:
                f.write(ln + "\n")
            f.write("--- raw last 12 ---\n")
            for ln in lines[-12:]:
                f.write(ln + "\n")
            f.flush()
            if not st.get("running") and i > 0:
                f.write("DONE\n"); break
        except Exception as e:
            f.write(f"ERR {e}\n"); f.flush()
        time.sleep(10)
    f.write("END\n")
print(str(out))
