import json, time, urllib.request, subprocess, os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
SNAP = ROOT / "matrix_runs" / "_quick_status.txt"
ALERT = ROOT / "matrix_runs" / "_ALERT_REPORT_READY.txt"
DONE = ROOT / "matrix_runs" / "_agent_matrix_done.flag"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"]="1"

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4) as r:
            return json.loads(r.read().decode("utf-8","replace"))
    except Exception as e:
        return {"err": str(e)}

def board():
    rows=[]
    if (OUT/"summary.jsonl").exists():
        rows=[json.loads(x) for x in (OUT/"summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    by=defaultdict(list)
    for r in rows: by[r.get("cell")].append(r)
    lines=[]; ge=0
    for c,items in sorted(by.items()):
        rounds={}
        for it in items:
            ri=it.get("round"); prev=rounds.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")): rounds[ri]=it
        if len(rounds)>=10: ge+=1
        cls=dict(Counter(v.get("class") for v in rounds.values()))
        ok=sum(1 for v in rounds.values() if v.get("ok"))
        lines.append(f"{c}: {len(rounds)}/10 ok={ok} {cls}")
    return "\n".join(lines), len(rows), ge

def ensure_publish_alive():
    import ctypes
    # check process list via tasklist is heavy; use pgrep-like
    try:
        out=subprocess.check_output(["wmic","process","where","name='python.exe'","get","commandline"], text=True, encoding="utf-8", errors="replace")
    except Exception:
        out=subprocess.check_output(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select -Expand CommandLine"], text=True, encoding="utf-8", errors="replace")
    if "_auto_publish_18r29" not in out:
        subprocess.Popen(["C:\\Python312\\python.exe","-B","tools\\_auto_publish_18r29.py"], cwd=str(ROOT), creationflags=0x08000000)
        return "restarted_publish"
    return "publish_ok"

for i in range(400):
    st=status()
    b, rows, ge = board()
    console = (ROOT/"matrix_runs"/"matrix_18r29_runner_console.log")
    tail=""
    if console.exists():
        tail="\n".join(console.read_text(encoding="utf-8",errors="replace").splitlines()[-8:])
    body = (
        f"ts={datetime.now().strftime('%H:%M:%S')} tick={i}\n"
        f"phase={st.get('phase')} running={st.get('running')} s/f/p={st.get('session_success')}/{st.get('session_fail')}/{st.get('session_pending_sso')}\n"
        f"last={str(st.get('last_event',''))[:180]}\n"
        f"rows={rows} cells_ge10={ge} report={(OUT/'REPORT.md').exists()} done={DONE.exists()}\n"
        f"---BOARD---\n{b}\n---CONSOLE---\n{tail}\n"
    )
    SNAP.write_text(body, encoding="utf-8")
    if (OUT/"REPORT.md").exists():
        ALERT.write_text(f"REPORT ready at {datetime.now().isoformat()}\n{body}", encoding="utf-8")
        ensure_publish_alive()
        # wait for package zip
        tag="stable-2026-07-19-matrix-singlethread-18r29"
        zip_path=ROOT/"packages"/f"{tag}.zip"
        for j in range(120):
            st2=status()
            body2=body+f"\npublish_wait j={j} zip={zip_path.exists()} tag_check...\n"
            # check tag
            tp=subprocess.run(["git","tag","--list",tag], cwd=str(ROOT), capture_output=True, text=True)
            body2 += f"tag={tp.stdout.strip()}\n"
            SNAP.write_text(body2, encoding="utf-8")
            if zip_path.exists() and tp.stdout.strip():
                # companions
                subprocess.run(["C:\\Python312\\python.exe","-B","tools\\_publish_companions_18r29.py"], cwd=str(ROOT), capture_output=True, text=True)
                DONE.write_text(body2, encoding="utf-8")
                ALERT.write_text(f"PUBLISH DONE {datetime.now().isoformat()}\n{body2}", encoding="utf-8")
                break
            time.sleep(10)
        break
    time.sleep(45)
