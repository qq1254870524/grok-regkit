import json, os, subprocess, time, urllib.request
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
MR = ROOT / "matrix_runs"
OUT = MR / "matrix_18r29_20260719_070041"
TAG = "stable-2026-07-19-matrix-singlethread-18r29"
LOG = MR / "_agent_complete_supervisor.log"
DONE = MR / "_agent_matrix_done.flag"
SNAP = MR / "_agent_complete_snap.txt"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def board_text():
    p = MR / "_progress_board_18r29.txt"
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

def summary_cells():
    p = OUT / "summary.jsonl"
    by = {}
    if not p.exists():
        return by
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        c = r.get("cell") or "?"
        by.setdefault(c, []).append(r)
    return by

def cell_stats(rows):
    # prefer last attempt per round
    rounds = {}
    for it in rows:
        ri = it.get("round")
        prev = rounds.get(ri)
        if prev is None or (it.get("ok") and not prev.get("ok")):
            rounds[ri] = it
        elif prev is not None and it.get("finished", "") > prev.get("finished", ""):
            rounds[ri] = it
    ok = sum(1 for v in rounds.values() if v.get("ok") or v.get("class") == "pending_sso" or (v.get("pending_sso") or 0) > 0)
    succ = sum(1 for v in rounds.values() if v.get("class") == "success" or (v.get("success") or 0) > 0)
    pend = sum(1 for v in rounds.values() if v.get("class") == "pending_sso" or (v.get("pending_sso") or 0) > 0)
    return len(rounds), succ, pend, ok

def publish_done():
    state = MR / "_publish_18r29_state.txt"
    if not state.exists():
        return False
    t = state.read_text(encoding="utf-8", errors="replace")
    return "DONE publish attempt" in t

def tag_exists():
    p = subprocess.run(["git", "rev-parse", TAG], cwd=ROOT, capture_output=True, text=True)
    return p.returncode == 0

def ensure_companions():
    script = ROOT / "tools" / "_publish_companions_18r29.py"
    if script.exists():
        log("run companion publish")
        subprocess.run(["C:\\Python312\\python.exe", "-B", str(script)], cwd=ROOT)
    # mark done
    DONE.write_text(
        f"done_at={datetime.now().isoformat(timespec='seconds')}\ntag={TAG}\nreport={(OUT/'REPORT.md').exists()}\npublish={publish_done()}\n",
        encoding="utf-8",
    )
    log(f"DONE flag written {DONE}")

log("supervisor start")
last_rows = 0
stall = 0
while True:
    st = status()
    by = summary_cells()
    rows_n = sum(len(v) for v in by.values())
    board = board_text()
    report = (OUT / "REPORT.md").exists()
    parts = []
    for c, items in sorted(by.items()):
        n, succ, pend, okish = cell_stats(items)
        parts.append(f"{c}: rounds={n} success={succ} pending={pend}")
    snap = (
        f"ts={datetime.now().isoformat(timespec='seconds')}\n"
        f"running={st.get('running')} phase={st.get('phase')} session_s={st.get('session_success')} session_p={st.get('session_pending_sso')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')}\n"
        f"rows={rows_n} report={report} publish={publish_done()} tag={tag_exists()} done={DONE.exists()}\n"
        + "\n".join(parts) + "\nBOARD\n" + board
    )
    SNAP.write_text(snap, encoding="utf-8")
    if rows_n > last_rows:
        log(f"progress rows={rows_n} phase={st.get('phase')} report={report}")
        last_rows = rows_n
        stall = 0
    else:
        stall += 1
        if stall % 10 == 0:
            log(f"heartbeat rows={rows_n} stall_ticks={stall} running={st.get('running')} phase={st.get('phase')} report={report}")

    if report and publish_done():
        if not DONE.exists():
            ensure_companions()
        log("all complete")
        break
    if report and not publish_done():
        # wait auto_publish; if stuck > 15 min after report, force run
        mtime = (OUT / "REPORT.md").stat().st_mtime
        if time.time() - mtime > 900:
            log("auto_publish stuck >15m, force run")
            subprocess.run(["C:\\Python312\\python.exe", "-B", str(ROOT / "tools" / "_auto_publish_18r29.py")], cwd=ROOT)
    time.sleep(30)
