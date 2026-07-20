# -*- coding: utf-8 -*-
"""Build non-overwriting package stable-2026-07-19-pending-rotate-18r24b."""
from __future__ import annotations
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "stable-2026-07-19-pending-rotate-18r24b"
PKG = ROOT / "packages" / TAG
FILES = [
    "hybrid_register.py",
    "grok_register_ttk.py",
    "pending_sso_recovery.py",
    "web/server.py",
    "web/index.html",
    "tools/matrix_cross_run.py",
    "tools/matrix_rerun_weak_18r24.py",
    "tools/_build_pkg_18r24.py",
    "tools/start_web8092_hidden.ps1",
    "outlook_mail.py",
    "aol_mail.py",
    "browser/token_harvester.py",
]
if PKG.exists():
    shutil.rmtree(PKG)
PKG.mkdir(parents=True)
copied = []
for rel in FILES:
    src = ROOT / rel
    if not src.is_file():
        print("skip", rel)
        continue
    dst = PKG / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(rel)
(PKG / "CHANGELOG_18r24b.md").write_text(
    f"""# {TAG}

## Fixes 18r24 / 18r24b
- profile fill timeout 210s + late Turnstile +75s
- classify: no false email_login_fail on IMAP login OK
- pending sign-in email=true deep-link
- pending fail rotates head to end of pending file
- 8092 pending job importlib.reload

## Path
register -> immediate SSO -> pool; pending fallback only.

## Do not overwrite older packages/releases.
""",
    encoding="utf-8",
)
zpath = ROOT / "packages" / f"{TAG}.zip"
if zpath.exists():
    zpath.unlink()
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for p in PKG.rglob("*"):
        if p.is_file():
            z.write(p, p.relative_to(PKG.parent))
print("PKG", PKG)
print("ZIP", zpath, zpath.stat().st_size)
print("files", len(copied))
