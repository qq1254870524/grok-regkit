import json, urllib.request, time
from pathlib import Path
out = Path("matrix_runs/_poll_18r28g2.txt")
for i in range(40):
    try:
        st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=10))
        snap = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=60", timeout=10))
        lines = snap.get("lines") or []
        interesting = [l for l in lines if any(k in l for k in [
            "NO second","IMMEDIATE","auth_error","re-register","get_oai_code route",
            "AOL missing","OK immediate","success","fail","login failed","re-fill","inject-only",
            "sign-up try","Turnstile","Outlook code","AOL code","pending_sso 恢复结束","click after turnstile"
        ])]
        body = json.dumps({k: st.get(k) for k in [
            "running","success","fail","session_success","session_fail","phase","last_event","job_kind"
        ]}, ensure_ascii=False) + "\n---keys---\n" + "\n".join(interesting[-40:]) + "\n---tail---\n" + "\n".join(lines[-20:])
        out.write_text(body, encoding="utf-8")
        if not st.get("running") and st.get("phase") == "finished":
            out.write_text(body + "\nJOB_FINISHED\n", encoding="utf-8")
            break
    except Exception as e:
        out.write_text(f"err {e}\n", encoding="utf-8")
    time.sleep(20)
