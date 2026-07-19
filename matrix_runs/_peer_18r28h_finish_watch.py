import json, time, urllib.request
from pathlib import Path
out = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28h_finish_watch.txt")
lines = []
def get(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode("utf-8", "replace"))
start = time.time()
last = ""
while time.time() - start < 240:
    try:
        st = get("http://127.0.0.1:8092/api/status")
        msg = f"t={time.strftime('%H:%M:%S')} run={st.get('running')} s={st.get('success')} f={st.get('fail')} ps={st.get('pending_sso')} phase={st.get('phase')} jf={st.get('jobs_finished')}/{st.get('jobs_started')} ev={str(st.get('last_event',''))[:160]}"
        if msg != last:
            lines.append(msg)
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            last = msg
        if not st.get("running"):
            # final logs keywords
            snap = get("http://127.0.0.1:8092/api/logs/snapshot?limit=120")
            ks = []
            for ln in snap.get("lines") or []:
                low = ln.lower() if isinstance(ln, str) else str(ln)
                if any(k in low for k in ["one login", "login_submit_done", "submit boost", "no second", "auth_error", "early_no_new", "ok immediate", "provider=outlook", "aol missing", "actual_send", "re-register result", "success", "fail", "g2a", "sub2api", "cpa", "统计", "finished"]):
                    ks.append(ln if isinstance(ln, str) else str(ln))
            Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28h_finish_keys.txt").write_text("\n".join(ks[-80:]), encoding="utf-8")
            lines.append("JOB_DONE")
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            break
    except Exception as e:
        lines.append(f"err {e}")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    time.sleep(6)
else:
    lines.append("WATCH_TIMEOUT")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
