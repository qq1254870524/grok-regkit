# -*- coding: utf-8 -*-
import json, time, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
logp = OUT / "_monitor_agent_18r35.log"
board = OUT / "_PROGRESS_BOARD_18r35.md"
jsonl = OUT / "matrix_18r30_20260720_003737.jsonl"
pulse = OUT / "_live_pulse_18r35.txt"
done = OUT / "_matrix_18r35_DONE.flag"
end = time.time() + 6 * 3600
last_cells = -1
while time.time() < end:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8).read().decode("utf-8","replace"))
    except Exception as e:
        st = {"error": str(e)}
    cells = []
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            line=line.strip()
            if not line: continue
            try: cells.append(json.loads(line))
            except Exception: pass
    n = len(cells)
    pu = pulse.read_text(encoding="utf-8", errors="replace").strip() if pulse.exists() else ""
    matrix_alive = False
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command",
            "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_18r30_multithread' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=20)
        matrix_alive = int((r.stdout or "0").strip() or 0) > 0
    except Exception:
        pass
    line = (f"{ts} matrix_alive={matrix_alive} cells={n}/8 "
            f"run={st.get('running')} phase={st.get('phase')} "
            f"ok={st.get('success')} fail={st.get('fail')} pend={st.get('pending_sso')} "
            f"sess={st.get('session_success')}/{st.get('session_fail')}/{st.get('session_pending_sso')} "
            f"jobs={st.get('jobs_finished')}/{st.get('jobs_started')} | {str(st.get('last_event',''))[:120]}\n")
    with logp.open("a", encoding="utf-8") as f:
        f.write(line)
    if n != last_cells:
        last_cells = n
        with logp.open("a", encoding="utf-8") as f:
            f.write(f"{ts} CELL_CHANGE cells={n}\n")
            for c in cells:
                f.write(f"  - {c.get('cell')}: ok={c.get('success')} fail={c.get('fail')} pend={c.get('pending_sso')}\n")
    rows = "\n".join(
        f"| `{c.get('cell')}` | {c.get('success')} | {c.get('fail')} | {c.get('pending_sso')} |"
        for c in cells
    )
    board.write_text(
        f"# 18r35 Progress Board\n\nUpdated: {ts}\n\n"
        f"- matrix_alive: {matrix_alive}\n"
        f"- cells_done: {n}/8 (+pending_sso_recovery)\n"
        f"- current: run={st.get('running')} phase={st.get('phase')} ok={st.get('success')} fail={st.get('fail')} pend={st.get('pending_sso')} target={st.get('target')}\n"
        f"- session: {st.get('session_success')}/{st.get('session_fail')}/{st.get('session_pending_sso')}\n"
        f"- jobs: {st.get('jobs_finished')}/{st.get('jobs_started')}\n"
        f"- last_event: {st.get('last_event')}\n"
        f"- pulse: {pu}\n\n"
        f"## Completed cells\n\n| cell | success | fail | pending |\n|---|---:|---:|---:|\n{rows}\n",
        encoding="utf-8",
    )
    # auto-done if matrix dead and not running and cells>=8
    if (not matrix_alive) and (not st.get("running")) and n >= 8 and not done.exists():
        done.write_text(json.dumps({"ts": ts, "cells": n, "status": st}, ensure_ascii=False, indent=2), encoding="utf-8")
        with logp.open("a", encoding="utf-8") as f:
            f.write(f"{ts} WROTE DONE FLAG\n")
        break
    time.sleep(60)
