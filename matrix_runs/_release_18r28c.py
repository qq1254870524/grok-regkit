# -*- coding: utf-8 -*-
"""18r28c package+release: non-blocking, never overwrite old tags/packages."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time, zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
os.chdir(ROOT)
LOG = ROOT / "matrix_runs" / "_release_18r28c.log"

def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, timeout=180, check=False):
    log("$ " + " ".join(map(str, cmd)))
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if p.stdout:
        log(p.stdout[-2500:])
    if p.stderr:
        log(p.stderr[-1500:])
    if check and p.returncode != 0:
        raise RuntimeError(f"fail {cmd} rc={p.returncode}")
    return p

FILES = [
    "hybrid_register.py",
    "grok_register_ttk.py",
    "pending_sso_recovery.py",
    "web/server.py",
    "web/index.html",
    "outlook_mail.py",
    "aol_mail.py",
    "browser/token_harvester.py",
    "sub2api_client.py",
    "tools/start_web8092_hidden.ps1",
    "tools/matrix_rerun_weak_18r24.py",
]

PACKAGES = [
    (
        "stable-2026-07-19-nsfw-direct-18r25",
        "18r25 NSFW proxy fail -> direct fallback; Outlook early_no_new 110s; 8092 hot-reload mail modules",
    ),
    (
        "stable-2026-07-19-sso-hold-signup-18r26",
        "18r26 browser SSO hold: never leave signup form while profile fields present; pure signing-in dwell before grok nudge",
    ),
    (
        "stable-2026-07-19-forced-rereg-18r27",
        "18r27 pending auth_error/bad_password re-register SAME email with optional b64 mail_token field; burn writes mail_token",
    ),
    (
        "stable-2026-07-19-pending-turnstile-18r28c",
        "18r28/18r28c pending SSO MUST solve+inject Cloudflare Turnstile before login submit; "
        "fill credentials without auto-click; CF-stuck/re-fill solve Turnstile; "
        "generic An error occurred one fresh Turnstile retry; "
        "hybrid _lookup_mail_token_from_pool; server/pending reload hybrid on pending job; "
        "main path unchanged: register -> immediate SSO -> pool; pending is fallback only",
    ),
]

def build_pkg(tag: str, notes: str) -> Path:
    pkg = ROOT / "packages" / tag
    zpath = ROOT / "packages" / f"{tag}.zip"
    if pkg.exists():
        # do not overwrite existing package content if zip already released size>0 and tag exists on remote? 
        # User said do not overwrite old packages. If local dir exists from failed build, rebuild only if no zip or empty.
        if zpath.exists() and zpath.stat().st_size > 1000:
            log(f"skip existing package {tag}")
            return zpath
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    for rel in FILES:
        src = ROOT / rel
        if src.is_file():
            dst = pkg / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (pkg / "CHANGELOG.md").write_text(
        f"# {tag}\n\n{notes}\n\n"
        f"Built: {datetime.now().isoformat(timespec='seconds')}\n\n"
        "Path: register -> immediate SSO -> pool; pending SSO recovery is fallback only.\n"
        "Do not overwrite older packages/releases.\n",
        encoding="utf-8",
    )
    (pkg / "RESTORE.md").write_text(
        f"# Restore {tag}\n\n"
        "1. Stop only 8092 (keep 8010/8080/8317/8318)\n"
        f"2. Copy package files over grok-regkit or `git checkout {tag}`\n"
        "3. `python -B web/server.py` or tools/start_web8092_hidden.ps1\n"
        "4. Pending SSO now requires Turnstile solve before login submit\n",
        encoding="utf-8",
    )
    # weak matrix report snippet if any
    weak = sorted((ROOT / "matrix_runs").glob("matrix_18r24_weak_*"), key=lambda p: p.stat().st_mtime)
    if weak:
        latest = weak[-1]
        rep = latest / "REPORT.md"
        if not rep.exists():
            rows = []
            sf = latest / "summary.jsonl"
            if sf.is_file():
                uniq = {}
                for line in sf.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    uniq[(r.get("cell"), r.get("round"))] = r
                body = [
                    f"# Weak matrix report",
                    f"dir: `{latest.name}`",
                    "",
                    "| cell | round | class | ok | elapsed |",
                    "|---|---:|---|:---:|---:|",
                ]
                for (c, r), v in sorted(uniq.items(), key=lambda x: (str(x[0][0]), x[0][1] or 0)):
                    body.append(f"| {c} | {r} | {v.get('class')} | {v.get('ok')} | {v.get('elapsed_s')} |")
                rep.write_text("\n".join(body) + "\n", encoding="utf-8")
        if rep.exists():
            shutil.copy2(rep, pkg / "MATRIX_REPORT.md")
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in pkg.rglob("*"):
            if fp.is_file():
                z.write(fp, fp.relative_to(pkg.parent))
    log(f"built {zpath} size={zpath.stat().st_size}")
    return zpath

def main():
    log("=== release 18r28c start ===")
    # compile sanity
    run([sys.executable, "-B", "-m", "py_compile", "pending_sso_recovery.py", "hybrid_register.py", "web/server.py"], check=True)
    zips = []
    for tag, notes in PACKAGES:
        zips.append((tag, notes, build_pkg(tag, notes)))

    # git add/commit/push mygithub only
    add = FILES + ["packages/"]
    run(["git", "add", "-A", "--"] + add)
    st = run(["git", "status", "--porcelain"])
    if st.stdout.strip():
        msg = (
            "18r28c: pending SSO Turnstile before login + fill_only + auth_error retry; "
            "hybrid mail_token pool lookup; hot-reload hybrid on pending job"
        )
        run(["git", "commit", "-m", msg])
    else:
        log("nothing to commit")

    # push commits
    run(["git", "push", "mygithub", "main"], timeout=180)

    # tags + releases (skip if tag exists)
    for tag, notes, zpath in zips:
        # local tag
        ex = run(["git", "tag", "-l", tag])
        if tag not in (ex.stdout or ""):
            run(["git", "tag", "-a", tag, "-m", notes[:200]])
        else:
            log(f"tag exists local {tag}")
        # push tag
        run(["git", "push", "mygithub", tag], timeout=120)
        # gh release
        chk = run(["gh", "release", "view", tag, "-R", "qq1254870524/grok-regkit"])
        if chk.returncode == 0:
            log(f"release exists skip {tag}")
            continue
        title = tag
        notes_file = ROOT / "matrix_runs" / f"_notes_{tag}.md"
        notes_file.write_text(f"## {tag}\n\n{notes}\n\nDo not overwrite older releases.\n", encoding="utf-8")
        cmd = [
            "gh", "release", "create", tag,
            str(zpath),
            "-R", "qq1254870524/grok-regkit",
            "--title", title,
            "--notes-file", str(notes_file),
            "--latest=false",
        ]
        run(cmd, timeout=180)
        log(f"release created {tag}")
    log("=== release 18r28c done ===")
    run(["gh", "release", "list", "-R", "qq1254870524/grok-regkit", "-L", "12"])

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL {e}")
        raise
