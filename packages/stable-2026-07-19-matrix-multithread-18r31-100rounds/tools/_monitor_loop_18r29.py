import json, time, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_monitor_18r29.txt"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
API = "http://127.0.0.1:8092"

def get_status():
    try:
        with urllib.request.urlopen(API + "/api/status", timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_logs(n=20):
    try:
        with urllib.request.urlopen(API + f"/api/logs/snapshot?limit={n}", timeout=8) as r:
            j = json.loads(r.read().decode())
            return j.get("lines") or []
    except Exception as e:
        return [f"log_err={e}"]

def alive():
    try:
        out = subprocess.check_output(
            'wmic process where "CommandLine like \'%matrix_cross_run%\'" get ProcessId /value',
            shell=True, text=True, errors="replace",
        )
        return "ProcessId=" in out
    except Exception:
        return False

last_ok = -1
while True:
    rows = []
    if (OUT / "summary.jsonl").exists():
        rows = [json.loads(x) for x in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r.get("cell")].append(r)
    lines = [f"ts={datetime.now().isoformat(timespec='seconds')}", f"matrix_alive={alive()}", f"report={(OUT/'REPORT.md').exists()}"]
    st = get_status()
    lines.append(f"status running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} p={st.get('pending_sso')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:180]}")
    lines.append(f"summary_rows={len(rows)} ok={sum(1 for r in rows if r.get('ok'))} classes={dict(Counter(r.get('class') for r in rows))}")
    for cell, items in by.items():
        rounds = {}
        for it in items:
            ri = it.get("round")
            prev = rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                rounds[ri] = it
        ok = sum(1 for v in rounds.values() if v.get("ok"))
        cls = dict(Counter(v.get("class") for v in rounds.values()))
        lines.append(f"  cell {cell}: rounds={len(rounds)} ok={ok} classes={cls}")
    clog = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if clog.exists():
        lines.append("console_tail:")
        lines.extend(clog.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    lines.append("logs_tail:")
    lines.extend(get_logs(15)[-15:])
    if ALERT.exists():
        lines.append("alerts:")
        lines.extend(ALERT.read_text(encoding="utf-8", errors="replace").splitlines()[-10:])
    SNAP.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok_n = sum(1 for r in rows if r.get("ok"))
    # alert on new non-success classes
    bad = [r for r in rows if r.get("class") not in ("success", "empty_log", None) and not r.get("ok")]
    if bad:
        last = bad[-1]
        msg = f"BAD class={last.get('class')} cell={last.get('cell')} r={last.get('round')} err={str(last.get('error') or '')[:160]}"
        prev = ALERT.read_text(encoding="utf-8") if ALERT.exists() else ""
        if msg not in prev:
            with ALERT.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    if (OUT / "REPORT.md").exists() and not alive():
        with ALERT.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] COMPLETE\n")
        break
    time.sleep(20)
