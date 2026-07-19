# -*- coding: utf-8 -*-
"""Watch matrix until REPORT; if matrix dies, resume remaining cells into SAME OUT."""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_agent_guardian_18r29j.txt"
DONE = ROOT / "matrix_runs" / "_agent_matrix_done.flag"
BASE = "http://127.0.0.1:8092"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(ROOT / "tools"))

# Import matrix helpers
import matrix_cross_run as mcr  # type: ignore

def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with SNAP.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def api(method, path, body=None, timeout=30):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw

def matrix_alive() -> bool:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'matrix_cross_run' } | "
             "Select-Object -ExpandProperty ProcessId"],
            text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        return bool(out.strip())
    except Exception:
        return False

def board():
    cells = defaultdict(list)
    sj = OUT / "summary.jsonl"
    if sj.exists():
        for line in sj.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            cells[r.get("cell") or "?"].append(r)
    return cells

def write_report(cells):
    # reuse matrix_cross_run write if available
    if hasattr(mcr, "write_report"):
        try:
            mcr.write_report(cells if not isinstance(cells, dict) else None)
        except Exception:
            pass
    # always write simple REPORT
    lines = ["# Matrix 18r29 REPORT", f"generated={datetime.now().isoformat(timespec='seconds')}", ""]
    ge = 0
    for c, rows in sorted(cells.items()):
        n = len(rows)
        if n >= 10:
            ge += 1
        ctr = Counter(x.get("class") for x in rows)
        ok = sum(1 for x in rows if x.get("ok") or x.get("class") in ("success", "pending_sso"))
        lines.append(f"- **{c}**: {n}/10 okish={ok} {dict(ctr)}")
    lines.append("")
    lines.append(f"cells_ge10={ge} total_rows={sum(len(v) for v in cells.values())}")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote REPORT cells_ge10={ge}")

def remaining_plan(cells):
    plan = []
    # rebuild CELLS same as matrix_cross_run
    # force re-init of CELLS
    if not getattr(mcr, "CELLS", None):
        # execute cell build by importing module side effects - CELLS filled at import
        pass
    for cell in mcr.CELLS:
        name = cell["name"]
        done_n = len(cells.get(name, []))
        need = max(0, 10 - done_n)
        for i in range(need):
            plan.append((cell, done_n + i + 1))
    return plan

def append_summary(row: dict):
    with (OUT / "summary.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def run_one_into_out(cell, round_i):
    """Run one matrix cell using matrix_cross_run.run_one but force OUT."""
    # temporarily point mcr.OUT
    old_out = mcr.OUT
    mcr.OUT = OUT
    mcr.SUMMARY = OUT / "summary.jsonl"
    mcr.REPORT = OUT / "REPORT.md"
    try:
        # run_one expects (cell, round_i) or similar - inspect
        fn = mcr.run_one
        import inspect
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        if len(params) >= 2:
            return fn(cell, round_i)
        return fn(cell)
    finally:
        mcr.OUT = old_out

def ensure_web():
    try:
        api("GET", "/api/status")
        return True
    except Exception:
        log("web down, restart 8092")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "tools" / "start_web8092_hidden.ps1")],
            cwd=str(ROOT),
        )
        time.sleep(5)
        try:
            api("GET", "/api/status")
            return True
        except Exception as e:
            log(f"web still down: {e}")
            return False

def main():
    log(f"guardian start OUT={OUT}")
    idle_dead = 0
    while True:
        if DONE.exists() and (OUT / "REPORT.md").exists():
            log("already done")
            break
        cells = board()
        ge = sum(1 for c, rows in cells.items() if len(rows) >= 10)
        alive = matrix_alive()
        try:
            _, st = api("GET", "/api/status")
            running = bool(st.get("running"))
            phase = st.get("phase")
            evt = st.get("last_event")
        except Exception as e:
            running = False
            phase = "?"
            evt = str(e)
            ensure_web()
        log(f"alive={alive} running={running} phase={phase} ge10={ge} rows={sum(len(v) for v in cells.values())} evt={str(evt)[:120]}")
        (ROOT / "matrix_runs" / "_progress_board_18r29.txt").write_text(
            "\n".join(f"{c}: {len(rows)}/10 {dict(Counter(x.get('class') for x in rows))}" for c, rows in sorted(cells.items()))
            + f"\nrows={sum(len(v) for v in cells.values())} cells_ge10={ge} report={(OUT/'REPORT.md').exists()}\n",
            encoding="utf-8",
        )

        # success path: original matrix finishes REPORT
        if (OUT / "REPORT.md").exists():
            log("REPORT exists, wait publish")
            # wait up to 15 min for publish flag
            for _ in range(90):
                if DONE.exists():
                    log("DONE flag present")
                    return
                # check packages
                pkg = ROOT / "packages" / "stable-2026-07-19-matrix-singlethread-18r29.zip"
                if pkg.exists():
                    DONE.write_text(f"published {datetime.now().isoformat()}\n", encoding="utf-8")
                    log("package found, wrote DONE")
                    return
                time.sleep(10)
            log("publish slow; keep waiting next loop")
            time.sleep(20)
            continue

        if alive:
            idle_dead = 0
            time.sleep(25)
            continue

        # matrix dead
        idle_dead += 1
        log(f"matrix dead tick={idle_dead}")
        if running:
            # let job finish
            time.sleep(20)
            continue
        if idle_dead < 2:
            time.sleep(15)
            continue

        # resume remaining into same OUT
        plan = remaining_plan(cells)
        log(f"resume plan remaining={len(plan)}")
        if not plan:
            write_report(board())
            continue

        ensure_web()
        for cell, round_i in plan:
            if matrix_alive():
                log("original matrix revived, stop resume")
                break
            name = cell["name"]
            log(f"RESUME {name} r{round_i}/10")
            try:
                # Prefer mcr.run_one
                if hasattr(mcr, "run_one"):
                    # monkeypatch OUT
                    mcr.OUT = OUT
                    mcr.SUMMARY = OUT / "summary.jsonl"
                    # many versions: run_one(cell_dict, round_i)
                    try:
                        mcr.run_one(cell, round_i)
                    except TypeError:
                        mcr.run_one(cell)
                else:
                    log("no run_one")
                    break
            except Exception as e:
                log(f"resume error {name} r{round_i}: {e}")
            cells = board()
        # after plan attempt write report if all ge10
        cells = board()
        names = {c["name"] for c in mcr.CELLS}
        if all(len(cells.get(n, [])) >= 10 for n in names):
            write_report(cells)
        time.sleep(5)

if __name__ == "__main__":
    main()
