import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"
out=root/"matrix_runs"/"_progress_live.txt"
def get_status():
    return json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
def get_logs(n=25):
    d=json.load(urllib.request.urlopen(f"http://127.0.0.1:8092/api/logs/snapshot?limit={n}", timeout=10))
    return d.get("lines") or []
lines=[]
prev_runner = weak.joinpath("runner.log").read_text(encoding="utf-8", errors="replace") if (weak/"runner.log").exists() else ""
for i in range(120):
    ts=datetime.now().strftime("%H:%M:%S")
    try:
        s=get_status()
        lg=get_logs(12)
        last_logs=" || ".join(str(x)[-120:] for x in lg[-4:])
        row=f"{ts} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={str(s.get('last_event'))[:100]}"
        lines.append(row)
        lines.append("  L:"+last_logs[:400])
    except Exception as e:
        lines.append(f"{ts} err={e}")
    rt=weak.joinpath("runner.log").read_text(encoding="utf-8", errors="replace") if (weak/"runner.log").exists() else ""
    if len(rt)>len(prev_runner):
        lines.append("  RUNNER:"+rt[len(prev_runner):].strip()[-500:])
        prev_runner=rt
    # done when weak gone
    import subprocess
    try:
        o=subprocess.check_output(["tasklist","/FI","PID eq 156952","/FO","CSV","/NH"], text=True, encoding="utf-8", errors="replace")
        alive = "156952" in o and not o.lower().startswith("info")
    except Exception:
        alive=False
    if not alive:
        lines.append(f"{ts} weak_pid_gone")
        # wait post a bit
        for j in range(40):
            time.sleep(15)
            plog=root/"matrix_runs"/"_post_matrix_r25_release.log"
            if plog.exists():
                lines.append(plog.read_text(encoding="utf-8", errors="replace")[-1500:])
            try:
                s=get_status(); lines.append(f"postwait run={s.get('running')} ok={s.get('ok')}")
            except Exception as e:
                lines.append(f"postwait status {e}")
            if (root/"packages"/"stable-2026-07-19-nsfw-direct-18r25.zip").exists():
                lines.append("PKG_18r25_READY")
                break
        break
    out.write_text("\n".join(lines[-200:])+"\n", encoding="utf-8")
    time.sleep(20)
out.write_text("\n".join(lines[-300:])+"\n", encoding="utf-8")
