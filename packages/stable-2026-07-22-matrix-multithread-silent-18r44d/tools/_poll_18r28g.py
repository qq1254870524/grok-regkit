import json, urllib.request, time
from pathlib import Path
out = Path("matrix_runs/_poll_18r28g.txt")
for i in range(24):
    try:
        st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=10))
        snap = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=50", timeout=10))
        lines = snap.get("lines") or []
        body = (
            json.dumps(
                {k: st.get(k) for k in [
                    "running","success","fail","session_success","session_fail",
                    "phase","last_event","job_kind","error","finished_at"
                ]},
                ensure_ascii=False,
            )
            + "\n---\n"
            + "\n".join(lines[-40:])
        )
        out.write_text(body, encoding="utf-8")
        if not st.get("running"):
            out.write_text(body + "\n\nJOB_FINISHED\n", encoding="utf-8")
            break
    except Exception as e:
        out.write_text(f"poll_err {e}\n", encoding="utf-8")
    time.sleep(15)
