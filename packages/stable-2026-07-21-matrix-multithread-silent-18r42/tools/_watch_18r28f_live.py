import json, time, urllib.request
from pathlib import Path
out = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_watch_18r28f_live.txt")
out.parent.mkdir(exist_ok=True)
t0 = time.time()
last = ""
with out.open("a", encoding="utf-8") as f:
    f.write(f"\n=== watch 18r28f start {time.strftime('%H:%M:%S')} ===\n")
    f.flush()
    while time.time() - t0 < 900:
        try:
            st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
            snap = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=40", timeout=10))
            logs = snap.get("logs") or snap.get("lines") or []
            if isinstance(logs, dict):
                logs = logs.get("items") or []
            chunk = "\n".join(str(x) for x in logs[-40:])
            line = (
                f"t+{int(time.time()-t0)}s run={st.get('running')} s={st.get('success')} f={st.get('fail')} "
                f"ps={st.get('pending_sso')} phase={st.get('phase')} last={st.get('last_event')}\n"
            )
            if chunk != last:
                f.write(line)
                f.write(chunk + "\n---\n")
                f.flush()
                last = chunk
            else:
                f.write(line)
                f.flush()
            if not st.get("running") and time.time() - t0 > 15:
                f.write("job finished\n")
                break
        except Exception as e:
            f.write(f"err {e}\n")
            f.flush()
        time.sleep(12)
