# -*- coding: utf-8 -*-
"""Background pulse for 18r43 matrix - writes every 30s for up to 36h."""
from __future__ import annotations
import json, time, urllib.request
from datetime import datetime
from pathlib import Path
OUT = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
LOG = OUT / "_CODEX_18r43_PULSE.jsonl"
MD = OUT / "_CODEX_18r43_PULSE.md"
PID = OUT / "_pulse_18r43.pid"
PID.write_text(str(__import__("os").getpid()), encoding="utf-8")

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e), "running": None}

def main():
    for i in range(4320):  # 36h * 120
        st = status()
        row = {
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "ok": st.get("success"),
            "fail": st.get("fail"),
            "pend": st.get("pending_sso"),
            "await": st.get("awaiting_pool"),
            "phase": st.get("phase"),
            "run": st.get("running"),
            "jobs_started": st.get("jobs_started"),
            "jobs_finished": st.get("jobs_finished"),
            "err": st.get("error") or st.get("error"),
        }
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        MD.write_text(
            f"# 18r43 pulse\nupdated={row['ts']}\n"
            f"ok={row['ok']} fail={row['fail']} pend={row['pend']} await={row['await']} "
            f"phase={row['phase']} run={row['run']} jobs={row['jobs_started']}/{row['jobs_finished']}\n",
            encoding="utf-8",
        )
        # stop if summary exists and idle
        if list(OUT.glob("matrix_18r43_*_summary.json")) and not st.get("running"):
            break
        time.sleep(30)

if __name__ == "__main__":
    main()
