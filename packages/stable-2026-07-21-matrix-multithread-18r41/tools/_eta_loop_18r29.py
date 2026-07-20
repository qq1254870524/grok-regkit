import json, time, urllib.request
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_monitor_18r29.txt"
PROG = ROOT / "matrix_runs" / "_eta_18r29.txt"
CELLS_REG = 8
ROUNDS = 10
PENDING_CELLS = 2
PENDING_ROUNDS = 10
TARGET = CELLS_REG * ROUNDS + PENDING_CELLS * PENDING_ROUNDS  # approx unique ok rounds goal

while True:
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8).read())
    except Exception as e:
        st = {"error": str(e)}
    rows = []
    if (OUT / "summary.jsonl").exists():
        rows = [json.loads(x) for x in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r.get("cell")].append(r)
    # unique successful rounds
    ok_unique = 0
    cell_lines = []
    for c, items in by.items():
        rounds = {}
        for it in items:
            ri = it.get("round")
            prev = rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                rounds[ri] = it
        ok = sum(1 for v in rounds.values() if v.get("ok"))
        ok_unique += ok
        cell_lines.append(f"  {c}: {ok}/{len(rounds)} ok classes={dict(Counter(v.get('class') for v in rounds.values()))}")
    classes = dict(Counter(r.get("class") for r in rows))
    done_est = ok_unique
    remain = max(0, TARGET - done_est)
    # rough 130s per round
    eta_min = remain * 130 / 60.0
    lines = [
        f"ts={datetime.now().isoformat(timespec='seconds')}",
        f"running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:160]}",
        f"summary_rows={len(rows)} classes={classes}",
        f"ok_unique_rounds≈{ok_unique} target≈{TARGET} remain≈{remain} eta_min≈{eta_min:.1f}",
        f"report={(OUT/'REPORT.md').exists()}",
    ] + cell_lines
    clogp = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if clogp.exists():
        lines.append("console_tail:")
        lines.extend(clogp.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    text = "\n".join(lines) + "\n"
    SNAP.write_text(text, encoding="utf-8")
    PROG.write_text(text, encoding="utf-8")
    if (OUT / "REPORT.md").exists():
        break
    time.sleep(45)
