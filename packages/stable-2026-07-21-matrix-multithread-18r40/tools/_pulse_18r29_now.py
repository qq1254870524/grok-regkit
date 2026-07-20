from __future__ import annotations
import json, os, time, urllib.request
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
PULSE = ROOT / "matrix_runs" / "_final_pulse_18r29.txt"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

CELLS_EXPECTED = []
for mode in ("hybrid", "browser"):
    for proxy in ("direct", "socks5_list"):
        for mail in ("outlook", "aol"):
            CELLS_EXPECTED.append(f"{mode}__{proxy}__{mail}")
CELLS_EXPECTED += ["pending_sso_recovery__socks5_list", "pending_sso_recovery__direct"]

def api_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def best_rounds(rows):
    by = defaultdict(dict)
    for r in rows:
        c = r.get("cell") or "?"
        ri = r.get("round")
        prev = by[c].get(ri)
        if prev is None or (r.get("ok") and not prev.get("ok")):
            by[c][ri] = r
    return by

def load_rows():
    p = OUT / "summary.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def write_pulse(note=""):
    rows = load_rows()
    by = best_rounds(rows)
    st = api_status()
    lines = [
        f"ts={datetime.now().isoformat(timespec='seconds')}",
        f"out={OUT}",
        f"report={ (OUT/'REPORT.md').exists() }",
        f"summary_rows={len(rows)}",
        f"api_running={st.get('running')} phase={st.get('phase')} sess_ok={st.get('session_success')} sess_fail={st.get('session_fail')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')}",
        f"last_event={(st.get('last_event') or '')[:220]}",
        "cells:",
    ]
    done_ok = 0
    total_need = 0
    for c in CELLS_EXPECTED:
        need = 10
        total_need += need
        rounds = by.get(c, {})
        ok = sum(1 for v in rounds.values() if v.get("ok"))
        fail = sum(1 for v in rounds.values() if not v.get("ok"))
        done_ok += ok
        cls = Counter((v.get("class") or "?") for v in rounds.values())
        lines.append(f"  {c}: best_rounds={len(rounds)}/{need} ok={ok} fail_entries={fail} classes={dict(cls)}")
    # current cell guess: last unfinished or last in summary
    cur = ""
    if rows:
        cur = f"{rows[-1].get('cell')} r{rows[-1].get('round')} class={rows[-1].get('class')}"
    lines.append(f"last_summary={cur}")
    lines.append(f"progress_ok_approx={done_ok}/{total_need}")
    if note:
        lines.append(f"note={note}")
    # stall: summary mtime
    sj = OUT / "summary.jsonl"
    if sj.exists():
        age = time.time() - sj.stat().st_mtime
        lines.append(f"summary_age_s={int(age)}")
        if age > 900 and st.get("running"):
            lines.append("WARN=summary_stale_but_api_running")
        if age > 900 and not st.get("running"):
            lines.append("ALERT=possible_matrix_stall")
            with ALERT.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat(timespec='seconds')}] stall summary_age={age} running={st.get('running')}\n")
    text = "\n".join(lines) + "\n"
    PULSE.write_text(text, encoding="utf-8")
    print(text, flush=True)
    return text

if __name__ == "__main__":
    # single shot if no loop arg
    import sys
    loop = "--loop" in sys.argv
    while True:
        write_pulse()
        if (OUT / "REPORT.md").exists():
            write_pulse(note="REPORT_READY")
            break
        if not loop:
            break
        time.sleep(45)
