import json, time, urllib.request
from pathlib import Path
root = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
root.mkdir(exist_ok=True)
out = root / "_poll_18r28h.txt"
keywords = []
start = time.time()
last_n = 0
while time.time() - start < 900:
    try:
        st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
    except Exception as e:
        st = {"error": str(e)}
    try:
        logs = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=300", timeout=5))
        lines = logs.get("lines") or []
    except Exception:
        lines = []
    interesting = [ln for ln in lines if any(k in ln for k in [
        "ONE login", "login_submit_done", "IMMEDIATE re-register", "NO second", "NO re-login",
        "submit boost", "re-register", "page_err", "auth_error", "success", "fail",
        "pending-sso", "Turnstile", "sso_len", "OK immediate", "CF/sign-in stuck",
        "click after turnstile", "web job thread"
    ])]
    tail = lines[-25:]
    blob = {
        "ts": time.strftime("%H:%M:%S"),
        "elapsed": round(time.time()-start,1),
        "status": {k: st.get(k) for k in ["running","success","fail","pending_sso","phase","last_event","job_kind","target"]},
        "interesting_tail": interesting[-40:],
        "tail": tail,
    }
    out.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    if not st.get("running") and st.get("phase") in ("finished", "idle", None) and time.time()-start > 15:
        # finished
        Path(root/"_final_18r28h.json").write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        break
    time.sleep(8)
else:
    Path(root/"_final_18r28h.json").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
print("monitor done")
