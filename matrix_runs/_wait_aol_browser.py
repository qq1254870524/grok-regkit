import json, time, urllib.request
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"
out=root/"matrix_runs"/"_wait_marker.txt"
def st():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error":str(e)}
prev=weak.joinpath("runner.log").read_text(encoding="utf-8",errors="replace") if weak.joinpath("runner.log").exists() else ""
start=time.time()
lines=[]
while time.time()-start < 900:
    s=st()
    ts=datetime.now().strftime("%H:%M:%S")
    txt=weak.joinpath("runner.log").read_text(encoding="utf-8",errors="replace") if weak.joinpath("runner.log").exists() else ""
    if len(txt)>len(prev):
        new="\n".join(txt[len(prev):].splitlines())
        lines.append(f"{ts} RUNNER_NEW: {new[-500:]}")
        prev=txt
    lines.append(f"{ts} run={s.get('running')} phase={s.get('phase')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} last={(s.get('last_event') or '')[:100]}")
    out.write_text("\n".join(lines[-80:])+"\n", encoding="utf-8")
    # if runner advanced past browser direct aol r1 and idle momentarily
    if "browser__direct__aol] r1/" in txt and not s.get("running"):
        # give 5s for next start
        time.sleep(5)
        s2=st(); txt2=weak.joinpath("runner.log").read_text(encoding="utf-8",errors="replace")
        lines.append(f"after r1: run={s2.get('running')} runner_tail={txt2.splitlines()[-3:]}")
        out.write_text("\n".join(lines[-80:])+"\n", encoding="utf-8")
        if "browser__direct__aol] r2/" in txt2 or s2.get("running"):
            # continue until r2 done and next cell or complete
            pass
    if all(k in txt for k in [
        "browser__direct__aol] r1/","browser__direct__aol] r2/",
        "browser__socks5_list__outlook] r1/","browser__socks5_list__outlook] r2/",
        "browser__socks5_list__aol] r1/","browser__socks5_list__aol] r2/",
        "pending_sso_recovery__socks5_list] r1/","pending_sso_recovery__direct] r2/",
    ]) and not s.get("running"):
        lines.append("ALL_REMAINING_MARKERS_SEEN")
        out.write_text("\n".join(lines[-100:])+"\n", encoding="utf-8")
        break
    time.sleep(25)
lines.append("WAIT_END")
out.write_text("\n".join(lines[-120:])+"\n", encoding="utf-8")
