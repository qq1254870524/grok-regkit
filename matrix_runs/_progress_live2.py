import json, time, urllib.request, subprocess
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"
out=root/"matrix_runs"/"_progress_live2.txt"
def alive(pid):
    try:
        o=subprocess.check_output(["tasklist","/FI",f"PID eq {pid}","/NH"], text=True, encoding="utf-8", errors="replace")
        return str(pid) in o and not o.lower().startswith("info")
    except Exception:
        return False
def st():
    try:
        return json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
    except Exception as e:
        return {"error":str(e)}
lines=[]
while True:
    ts=datetime.now().strftime("%H:%M:%S")
    s=st()
    rl=(weak/"runner.log").read_text(encoding="utf-8", errors="replace") if (weak/"runner.log").exists() else ""
    tail=" | ".join(rl.splitlines()[-3:])
    lines.append(f"{ts} weak={alive(156952)} post={alive(164224)} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={str(s.get('last_event'))[:90]}")
    lines.append("  RUN:"+tail)
    out.write_text("\n".join(lines[-120:])+"\n", encoding="utf-8")
    if not alive(156952) and not s.get("running"):
        # wait for post packages
        for i in range(80):
            time.sleep(10)
            pl=root/"matrix_runs"/"_post_matrix_r25_release.log"
            pt=pl.read_text(encoding="utf-8", errors="replace") if pl.exists() else ""
            lines.append(f"POST_TAIL: {pt[-800:]}")
            pkgs=list((root/"packages").glob("*18r2*"))
            lines.append("PKGS:"+ ", ".join(sorted(x.name for x in pkgs)[-12:]))
            out.write_text("\n".join(lines[-160:])+"\n", encoding="utf-8")
            if "DONE post_matrix" in pt or (root/"packages"/"stable-2026-07-19-sso-hold-signup-18r26.zip").exists():
                lines.append("RELEASE_DONE_SIGNAL")
                out.write_text("\n".join(lines[-180:])+"\n", encoding="utf-8")
                break
            if not alive(164224) and i>3:
                lines.append("post dead early")
                break
        break
    time.sleep(30)
