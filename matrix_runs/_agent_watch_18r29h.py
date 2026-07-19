# -*- coding: utf-8 -*-
import json, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_agent_complete_snap.txt"
BOARD = ROOT / "matrix_runs" / "_progress_board_18r29.txt"
CONSOLE = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"

def get(url):
    with urllib.request.urlopen(url, timeout=6) as r:
        return r.read().decode("utf-8", "replace")

def board_text():
    sj = OUT / "summary.jsonl"
    if not sj.exists():
        return "no summary"
    from collections import Counter, defaultdict
    cells = defaultdict(list)
    for line in sj.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        cells[r.get("cell") or "?"].append(r)
    lines = []
    ge10 = 0
    for c, rows in cells.items():
        ctr = Counter(x.get("class") for x in rows)
        ok = sum(1 for x in rows if x.get("ok") or x.get("class") in ("success", "pending_sso"))
        n = len(rows)
        if n >= 10:
            ge10 += 1
        lines.append(f"{c}: {n}/10 ok={ok} {dict(ctr)}")
    lines.append(f"rows={sum(len(v) for v in cells.values())} cells_ge10={ge10} report={(OUT/'REPORT.md').exists()}")
    return "\n".join(lines)

while True:
    try:
        st = json.loads(get("http://127.0.0.1:8092/api/status"))
    except Exception as e:
        st = {"error": str(e)}
    b = board_text()
    try:
        BOARD.write_text(b + "\n", encoding="utf-8")
    except Exception:
        pass
    ts = datetime.now().isoformat(timespec="seconds")
    snap = f"ts={ts}\nSTATUS={json.dumps(st, ensure_ascii=False)}\nBOARD\n{b}\n"
    if CONSOLE.exists():
        tail = "\n".join(CONSOLE.read_text(encoding="utf-8", errors="replace").splitlines()[-15:])
        snap += "CONSOLE\n" + tail + "\n"
    SNAP.write_text(snap, encoding="utf-8")
    if (OUT / "REPORT.md").exists() and (ROOT / "matrix_runs" / "_agent_matrix_done.flag").exists():
        break
    # also stop if matrix processes gone and report exists
    if (OUT / "REPORT.md").exists():
        time.sleep(30)
        continue
    time.sleep(20)
