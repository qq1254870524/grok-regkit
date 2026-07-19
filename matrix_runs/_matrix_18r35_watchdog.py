# -*- coding: utf-8 -*-
"""18r35 cell completion monitor: sample every 45s, flag issues, write progress."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path
from datetime import datetime
BASE="http://127.0.0.1:8092"
OUT=Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
prog=OUT/"_matrix_18r35_progress.jsonl"
issues=OUT/"_matrix_18r35_issues.jsonl"
pulse=OUT/"_live_pulse_18r35.txt"
last_ok=None
stall=0
end=time.time()+3600*10
while time.time()<end:
    try:
        with urllib.request.urlopen(BASE+"/api/status", timeout=12) as r:
            st=json.loads(r.read().decode("utf-8","replace"))
        with urllib.request.urlopen(BASE+"/api/config", timeout=12) as r:
            cfg=(json.loads(r.read().decode("utf-8","replace")).get("config") or {})
        row={
            "ts": datetime.now().isoformat(timespec="seconds"),
            "running": st.get("running"),
            "phase": st.get("phase"),
            "ok": st.get("success"),
            "fail": st.get("fail"),
            "pend": st.get("pending_sso"),
            "skip": st.get("skipped"),
            "target": st.get("target"),
            "mode": cfg.get("register_mode"),
            "proxy": cfg.get("proxy_mode"),
            "email": cfg.get("email_provider"),
            "workers": cfg.get("workers"),
            "event": (st.get("last_event") or "")[:300],
        }
        with prog.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False)+"\n")
        pulse.write_text(
            f"{row['ts'][11:]} running={row['running']} phase={row['phase']} ok={row['ok']} fail={row['fail']} pend={row['pend']} skip={row['skip']} target={row['target']} mode={row['mode']} proxy={row['proxy']} email={row['email']} workers={row['workers']} | {row['event']}\n",
            encoding="utf-8")
        ok=int(row["ok"] or 0)
        if last_ok is not None and ok==last_ok and st.get("running"):
            stall += 1
        else:
            stall = 0
        last_ok = ok
        # issue heuristics
        ev=(row["event"] or "").lower()
        if any(x in ev for x in ["traceback", "exception", "source_file", "forbidden", "server action not found"]):
            with issues.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False)+"\n")
        if stall >= 40:  # ~30min no success growth
            with issues.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts":row["ts"],"type":"stall","row":row}, ensure_ascii=False)+"\n")
            stall=0
        # matrix finished?
        import subprocess
        try:
            out=subprocess.check_output([
                "powershell","-NoProfile","-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_18r30_multithread' } | Measure-Object).Count"
            ], text=True, timeout=20)
            alive=int((out or "0").strip() or 0)>0
        except Exception:
            alive=True
        if (not st.get("running")) and (not alive):
            time.sleep(15)
            (OUT/"_matrix_18r35_DONE.flag").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            break
    except Exception as e:
        with issues.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "error": str(e)}, ensure_ascii=False)+"\n")
    time.sleep(45)
