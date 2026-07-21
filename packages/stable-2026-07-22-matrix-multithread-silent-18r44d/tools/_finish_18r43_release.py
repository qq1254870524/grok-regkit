# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path
import urllib.request
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
LOG = OUT / "_CODEX_18r43_FINISH.log"
PKG_NAME = "stable-2026-07-21-matrix-multithread-silent-18r43"
ZIP = ROOT / "packages" / (PKG_NAME + ".zip")
TAG = PKG_NAME

def log(msg: str) -> None:
    line = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + " " + msg
    print(line, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e), "running": True}

def find_summary():
    files = sorted(OUT.glob("matrix_18r43_*_summary.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    return files[0] if files else None

def run(cmd, timeout=600):
    log("run: " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    log("rc=%s" % r.returncode)
    if r.stdout:
        log("stdout: " + r.stdout[-800:])
    if r.stderr:
        log("stderr: " + r.stderr[-400:])
    return r.returncode

def main():
    log("finish watcher start pid=%s" % os.getpid())
    while True:
        summ = find_summary()
        st = status()
        running = bool(st.get("running"))
        log("summary=%s running=%s ok=%s fail=%s zip=%s" % (bool(summ), running, st.get("success"), st.get("fail"), ZIP.exists()))
        if summ and (not running):
            break
        time.sleep(60)
    log("matrix done summary=%s" % (summ.name if summ else "?"))
    if not ZIP.exists():
        rc = run([sys.executable, "-B", str(ROOT / "tools" / "package_18r43_silent.py")])
        if rc != 0:
            log("package failed rc=%s" % rc)
            return 1
    else:
        log("package already exists")
    files = [
        "hybrid_register.py", "browser/token_harvester.py", "grok_register_ttk.py",
        "web/server.py", "web/index.html", "pending_sso_recovery.py", "protocol/sso_util.py",
        "tools/matrix_18r43_silent_stable_mt.py", "tools/package_18r43_silent.py",
        "tools/start_matrix18r43_hidden.ps1", "tools/_supervisor_18r43_complete.py", "tools/_agent_keep_18r43.py",
        "tools/_silence_safe_drission.py", "CHANGELOG.md",
        "packages/" + PKG_NAME, "packages/" + PKG_NAME + ".zip",
    ]
    for rel in files:
        fp = ROOT / rel
        if fp.exists():
            run(["git", "add", "--", rel], timeout=60)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(ROOT))
    if r.returncode != 0:
        msg = "feat(matrix): 18r43 silent multi-thread matrix package + dual_send/awaiting_pool/SSO fixes"
        run(["git", "commit", "-m", msg], timeout=60)
    else:
        log("no staged changes to commit")
    existing = subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/" + TAG], cwd=str(ROOT), capture_output=True)
    if existing.returncode != 0:
        run(["git", "tag", "-a", TAG, "-m", PKG_NAME], timeout=30)
    else:
        log("tag already exists: " + TAG)
    run(["git", "push", "mygithub", "HEAD", TAG], timeout=180)
    notes = ROOT / "packages" / PKG_NAME / "PACKAGE_NOTES.md"
    body = notes.read_text(encoding="utf-8", errors="replace") if notes.exists() else PKG_NAME
    notes_tmp = OUT / "_18r43_release_notes.md"
    notes_tmp.write_text(body, encoding="utf-8")
    chk = subprocess.run(["gh", "release", "view", TAG, "--repo", "qq1254870524/grok-regkit"], cwd=str(ROOT), capture_output=True)
    if chk.returncode != 0:
        run(["gh", "release", "create", TAG, str(ZIP), "--title", PKG_NAME, "--notes-file", str(notes_tmp), "--repo", "qq1254870524/grok-regkit"], timeout=180)
    else:
        log("release already exists")
    log("FINISH COMPLETE")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        log("FATAL: %s" % e)
        raise
