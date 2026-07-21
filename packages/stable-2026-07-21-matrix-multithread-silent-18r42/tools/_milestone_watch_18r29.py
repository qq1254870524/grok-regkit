import json, time, urllib.request
from pathlib import Path
from collections import defaultdict, Counter
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
MS = ROOT / "matrix_runs" / "_milestones_18r29.txt"
SUM = OUT / "summary.jsonl"
last_n = -1
last_phase = ""
def api():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}
def summarize():
    if not SUM.exists():
        return 0, {}
    rows=[json.loads(x) for x in SUM.read_text(encoding="utf-8").splitlines() if x.strip()]
    by=defaultdict(dict)
    for r in rows:
        c=r.get("cell"); ri=r.get("round"); prev=by[c].get(ri)
        if prev is None or (r.get("ok") and not prev.get("ok")):
            by[c][ri]=r
    cells={}
    for c, rounds in by.items():
        ok=sum(1 for v in rounds.values() if v.get("ok"))
        cells[c]={"ok":ok,"n":len(rounds),"cls":dict(Counter(v.get("class") for v in rounds.values()))}
    return len(rows), cells
with MS.open("a", encoding="utf-8") as f:
    f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] milestone watcher start\n")
for i in range(400):
    n, cells = summarize()
    st = api()
    phase = f"{st.get('phase')}|{st.get('running')}|{st.get('session_success')}|{st.get('jobs_started')}/{st.get('jobs_finished')}"
    report = (OUT/"REPORT.md").exists()
    changed = (n != last_n) or (phase != last_phase and (st.get("phase") in ("finished","idle",None) or not st.get("running")))
    if n != last_n or report or (i % 5 == 0):
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] rows={n} report={report} {phase} ev={(st.get('last_event') or st.get('error') or '')[:100]}"
        # compact cells
        bits=[]
        for c in sorted(cells):
            bits.append(f"{c.split('__')[0][:1]}{c.split('__')[1][:1] if len(c.split('__'))>1 else ''}{c.split('__')[-1][:1]}={cells[c]['ok']}/{cells[c]['n']}")
        # better labels
        nice=[]
        for c,v in sorted(cells.items()):
            nice.append(f"{c}:{v['ok']}/{v['n']}{v['cls']}")
        with MS.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            if n != last_n:
                f.write("  " + " | ".join(nice) + "\n")
                if SUM.exists():
                    last = SUM.read_text(encoding="utf-8").strip().splitlines()[-1]
                    f.write("  last=" + last[:240] + "\n")
        last_n = n
    last_phase = phase
    if report:
        with MS.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] REPORT_READY\n")
        break
    time.sleep(30)
