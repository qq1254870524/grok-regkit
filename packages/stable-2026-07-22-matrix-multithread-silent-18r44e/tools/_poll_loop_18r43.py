import sys, time, json, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode = True
ROOT = Path(r"C:/Users/zhang/grok-regkit")
OUT = ROOT / "matrix_runs" / "_CODEX_18r43_POLL_LOOP.md"
STATUS = "http://127.0.0.1:8092/api/status"
MATRIX, WEB, LONGMON = 85044, 23304, 135408
lines = []
start = time.time()

def count_name(name):
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command", f("(GetProcess {name} -EA SilentlyContinue | Measure-Object).Count")], capture_output=True, text=True, timeout=15)
        return (r.stdout or "0").strip() or "0"
    except Exception:
        return "?"

def unique_profiles():
    try:
        cmd = r"(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match 'userData\\(\d+)' } | ForEach-Object { if ($_.CommandLine -match 'userData\\(\d+)'" { $matches[1] } } | Sort-Object -Unique | Measure-Object).Count"
        r = subprocess.run(["powershell","-NoProfile","-Command", cmd], capture_output=True, text=True, timeout=30)
        return (r.stdout or "?").strip() or "?"
    except Exception:
        return "?"

def alive(pid):
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command", f"if(Get-Process -Id {pid} -EA SilentlyContinue){'1'}else{'0'}"], capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() == "1"
    except Exception:
        return False

while time.time() - start < 12*3600:
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        with urllib.request.urlopen(STATUS, timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8", "replace"))
        ok, fail, pend = d.get("success"), d.get("fail"), d.get("pending")
        awaitp, phase, run = d.get("awaiting_pool"), d.get("phase"), d.get("running")
        jobs = f"{d.get('jobs_started')}/{d.get('jobs_finished')}"
    except Exception as e:
        ok = fail = pend = awaitp = phase = run = jobs = "ERR:" + str(e)[:80]
    ch, ed, up = count_name("chrome"), count_name("msedge"), unique_profiles()
    line = f"2{ts} run={run} ok={ok} fail={fail} pend={pend} await={awaitp} phase={phase} jobs={jobs} chrome={ch} profiles={up} edge={ed} mx={alive(MATRIX)} web={alive(WEB)} lm={alive(LONGMON)}"
    lines.append(line); lines = lines[-80:]
    OUT.write_text("# 18r43 poll loop\n" + "\n".join(lines) + "\n", encoding="utf-8")
    if (ROOT / "packages" / "stable-2026-07-21-matrix-multithread-silent-18r43.zip").exists():
        OUT write_text(OUT.read_text(encoding="utf-8") + f"\nDONE package at {ts}\n", encoding="utf-8")
        break
    time.sleep(45)
