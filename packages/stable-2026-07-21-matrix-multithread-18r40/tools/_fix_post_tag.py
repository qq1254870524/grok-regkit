from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_post_matrix_r24b_release.py")
t = p.read_text(encoding="utf-8")
# force constants
import re
t = re.sub(r'WEAK_PID\s*=\s*\d+', 'WEAK_PID = 156952', t)
t = re.sub(r'TAG\s*=\s*"[^"]+"', 'TAG = "stable-2026-07-19-pending-rotate-18r24c"', t, count=1)
if 'pending_sso_recovery.py' not in t:
    t = t.replace('"hybrid_register.py",', '"hybrid_register.py",\n        "pending_sso_recovery.py",')
p.write_text(t, encoding="utf-8")
print('TAG line:', [l for l in t.splitlines() if l.startswith('TAG')][:2])
print('WEAK', [l for l in t.splitlines() if 'WEAK_PID' in l][:1])
