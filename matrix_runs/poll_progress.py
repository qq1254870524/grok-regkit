import urllib.request, json, time, pathlib
from datetime import datetime
m = pathlib.Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216")
out = pathlib.Path(r"C:\Users\zhang\grok-regkit\matrix_runs\poll_progress.txt")
end = time.time() + 600
while time.time() < end:
    lines = [f"=== {datetime.now().isoformat()} ==="]
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
        snap = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot", timeout=5).read().decode())
        last = (snap.get("lines") or [])[-8:]
        lines.append(
            "status running={running} phase={phase} s={success} f={fail} p={pending_sso} js={jobs_started} jf={jobs_finished}".format(
                **{k: st.get(k) for k in ["running", "phase", "success", "fail", "pending_sso", "jobs_started", "jobs_finished"]}
            )
        )
        lines.extend(["LOG " + x for x in last])
    except Exception as e:
        lines.append(f"status err {e}")
    if (m / "runner.log").exists():
        lines.append("--- runner ---")
        lines.extend((m / "runner.log").read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    if (m / "summary.jsonl").exists():
        rows = (m / "summary.jsonl").read_text(encoding="utf-8", errors="replace").strip().splitlines()
        lines.append(f"summary_rows={len(rows)}")
        lines.extend(rows[-6:])
    files = sorted(m.glob("*"), key=lambda p: p.stat().st_mtime)
    lines.append("files:")
    for p in files:
        lines.append(f"  {datetime.fromtimestamp(p.stat().st_mtime).strftime('%H:%M:%S')} {p.stat().st_size} {p.name}")
    out.write_text("\n".join(lines), encoding="utf-8")
    # stop if matrix dead and not running for a bit
    alive = False
    try:
        import os, signal
        os.kill(154288, 0)
        alive = True
    except Exception:
        alive = False
    lines.append(f"matrix_alive={alive}")
    out.write_text("\n".join(lines), encoding="utf-8")
    if not alive and not st.get("running"):
        # give one more cycle
        time.sleep(20)
        try:
            st2 = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
        except Exception:
            st2 = {}
        if not st2.get("running"):
            out.write_text(out.read_text(encoding="utf-8") + "\nMATRIX_IDLE_DONE\n", encoding="utf-8")
            break
    time.sleep(30)
