# -*- coding: utf-8 -*-
import json, time, urllib.request
from pathlib import Path
from datetime import datetime
BASE="http://127.0.0.1:8092"
OUT=Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
rep=OUT/"_matrix_18r35_progress.jsonl"
end=time.time()+3600*8
last_ok=-1
while time.time()<end:
    try:
        with urllib.request.urlopen(BASE+"/api/status", timeout=20) as r:
            st=json.loads(r.read().decode("utf-8","replace"))
        with urllib.request.urlopen(BASE+"/api/config", timeout=20) as r:
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
            "event": (st.get("last_event") or "")[:240],
        }
        with rep.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False)+"\n")
        # also update human pulse
        (OUT/"_live_pulse_18r35.txt").write_text(
            f"{row['ts'][11:]} running={row['running']} phase={row['phase']} ok={row['ok']} fail={row['fail']} pend={row['pend']} target={row['target']} mode={row['mode']} proxy={row['proxy']} email={row['email']} workers={row['workers']} | {row['event']}\n",
            encoding="utf-8")
        # detect matrix finished: process gone + idle + report summary exists pattern
        mtx_alive=False
        try:
            import subprocess
            out=subprocess.check_output(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_18r30_multithread' } | Measure-Object | Select-Object -ExpandProperty Count"], text=True, timeout=15)
            mtx_alive=int((out or "0").strip() or 0)>0
        except Exception:
            mtx_alive=True
        if (not st.get("running")) and (not mtx_alive):
            # wait a bit for summary write
            time.sleep(20)
            if not mtx_alive:
                (OUT/"_matrix_18r35_DONE.flag").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                break
    except Exception as e:
        with rep.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "error": str(e)}, ensure_ascii=False)+"\n")
    time.sleep(60)
