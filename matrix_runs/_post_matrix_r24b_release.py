# -*- coding: utf-8 -*-
"""Wait for weak matrix PID, restart 8092 only, build 18r24c package, commit+push+release."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
LOG = ROOT / "matrix_runs" / "_post_matrix_r24b_release.log"
WEAK_PID = 156952
TAG = "stable-2026-07-19-pending-rotate-18r24c"
TAG23 = "stable-2026-07-19-outlook-sso-nudge-18r23"

def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, cwd=None, check=False, timeout=600):
    log(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    p = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=isinstance(cmd, str),
    )
    if p.stdout:
        log(p.stdout.strip()[-2000:])
    if p.stderr:
        log(("STDERR: " + p.stderr.strip())[-1500:])
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed rc={p.returncode}")
    return p

def pid_alive(pid: int) -> bool:
    try:
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, errors="replace")
        return str(pid) in out and "python" in out.lower()
    except Exception:
        return False

def wait_pid(pid: int, max_h: float = 6.0) -> None:
    log(f"waiting weak pid={pid}")
    deadline = time.time() + max_h * 3600
    while time.time() < deadline:
        if not pid_alive(pid):
            log("weak pid ended")
            return
        time.sleep(15)
    raise TimeoutError("weak wait timeout")

def api_status():
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def stop_job():
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:8092/api/stop", data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log(f"stop_job: {e}")

def kill_8092_only():
    # find listener on 8092
    out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
    pids = set()
    for line in out.splitlines():
        if "LISTENING" in line and ":8092" in line:
            parts = line.split()
            try:
                pids.add(int(parts[-1]))
            except Exception:
                pass
    for pid in pids:
        log(f"kill 8092 pid={pid}")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)

def start_8092():
    ps1 = ROOT / "tools" / "start_web8092_hidden.ps1"
    if ps1.is_file():
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            [sys.executable, "-B", "web/server.py"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for i in range(40):
        time.sleep(1)
        st = api_status()
        if st.get("ok"):
            log(f"8092 up i={i} running={st.get('running')}")
            return
    raise RuntimeError("8092 failed to start")

def build_pkg():
    pkg = ROOT / "packages" / TAG
    if pkg.exists():
        import shutil
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    files = [
        "hybrid_register.py",
        "grok_register_ttk.py",
        "pending_sso_recovery.py",
        "web/server.py",
        "web/index.html",
        "tools/matrix_cross_run.py",
        "tools/matrix_rerun_weak_18r24.py",
        "tools/_build_pkg_18r24.py",
        "outlook_mail.py",
        "aol_mail.py",
        "browser/token_harvester.py",
        "protocol/sso_util.py",
    ]
    import shutil
    copied = []
    for rel in files:
        src = ROOT / rel
        if not src.is_file():
            log(f"skip missing {rel}")
            continue
        dst = pkg / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    changelog = f"""# {TAG}

## 2026-07-19 18r24 / 18r24c

### Fixes
- browser `fill_profile_and_submit` timeout 120→210s; late Turnstile extends deadline +75s
- matrix `classify` no longer maps healthy `IMAP login OK` to `email_login_fail`
- new classes: `profile_fill_fail`, `sso_timeout`, clearer pending signals
- pending sign-in prefers `?email=true` deep-link; force email form after empty social clicks
- **18r24c**: failed pending account rotates to end of `accounts_registered_pending_sso.txt`
- **18r24c**: pending job `importlib.reload` so mid-process patches apply without full stack restart
- browser success burns mailbox; signing-in SSO nudge (18r23 lineage)

### Main path
register → immediate SSO → pool materialize (g2a/Sub2API/CPA). pending is fallback only.

### Matrix evidence
- baseline: `matrix_runs/matrix_18r21_20260719_023216` (7 success / 13 fail, old classify noise)
- weak rerun: `matrix_runs/matrix_18r24_weak_*`

