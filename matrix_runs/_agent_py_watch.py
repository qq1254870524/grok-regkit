import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
out=root/"matrix_runs"/"matrix_18r29_20260719_070041"
snap=root/"matrix_runs"/"_agent_py_snap.txt"
log=root/"matrix_runs"/"_agent_py_watch.log"
end=time.time()+20*60
def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=3) as r:
            return r.read().decode("utf-8","replace")
    except Exception as e:
        return str(e)
def board():
    p=out/"summary.jsonl"
    if not p.exists():
        return "no summary"
    import collections
    rows=[json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    by=collections.defaultdict(list)
    for r in rows: by[r.get("cell")].append(r)
    lines=[]
    for c,items in by.items():
        rounds={}
        for it in items:
            ri=it.get("round"); prev=rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")): rounds[ri]=it
        cls=dict(collections.Counter(v.get("class") for v in rounds.values()))
        ok=sum(1 for v in rounds.values() if v.get("ok"))
        lines.append(f"{c}: {len(rounds)}/10 ok={ok} {cls}")
    return "\n".join(lines)+f"\nrows={len(rows)} report={(out/'REPORT.md').exists()}"
while time.time()<end:
    ts=datetime.now().isoformat(timespec="seconds")
    st=status(); b=board()
    console=""
    cp=root/"matrix_runs"/"matrix_18r29_runner_console.log"
    if cp.exists():
        console="\n".join(cp.read_text(encoding="utf-8",errors="replace").splitlines()[-12:])
    newest=" | ".join(f"{p.stat().st_mtime_ns} {p.name}" for p in sorted(out.glob('*'), key=lambda x:x.stat().st_mtime, reverse=True)[:6])
    body=f"ts={ts}\nSTATUS={st}\nBOARD\n{b}\nCONSOLE\n{console}\n"
    snap.write_text(body, encoding="utf-8")
    log.open("a",encoding="utf-8").write(f"{ts} report={(out/'REPORT.md').exists()}\n")
    if (out/"REPORT.md").exists():
        break
    time.sleep(40)
