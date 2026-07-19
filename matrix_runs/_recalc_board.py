import json, collections
from pathlib import Path
out=Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041")
rows=[json.loads(x) for x in (out/"summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
by=collections.defaultdict(list)
for r in rows:
    by[r.get("cell")].append(r)
lines=[]
for c, items in by.items():
    rounds={}
    for it in items:
        ri=it.get("round")
        prev=rounds.get(ri)
        if prev is None or (it.get("ok") and not prev.get("ok")):
            rounds[ri]=it
    cls=dict(collections.Counter(v.get("class") for v in rounds.values()))
    ok=sum(1 for v in rounds.values() if v.get("ok"))
    lines.append(f"{c}: {len(rounds)} rounds ok={ok} classes={cls}")
text="\n".join(lines)+f"\ntotal_rows={len(rows)}\nreport={(out/'REPORT.md').exists()}\n"
Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_agent_board_recalc.txt").write_text(text, encoding="utf-8")
print(text)
