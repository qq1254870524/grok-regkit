import json, time, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
root = Path(r"C:\Users\zhang\grok-regkit")
weak = root / "matrix_runs" / "matrix_18r24_weak_20260719_033411"
out = root / "matrix_runs" / "_pulse_long.txt"
def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}
def pids():
    try:
        o=subprocess.check_output(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_rerun_weak_18r24|_post_matrix_r25' } | ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine.Substring(0,[Math]::Min(80,$_.CommandLine.Length)))\" }"], text=True, encoding="utf-8", errors="replace", timeout=20)
        return o.strip()
    except Exception as e:
        return str(e)
lines=[]
for i in range(90):  # ~45 min
    ts=datetime.now().strftime("%H:%M:%S")
    s=status()
    last=(s.get("last_event") or s.get("error") or "")[:140]
    rl=weak/"runner.log"
    rm=datetime.fromtimestamp(rl.stat().st_mtime).strftime("%H:%M:%S") if rl.exists() else "-"
    line=f"{ts} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={last} runner_m={rm}"
    lines.append(line)
    if i%3==0:
        # append runner last 3
        if rl.exists():
            t=rl.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
            lines.append("  RUN:"+(" | ".join(t)))
        lines.append("  PID:"+pids().replace("\n","; "))
    out.write_text("\n".join(lines[-200:])+"\n", encoding="utf-8")
    # exit early if weak dead and not running for a while
    if i>5 and "matrix_rerun_weak" not in pids() and not s.get("running"):
        lines.append(f"{ts} weak done idle")
        out.write_text("\n".join(lines[-200:])+"\n", encoding="utf-8")
        break
    time.sleep(30)
out.write_text("\n".join(lines[-300:])+"\n", encoding="utf-8")
