# -*- coding: utf-8 -*-
from __future__ import annotations
import json, time, urllib.request
from datetime import datetime
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
LOG = OUT / "_CODEX_18r43_AGENT_KEEP.md"
STATUS = OUT / "_CODEX_18r43_AGENT_STATUS.md"

def api():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e), "running": None}

def main():
    last_ok = None
    last_change = time.time()
    while True:
        st = api()
        ok = st.get("success")
        now = datetime.now().isoformat(timespec="seconds")
        if ok is not None and ok != last_ok:
            last_ok = ok
            last_change = time.time()
        stall_min = int((time.time() - last_change) / 60)
        rem = max(0, 1000 - int(ok or 0))
        eta = int(rem / 3) if rem else 0
        alert = ""
        if stall_min >= 25 and st.get("running"):
            alert = "STALL_ALERT ok frozen %sm" % stall_min
        body = (
            "# 18r43 agent keep\nupdated=%s\n"
            "ok=%s fail=%s pend=%s await=%s run=%s phase=%s\n"
            "stall_min=%s rem~%s eta_min~%s\n%s\n"
        ) % (
            now, ok, st.get("fail"), st.get("pending_sso"), st.get("awaiting_pool"),
            st.get("running"), st.get("phase"), stall_min, rem, eta, alert,
        )
        try:
            LOG.write_text(body, encoding="utf-8")
            STATUS.write_text(body.replace("agent keep", "agent status"), encoding="utf-8")
        except Exception:
            pass
        summaries = list(OUT.glob("matrix_18r43_*_summary.json"))
        if summaries and not st.get("running"):
            try:
                LOG.write_text(body + "matrix_summary_seen exit\n", encoding="utf-8")
            except Exception:
                pass
            return
        time.sleep(60)

if __name__ == "__main__":
    main()