### Do not overwrite
Previous packages/releases (18r9–18r23) remain intact.
"""
    (pkg / "CHANGELOG_18r24c.md").write_text(changelog, encoding="utf-8")
    (pkg / "RESTORE.md").write_text(
        f"# Restore {TAG}\n\n1. Stop only 8092.\n2. Copy package files or `git checkout {TAG}`.\n3. `python -B web/server.py`\n4. Keep 8010/8080/8317/8318 running.\n",
        encoding="utf-8",
    )
    import zipfile
    zpath = ROOT / "packages" / f"{TAG}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pkg.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(pkg.parent))
    log(f"PKG {pkg} files={len(copied)} zip={zpath} size={zpath.stat().st_size}")
    return zpath, changelog

def git_release(zpath: Path, changelog: str):
    # stage source only
    add = [
        "hybrid_register.py",
        "grok_register_ttk.py",
        "pending_sso_recovery.py",
        "web/server.py",
        "web/index.html",
        "tools/matrix_cross_run.py",
        "tools/matrix_rerun_weak_18r24.py",
        "tools/_build_pkg_18r24.py",
        "tools/start_web8092_hidden.ps1",
        f"packages/{TAG}/",
        f"packages/{TAG}.zip",
    ]
    # also ensure 18r23 package tracked if present
    p23 = ROOT / "packages" / "stable-2026-07-19-outlook-sso-nudge-18r23"
    if p23.is_dir():
        add.append("packages/stable-2026-07-19-outlook-sso-nudge-18r23/")
        z23 = ROOT / "packages" / "stable-2026-07-19-outlook-sso-nudge-18r23.zip"
        if z23.is_file():
            add.append("packages/stable-2026-07-19-outlook-sso-nudge-18r23.zip")
    run(["git", "add", "-A", "--"] + add)
    # commit if dirty
    st = run(["git", "status", "--porcelain"])
    if st.stdout.strip():
        msg = "18r24c: profile timeout+classify+pending rotate; package+matrix weak evidence"
        run(["git", "commit", "-m", msg], check=False)
    else:
        log("nothing to commit")
    run(["git", "push", "mygithub", "main"], check=False, timeout=180)
    # tags
    for tag, note in (
        (TAG23, "18r23 Outlook strict post-send + browser SSO nudge"),
        (TAG, "18r24c profile timeout/classify/pending rotate"),
    ):
        # skip if remote tag exists
        ex = run(["git", "tag", "-l", tag])
        if tag not in (ex.stdout or ""):
            run(["git", "tag", "-a", tag, "-m", note], check=False)
        run(["git", "push", "mygithub", tag], check=False, timeout=120)
    # gh releases - create only if missing
    for tag, title, zname in (
        (TAG23, "18r23 Outlook SSO nudge", "stable-2026-07-19-outlook-sso-nudge-18r23.zip"),
        (TAG, "18r24c pending rotate + profile/classify", f"{TAG}.zip"),
    ):
        chk = run(["gh", "release", "view", tag, "-R", "qq1254870524/grok-regkit"])
        if chk.returncode == 0:
            log(f"release exists skip {tag}")
            continue
        zf = ROOT / "packages" / zname
        notes = ROOT / "packages" / tag / ("CHANGELOG_18r24c.md" if "18r24" in tag else "CHANGELOG.md")
        if not notes.is_file():
            # try common names
            cands = list((ROOT / "packages" / tag).glob("CHANGELOG*")) if (ROOT / "packages" / tag).is_dir() else []
            notes_path = str(cands[0]) if cands else None
        else:
            notes_path = str(notes)
        cmd = ["gh", "release", "create", tag, "-R", "qq1254870524/grok-regkit", "--title", title, "--latest=false"]
        if notes_path and Path(notes_path).is_file():
            cmd += ["--notes-file", notes_path]
        else:
            cmd += ["--notes", title]
        if zf.is_file():
            cmd.append(str(zf))
        run(cmd, check=False, timeout=180)

def main():
    log("post_matrix_r24b_release start")
    if pid_alive(WEAK_PID):
        wait_pid(WEAK_PID)
    else:
        log("weak pid already dead")
    # ensure idle
    for _ in range(60):
        st = api_status()
        if not st.get("running"):
            break
        stop_job()
        time.sleep(2)
    kill_8092_only()
    time.sleep(2)
    start_8092()
    zpath, changelog = build_pkg()
    git_release(zpath, changelog)
    # write weak report pointer
    weak_dirs = sorted((ROOT / "matrix_runs").glob("matrix_18r24_weak_*"), key=lambda p: p.stat().st_mtime)
    if weak_dirs:
        latest = weak_dirs[-1]
        log(f"latest weak={latest}")
        if (latest / "REPORT.md").is_file():
            log((latest / "REPORT.md").read_text(encoding="utf-8", errors="replace")[:1500])
        if (latest / "summary.jsonl").is_file():
            lines = (latest / "summary.jsonl").read_text(encoding="utf-8", errors="replace").strip().splitlines()
            log(f"summary lines={len(lines)}")
    log("DONE post_matrix_r24b_release")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL {e}")
        raise

