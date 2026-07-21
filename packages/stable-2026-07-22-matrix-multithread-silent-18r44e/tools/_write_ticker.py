from pathlib import Path
Path("_tmp_ticker.py").write_text(r'''# -*- coding: utf-8 -*-
import json, time, urllib.request
from datetime import datetime
from pathlib import Path
BASE = "http://127.0.0.1:8092"
out = Path(r"C:/Users/zhang/grok-regkit/matrix_runs/_ticker_18r43.jsonl")
for i in range(120):
    try:
        st = json.loads(urllib.request.urlopen(BASE + "/api/status", timeout=10).read().decode())
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "ok": st.get("success"),
            "fail": st.get("fail"),
            "pend": st.get("pending_sso"),
            "await": st.get("awaiting_pool"),
            "phase": st.get("phase"),
            "run": st.get("running"),
            "evt": str(st.get("last_event") or "")[:120],
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "err": str(e)}, ensure_ascii=False) + "\n")
    time.sleep(30)
''', encoding="utf-8")
import subprocess, sys
p = subprocess.Popen([sys.executable, "-B", "_tmp_ticker.py"], cwd=r"C:\Users\zhang\grok-regkit", creationflags=0x08000000)
print("ticker", p.pid)
