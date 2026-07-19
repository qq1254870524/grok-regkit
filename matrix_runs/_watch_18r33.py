import json, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
BASE = "http://127.0.0.1:8092"
progress = OUT / "_progress_agent_18r33.txt"
live = OUT / "_progress_live_18r33.txt"
def get(path):
    with urllib.request.urlopen(BASE+path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8","replace"))
n=0
while True:
    n+=1
    try:
        st=get("/api/status")
        line=f"[{datetime.now().strftime('%H:%M:%S')}] #{n} running={st.get('running')} ok={st.get('success')}/{st.get('target')} fail={st.get('fail')} pend={st.get('pending_sso')} phase={st.get('phase')} last={st.get('last_event')}"
    except Exception as e:
        line=f"[{datetime.now().strftime('%H:%M:%S')}] #{n} status_err={e}"
    with progress.open("a", encoding="utf-8") as f:
        f.write(line+"\n")
    live.write_text(line+"\n", encoding="utf-8")
    try:
        lines=progress.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines)>200:
            progress.write_text("\n".join(lines[-200:])+"\n", encoding="utf-8")
    except Exception:
        pass
    time.sleep(45)
