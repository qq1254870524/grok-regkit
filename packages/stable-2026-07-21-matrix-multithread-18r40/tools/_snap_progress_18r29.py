import json, urllib.request, time, sys
from pathlib import Path
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = Path("matrix_runs/matrix_18r29_20260719_070041/summary.jsonl")
rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
by = defaultdict(dict)
for r in rows:
    c = r.get("cell"); ri = r.get("round"); prev = by[c].get(ri)
    if prev is None or (r.get("ok") and not prev.get("ok")):
        by[c][ri] = r
print("rows", len(rows), "mtime", time.ctime(p.stat().st_mtime))
for c in sorted(by):
    rounds = by[c]
    ok = sum(1 for v in rounds.values() if v.get("ok"))
    print(f" {c}: {ok}/{len(rounds)} {dict(Counter(v.get('class') for v in rounds.values()))}")
st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4).read())
ev = (st.get("last_event") or "").encode("utf-8", "replace").decode("utf-8", "replace")[:140]
print("api", st.get("running"), st.get("phase"), st.get("session_success"), f"{st.get('jobs_started')}/{st.get('jobs_finished')}", ev)
print("report", (p.parent / "REPORT.md").exists())
