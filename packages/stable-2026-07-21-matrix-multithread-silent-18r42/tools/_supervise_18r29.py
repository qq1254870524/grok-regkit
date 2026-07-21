import json, time, urllib.request, subprocess, re
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
PROG = ROOT / "matrix_runs" / "_progress_18r29.json"
API = "http://127.0.0.1:8092"
last_phase = None
last_phase_ts = time.time()
stuck_n = 0

def api_get(path, timeout=8):
    with urllib.request.urlopen(API+path, timeout=timeout) as r:
        return json.loads(r.read().decode())

def matrix_alive():
    try:
        out = subprocess.check_output(
            'wmic process where "CommandLine like \'%matrix_cross_run%\'" get ProcessId /value',
            shell=True, text=True, errors="replace",
        )
        return any(x.strip().startswith("ProcessId=") for x in out.splitlines())
    except Exception:
        return False

def append_alert(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n"
    with ALERT.open("a", encoding="utf-8") as f:
        f.write(line)

while True:
    now = datetime.now().isoformat(timespec="seconds")
    st = {}
    try:
        st = api_get("/api/status")
    except Exception as e:
        append_alert(f"status_err={e}")
        st = {}

    phase = f"{st.get('phase')}|{st.get('last_event','')[:80]}"
    if phase != last_phase:
        last_phase = phase
        last_phase_ts = time.time()
        stuck_n = 0
    else:
        stuck_s = time.time() - last_phase_ts
        # waiting_code can be long; sign-up/turnstile stuck > 180s is bad
        lim = 240 if (st.get("phase") or "") in ("waiting_code", "verify_code", "mail_poll") else 180
        if st.get("running") and stuck_s > lim:
            stuck_n += 1
            if stuck_n in (1, 3, 6):
                append_alert(f"STUCK phase={st.get('phase')} for {int(stuck_s)}s event={(st.get('last_event') or '')[:200]}")

    rows = []
    if (OUT / "summary.jsonl").exists():
        rows = [json.loads(x) for x in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

    by_cell = defaultdict(list)
    for r in rows:
        by_cell[r.get("cell")].append(r)
    cell_prog = {}
    for c, items in by_cell.items():
        # count unique rounds with ok success preferred
        rounds = {}
        for it in items:
            ri = it.get("round")
            prev = rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                rounds[ri] = it
        ok = sum(1 for v in rounds.values() if v.get("ok"))
        classes = dict(Counter(v.get("class") for v in rounds.values()))
        cell_prog[c] = {"rounds_done": len(rounds), "ok": ok, "classes": classes}

    prog = {
        "ts": now,
        "running": st.get("running"),
        "phase": st.get("phase"),
        "event": (st.get("last_event") or "")[:200],
        "session_success": st.get("session_success"),
        "matrix_alive": matrix_alive(),
        "summary_rows": len(rows),
        "ok_rows": sum(1 for r in rows if r.get("ok")),
        "classes": dict(Counter(r.get("class") for r in rows)),
        "cells": cell_prog,
        "report_ready": (OUT / "REPORT.md").exists(),
    }
    PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

    if prog["report_ready"] and not prog["matrix_alive"]:
        append_alert("MATRIX_COMPLETE report ready")
        break
    if not prog["matrix_alive"] and not st.get("running") and len(rows) > 0 and not prog["report_ready"]:
        append_alert("MATRIX_DEAD without REPORT — needs resume")
        # don't break forever; keep watching in case restarted
        time.sleep(30)
        continue
    time.sleep(25)
