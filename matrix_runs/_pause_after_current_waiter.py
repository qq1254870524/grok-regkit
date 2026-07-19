import json, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
BASE = "http://127.0.0.1:8092"
logp = OUT / "_pause_after_current.log"

def get(path, timeout=15):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def w(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with logp.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

w("waiter start: allow current job to finish, then stay paused (no next start)")
last_running = None
while True:
    try:
        st = get("/api/status")
        running = bool(st.get("running"))
        msg = (
            f"running={running} ok={st.get('success')}/{st.get('target')} "
            f"fail={st.get('fail')} pend={st.get('pending_sso')} phase={st.get('phase')} "
            f"jobs={st.get('jobs_started')}/{st.get('jobs_finished')}"
        )
        if running != last_running:
            w(msg)
            last_running = running
        if not running:
            # double-check stable idle
            time.sleep(5)
            st2 = get("/api/status")
            if not st2.get("running"):
                # kill any stray matrix that reappeared
                import subprocess
                try:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command",
                         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_18r30_multithread|matrix_cross_run|unattended_guardian' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"],
                        text=True, timeout=30,
                    )
                    if out.strip():
                        w(f"killed stray matrix pids: {out.strip()}")
                except Exception as e:
                    w(f"stray check: {e}")
                summary = {
                    "paused_at": datetime.now().isoformat(timespec="seconds"),
                    "final_status": st2,
                    "note": "current job finished; all matrix paused; services left running",
                }
                (OUT / "_PAUSE_DONE.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                w(
                    f"PAUSE_DONE ok={st2.get('success')}/{st2.get('target')} "
                    f"fail={st2.get('fail')} pend={st2.get('pending_sso')} phase={st2.get('phase')}"
                )
                w("no further cells will be started")
                break
        time.sleep(15)
    except Exception as e:
        w(f"wait err: {e}")
        time.sleep(20)
