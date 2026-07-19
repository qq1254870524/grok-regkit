import time, json, urllib.request
from pathlib import Path
from datetime import datetime
m = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216")
out = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\long_mon.txt")
rst = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\restart8092.txt")
end = time.time() + 2400
last_runner = ""
while time.time() < end:
    lines = [f"=== {datetime.now().isoformat()} ==="]
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
        lines.append(
            "status run={running} phase={phase} s={success} f={fail} p={pending_sso} kind={job_kind}".format(
                running=st.get("running"), phase=st.get("phase"), success=st.get("success"),
                fail=st.get("fail"), pending_sso=st.get("pending_sso"), job_kind=st.get("job_kind"),
            )
        )
        lines.append("last=" + str(st.get("last_event") or "")[:220])
    except Exception as e:
        lines.append(f"status_err {e}")
    if (m / "runner.log").exists():
        rt = (m / "runner.log").read_text(encoding="utf-8", errors="replace")
        lines.append("--- runner tail ---")
        lines.extend(rt.splitlines()[-18:])
        if rt != last_runner:
            last_runner = rt
    if (m / "summary.jsonl").exists():
        rows = (m / "summary.jsonl").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        lines.append(f"summary_rows={len(rows)}")
        lines.extend(rows[-8:])
    if rst.exists():
        lines.append("restart:" + rst.read_text(encoding="utf-8", errors="replace")[:300])
    # server pid age via simple check of hybrid r22 loaded marker after restart
    out.write_text("\n".join(lines), encoding="utf-8")
    # done when runner contains FINAL or matrix process gone and not running
    if "MATRIX COMPLETE" in (last_runner or "") or "done cells" in (last_runner or "").lower():
        break
    if "pending_sso_recovery" in last_runner and last_runner.count("ok=") >= 12:
        # rough complete
        pass
    time.sleep(45)
out.write_text(out.read_text(encoding="utf-8") + "\nDONE_MONITOR\n", encoding="utf-8")
