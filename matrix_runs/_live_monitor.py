import time, json, urllib.request
from pathlib import Path
root = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411")
out = root / "_monitor_live.txt"
end = time.time() + 40*60
last = ""
while time.time() < end:
    lines = []
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            s = json.loads(r.read().decode())
        lines.append(f"status running={s.get('running')} phase={s.get('phase')} job={s.get('job_kind')} s={s.get('success')} f={s.get('fail')} p={s.get('pending_sso')} event={str(s.get('last_event') or '')[:160]}")
    except Exception as e:
        lines.append(f"status err={e}")
    try:
        rl = (root/"runner.log").read_text(encoding="utf-8", errors="ignore").splitlines()
        lines.append("runner_tail:")
        lines.extend("  "+x for x in rl[-8:])
    except Exception as e:
        lines.append(f"runner err={e}")
    done = (root/"DONE.txt").exists()
    lines.append(f"DONE={done}")
    txt = "\n".join(lines) + f"\n---- {time.strftime('%H:%M:%S')} ----\n"
    out.write_text(txt, encoding="utf-8")
    if done:
        break
    time.sleep(12)
out.write_text(out.read_text(encoding="utf-8") + "\nMONITOR_EXIT\n", encoding="utf-8")
