import time, json, urllib.request, traceback
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "matrix_18r29_20260719_070041"
sj = out / "summary.jsonl"
logp = root / "matrix_runs" / "_hour_monitor_18r29.log"
alert = root / "matrix_runs" / "_alerts_18r29.txt"
pulse = root / "_agent_pulse_18r29.txt"
last_n = 0
last_change = time.time()
start = time.time()

def status():
    try:
        return json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
    except Exception as e:
        return {"error": str(e)}

def rows():
    if not sj.exists():
        return []
    return [json.loads(x) for x in sj.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]

def cells(rs):
    by = defaultdict(list)
    for r in rs:
        by[r.get("cell")].append(r)
    outm = {}
    for c, items in by.items():
        best = {}
        for it in items:
            ri = it.get("round")
            prev = best.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                best[ri] = it
        outm[c] = {
            "ok": sum(1 for v in best.values() if v.get("ok")),
            "n": len(best),
            "cls": dict(Counter(v.get("class") for v in best.values())),
        }
    return outm

# run up to 4 hours
while time.time() - start < 4 * 3600:
    try:
        rs = rows()
        st = status()
        n = len(rs)
        if n > last_n:
            last_n = n
            last_change = time.time()
        age = time.time() - last_change
        cm = cells(rs)
        last = rs[-1] if rs else {}
        report = (out / "REPORT.md").exists()
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] n={n} age={int(age)}s "
            f"last={last.get('cell')} r={last.get('round')} cls={last.get('class')} "
            f"sess={st.get('session_success')}/{st.get('session_fail')}/p{st.get('session_pending_sso')} "
            f"run={st.get('running')} phase={st.get('phase')} report={report} "
            f"evt={(st.get('last_event') or st.get('error') or '')[:140]}"
        )
        parts = [f"{c}:{v['ok']}/{v['n']}" for c, v in sorted(cm.items())]
        body = line + "\n  " + " | ".join(parts) + "\n"
        with logp.open("a", encoding="utf-8") as f:
            f.write(body)
        pulse.write_text(body, encoding="utf-8")
        # stall alert if no progress 25 min and not finished
        if not report and age > 1500 and not st.get("running"):
            with alert.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] STALL age={age} n={n} running={st.get('running')}\n")
        if report:
            with logp.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] REPORT READY — monitor exit\n")
            break
        time.sleep(60)
    except Exception:
        with logp.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        time.sleep(30)
