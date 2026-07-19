import time, json, urllib.request, traceback
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "matrix_18r29_20260719_070041"
sj = out / "summary.jsonl"
pulse = root / "_agent_pulse_18r29.txt"
mile = root / "_milestones_18r29.txt"
logf = root / "matrix_runs" / "matrix_18r29_monitor_loop.log"

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def load_rows():
    if not sj.exists():
        return []
    rows = []
    for ln in sj.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    return rows

def cell_stats(rows):
    by = defaultdict(list)
    for r in rows:
        by[r.get("cell")].append(r)
    parts = []
    for cell, items in sorted(by.items()):
        c = Counter(x.get("class") for x in items)
        ok = sum(1 for x in items if x.get("ok"))
        parts.append(f"{cell}:n={len(items)}/ok={ok}/{dict(c)}")
    return " | ".join(parts)

seen_n = 0
last_report = False
while True:
    try:
        rows = load_rows()
        st = status()
        n = len(rows)
        last = rows[-1] if rows else {}
        report = (out / "REPORT.md").exists()
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] n={n} "
            f"last={last.get('cell')} r={last.get('round')} class={last.get('class')} "
            f"sess_s={st.get('session_success')} p={st.get('session_pending_sso')} f={st.get('session_fail')} "
            f"run={st.get('running')} phase={st.get('phase')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')} "
            f"report={report} evt={(st.get('last_event') or st.get('error') or '')[:160]}"
        )
        stats = cell_stats(rows)
        body = line + "\n" + stats + "\n"
        pulse.write_text(body, encoding="utf-8")
        with logf.open("a", encoding="utf-8") as f:
            f.write(body + "\n")
        if n > seen_n:
            with mile.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                if last:
                    f.write("  ROW " + json.dumps(last, ensure_ascii=False) + "\n")
            seen_n = n
        if report and not last_report:
            with mile.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] REPORT.md READY\n")
            last_report = True
            # keep looping a bit more for publish state
        time.sleep(20)
    except Exception:
        with logf.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        time.sleep(30)
