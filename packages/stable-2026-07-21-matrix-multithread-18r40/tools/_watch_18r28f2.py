import json, time, urllib.request
from pathlib import Path
out = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_watch_18r28f2.txt")
t0 = time.time()
last = ""
with out.open("a", encoding="utf-8") as f:
    f.write(f"\n===18r28f2 {time.strftime('%H:%M:%S')}===\n")
    f.flush()
    while time.time() - t0 < 720:
        try:
            st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
            snap = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=80", timeout=15))
            logs = snap.get("lines") or []
            chunk = "\n".join(logs[-80:])
            line = (
                f"t+{int(time.time()-t0)} run={st.get('running')} s={st.get('success')} "
                f"f={st.get('fail')} ph={st.get('phase')} last={st.get('last_event')}\n"
            )
            f.write(line)
            if chunk != last:
                f.write(chunk + "\n---\n")
                last = chunk
            f.flush()
            if (not st.get("running")) and time.time() - t0 > 25:
                f.write("done\n")
                break
        except Exception as e:
            f.write(f"err {e}\n")
            f.flush()
        time.sleep(12)
