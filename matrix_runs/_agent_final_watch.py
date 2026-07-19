import json, time, urllib.request, collections, traceback
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
out = root/"matrix_runs"/"matrix_18r29_20260719_070041"
snap = root/"matrix_runs"/"_agent_final_snap.txt"
log = root/"matrix_runs"/"_agent_final_watch.log"
boardf = root/"matrix_runs"/"_progress_board_18r29.txt"
flag = root/"matrix_runs"/"_agent_matrix_done.flag"

def logw(m):
    line=f"[{datetime.now().isoformat(timespec='seconds')}] {m}"
    with log.open("a", encoding="utf-8") as f:
        f.write(line+"\n"); f.flush()

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4) as r:
            return r.read().decode("utf-8","replace")
    except Exception as e:
        return f"ERR {e}"

def board_text():
    p=out/"summary.jsonl"
    if not p.exists():
        return "no summary"
    rows=[json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    by=collections.defaultdict(list)
    for r in rows: by[r.get("cell")].append(r)
    lines=[]; done=0
    for c,items in by.items():
        rounds={}
        for it in items:
            ri=it.get("round"); prev=rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")): rounds[ri]=it
        if len(rounds)>=10: done+=1
        cls=dict(collections.Counter(v.get("class") for v in rounds.values()))
        ok=sum(1 for v in rounds.values() if v.get("ok"))
        lines.append(f"{c}: {len(rounds)}/10 ok={ok} {cls}")
    return "\n".join(lines)+f"\nrows={len(rows)} cells_ge10={done} report={(out/'REPORT.md').exists()}"

def write_snap(tag):
    cp=root/"matrix_runs"/"matrix_18r29_runner_console.log"
    console="\n".join(cp.read_text(encoding="utf-8",errors="replace").splitlines()[-12:]) if cp.exists() else ""
    b=board_text()
    body=f"tag={tag}\nts={datetime.now().isoformat(timespec='seconds')}\nSTATUS={status()}\nBOARD\n{b}\nCONSOLE\n{console}\n"
    snap.write_text(body, encoding="utf-8")
    boardf.write_text(b+"\n", encoding="utf-8")

logw("robust watcher start")
last_rows=0; stall=0
while True:
    try:
        write_snap("tick")
        rows=0
        sp=out/"summary.jsonl"
        if sp.exists():
            rows=sum(1 for line in sp.open(encoding="utf-8") if line.strip())
        if rows>last_rows:
            logw(f"progress rows={rows}"); last_rows=rows; stall=0
        else:
            stall+=1; logw(f"stall={stall} rows={rows}")
        if (out/"REPORT.md").exists():
            logw("REPORT found")
            write_snap("report")
            # wait up to 30min for publish tag
            for i in range(180):
                time.sleep(10)
                write_snap(f"pub{i}")
                import subprocess
                p=subprocess.run(["git","tag","--list","stable-2026-07-19-matrix-singlethread-18r29"], cwd=str(root), capture_output=True, text=True)
                if p.stdout.strip():
                    logw("tag ok "+p.stdout.strip()); break
            flag.write_text(board_text(), encoding="utf-8")
            logw("done flag"); write_snap("end"); break
    except Exception:
        logw("exc "+traceback.format_exc()[-500:])
    time.sleep(30)
