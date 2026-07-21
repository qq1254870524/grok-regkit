"""Companion publish after 18r29 main package. Does not overwrite existing tags."""
from __future__ import annotations
import subprocess, time
from pathlib import Path
from datetime import datetime

TAG = "stable-2026-07-19-matrix-singlethread-18r29"
NOTE = f"""# Compat {TAG}

Paired with grok-regkit `{TAG}` single-thread matrix restore point.
- date: {datetime.now().isoformat(timespec='seconds')}
- matrix: hybrid/browser x direct/socks5_list x outlook/aol + pending_sso x2, 10 rounds each, count=1
- services keep running independent of registration stop
"""

def run(cmd, cwd):
    print("RUN", cmd, "cwd", cwd, flush=True)
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, encoding="utf-8", errors="replace")
    print(p.stdout[-1500:] if p.stdout else "")
    print(p.stderr[-800:] if p.stderr else "")
    return p.returncode

repos = [
    Path(r"C:\Users\zhang\grok-regkit-services"),
    Path(r"C:\Users\zhang\sub2api-src"),
    Path(r"C:\Users\zhang\grok-regkit-services1\grok2api1"),
]
for repo in repos:
    if not repo.exists():
        print("skip missing", repo)
        continue
    note = repo / f"COMPAT_{TAG}.md"
    note.write_text(NOTE, encoding="utf-8")
    run(["git", "add", note.name], repo)
    run(["git", "commit", "-m", f"docs: companion restore {TAG}"], repo)
    # tag if missing
    tp = subprocess.run(["git", "rev-parse", TAG], cwd=repo, capture_output=True, text=True)
    if tp.returncode != 0:
        run(["git", "tag", TAG], repo)
    else:
        print("tag exists", repo, TAG)
    # push
    remotes = subprocess.check_output(["git", "remote"], cwd=repo, text=True).split()
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else None)
    if remote:
        run(["git", "push", remote, "HEAD"], repo)
        run(["git", "push", remote, TAG], repo)
print("companion publish done")
