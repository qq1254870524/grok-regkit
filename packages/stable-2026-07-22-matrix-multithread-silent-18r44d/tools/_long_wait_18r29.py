import time, json, urllib.request
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "matrix_18r29_20260719_070041"
sj = out / "summary.jsonl"
dst = root / "matrix_runs" / "_long_wait_18r29.log"
pulse = root / "_agent_pulse_18r29.txt"

def status():
    try:
        return json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
    except Exception as e:
        return {"error": str(e)}

def rows():
    if not sj.exists():
        return []
    return [json.loads(x) for x in sj.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]

def cell_line(rs):
    by = defaultdict(list)
    for r in rs:
        by[r.get("cell")].append(r)
    parts = []
    for c, items in sorted(by.items()):
        best = {}
        for it in items:
            ri = it.get("round")
            prev = best.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                best[ri] = it
        ok = sum(1 for v in best.values() if v.get("ok"))
        cls = dict(Counter(v.get("class") for v in best.values()))
        parts.append(f"{c}={ok}/{len(best)}{cls}")
    return " | ".join(parts)

# ~15 minutes, every 45s
for i in range(20):
    rs = rows()
    st = status()
    last = rs[-1] if rs else {}
    line = (
        f"[{datetime.now().strftime('%H:%M:%S')}] i={i} n={len(rs)} "
        f"last={last.get('cell')} r={last.get('round')} cls={last.get('class')} "
        f"sess={st.get('session_success')}/{st.get('session_fail')}/p{st.get('session_pending_sso')} "
        f"run={st.get('running')} phase={st.get('phase')} report={(out/'REPORT.md').exists()} "
        f"evt={(st.get('last_event') or '')[:120]}"
    )
    stats = cell_line(rs)
    body = line + "\n  " + stats + "\n"
    with dst.open("a", encoding="utf-8") as f:
        f.write(body)
    pulse.write_text(body, encoding="utf-8")
    print(body, flush=True)
    if (out / "REPORT.md").exists():
        print("REPORT READY", flush=True)
        break
    time.sleep(45)
