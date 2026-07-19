# -*- coding: utf-8 -*-
import json, time, urllib.request
from pathlib import Path
from datetime import datetime
BASE="http://127.0.0.1:8092"
OUT=Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
pulse=OUT/"_live_pulse_18r35.txt"
def get(path):
    with urllib.request.urlopen(BASE+path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8","replace"))
last_cell=""
while True:
    try:
        st=get("/api/status")
        cfg=(get("/api/config").get("config") or {})
        line=f"{datetime.now().strftime('%H:%M:%S')} running={st.get('running')} phase={st.get('phase')} ok={st.get('success')} fail={st.get('fail')} pend={st.get('pending_sso')} target={st.get('target')} mode={cfg.get('register_mode')} proxy={cfg.get('proxy_mode')} email={cfg.get('email_provider')} workers={cfg.get('workers')} | {str(st.get('last_event') or '')[:180]}"
        pulse.write_text(line+"\n", encoding="utf-8")
        # append progress log every tick
        with (OUT/"_live_pulse_18r35.log").open("a", encoding="utf-8") as f:
            f.write(line+"\n")
        # stop when matrix process gone and idle for a while after flag
        if (OUT/"_ALL_PAUSED.flag").exists() and not st.get("running"):
            # keep watching unless matrix still writing
            pass
    except Exception as e:
        pulse.write_text(f"ERR {e}\n", encoding="utf-8")
    time.sleep(15)
