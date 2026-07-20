import json, urllib.request
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_monitor_18r29.txt"

st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8).read())
rows = []
if (OUT / "summary.jsonl").exists():
    rows = [json.loads(x) for x in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
by = defaultdict(list)
for r in rows:
    by[r.get("cell")].append(r)
lines = [
    f"ts={datetime.now().isoformat(timespec='seconds')}",
    f"running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:180]}",
    f"rows={len(rows)} ok={sum(1 for r in rows if r.get('ok'))} classes={dict(Counter(r.get('class') for r in rows))}",
]
for c, items in by.items():
    rounds = {}
    for it in items:
        ri = it.get("round")
        prev = rounds.get(ri)
        if prev is None or (it.get("ok") and not prev.get("ok")):
            rounds[ri] = it
    lines.append(
        f"  {c}: rounds={len(rounds)} ok={sum(1 for v in rounds.values() if v.get('ok'))} cls={dict(Counter(v.get('class') for v in rounds.values()))}"
    )
clog = (ROOT / "matrix_runs" / "matrix_18r29_runner_console.log").read_text(encoding="utf-8", errors="replace").splitlines()[-18:]
lines.append("console:")
lines.extend(clog)
text = "\n".join(lines) + "\n"
SNAP.write_text(text, encoding="utf-8")
print(text)
