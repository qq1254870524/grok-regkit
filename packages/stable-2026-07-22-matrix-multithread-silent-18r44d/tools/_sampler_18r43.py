import json, time, urllib.request
from pathlib import Path
from datetime import datetime
runs = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
out = runs / "_CODEX_18r43_SAMPLER.jsonl"
url = "http://127.0.0.1:8092/api/status"
while True:
    row = {"ts": datetime.now().isoformat(timespec="seconds")}
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        row.update({
            "ok": d.get("success"), "fail": d.get("fail"),
            "pend": d.get("pending_sso"), "await": d.get("awaiting_pool"),
            "phase": d.get("phase"), "run": d.get("running"),
            "jobs_f": d.get("jobs_finished"), "jobs_s": d.get("jobs_started"),
            "target": d.get("target"), "event": (d.get("last_event") or "")[:180],
        })
    except Exception as e:
        row["err"] = str(e)[:200]
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    md = runs / "_CODEX_18r43_SAMPLER.md"
    md.write_text(
        f"# 18r43 sampler\nupdated={row['ts']}\n"
        f"ok={row.get('ok')} fail={row.get('fail')} pend={row.get('pend')} await={row.get('await')} "
        f"phase={row.get('phase')} run={row.get('run')} jobs={row.get('jobs_f')}/{row.get('jobs_s')}\n"
        f"event={row.get('event') or row.get('err')}\n",
        encoding="utf-8",
    )
    time.sleep(20)
