# -*- coding: utf-8 -*-

"""Package stable-2026-07-21-matrix-multithread-silent-18r43 (source-only, no overwrite)."""

from __future__ import annotations

import hashlib

import shutil

import zipfile

from datetime import datetime

from pathlib import Path



ROOT = Path(r"C:\Users\zhang\grok-regkit")

PKG_NAME = "stable-2026-07-21-matrix-multithread-silent-18r43"

PKG = ROOT / "packages" / PKG_NAME

ZIP = ROOT / "packages" / f"{PKG_NAME}.zip"



SKIP_DIR_NAMES = {

    "__pycache__", ".git", "node_modules", "packages",

    ".venv", "venv", "chrome_profiles", "profiles", "data", "logs",

    "accounts", "cookies", "cache",

}





def should_skip(path: Path) -> bool:

    rel = path.relative_to(ROOT)

    parts = set(rel.parts)

    if "matrix_runs" in parts:

        name = path.name

        if name.startswith("_CODEX_MATRIX_18r43") or name.startswith("MATRIX_18r43_") or (

            name.startswith("matrix_18r43_") and name.endswith("_summary.json")

        ) or name.startswith("_CODEX_MATRIX_18r43_BOARD") or name.startswith("_CODEX_MATRIX_18r43_LIVE"):

            return False

        return True

    if parts & SKIP_DIR_NAMES:

        return True

    name = path.name.lower()

    if name.endswith((".pyc", ".log", ".zip", ".sqlite3", ".db")):

        return True

    if any(x in name for x in ("accounts_registered", "accounts_pending", "accounts_importable", "accounts_reregistered")):

        return True

    if name == "config.json":

        return True

    return False





def collect_files():

    files = []

    for p in ROOT.rglob("*"):

        if not p.is_file():

            continue

        if should_skip(p):

            continue

        rel = p.relative_to(ROOT)

        if rel.parts[0] in {"web", "protocol", "cpa_xai", "tools", "scripts", "tests"} or rel.suffix in {

            ".py", ".md", ".txt", ".html", ".css", ".js", ".ps1", ".json",

        }:

            files.append(p)

    uniq = []

    seen = set()

    for f in files:

        r = f.resolve()

        if r in seen:

            continue

        seen.add(r)

        uniq.append(f)

    return sorted(uniq, key=lambda x: str(x).lower())





def main():

    if ZIP.exists() or PKG.exists():

        raise SystemExit(f"Refuse overwrite existing package: {PKG_NAME}")

    files = collect_files()

    PKG.mkdir(parents=True, exist_ok=False)

    copied = []

    for src in files:

        rel = src.relative_to(ROOT)

        dst = PKG / rel

        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, dst)

        copied.append(rel.as_posix())



    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    notes = [
        f"# {PKG_NAME}",
        f"built={ts}",
        "",
        "## Highlights",
        "- multi-thread silent stable matrix 18r43 (workers=20 preheat=40 count=1000)",
        "- hybrid only + SOCKS5 outlook/aol x2 each",
        "- pending_sso recovery SOCKS5 x2",
        "- stop registration tests x2",
        "- UI top metric: awaiting_pool with success/fail live",
        "- 18r43a: mail_token never counts success; multi post-success workers default 6",
        "- 18r43b: dual_send_lock strict; freeze-reclick throttle; soft net_hits yield",
        "- 18r43c: register /api/start also reloads browser.token_harvester",
        "- 18r43d: post_success_workers=6 at cell config; early ensure; drain timeout scales with awaiting_pool depth",
        "- 18r43e: matrix resume/attach running job; supervisor auto-restart dead matrix; start skips if alive",
        "- 18r43f: Sub2API verify fail-fast permanent permission-denied; matrix verify_timeout=35 attempts=1",
        "- 18r43g: register count is SUCCESS target (pending/fail no longer end job early)",
        "- 18r43h: post_success task_done guard + auto-replace dead drain workers (awaiting_pool)",
        "- SSO vs mail_token import fix: reject mail_token as SSO; export importable session SSO only",
        "- silence edge_safe (never minimize/kill user Edge)",
        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",
        "- no overwrite of 18r40/18r41/18r42 packages",
        "",
        f"## Files count={len(copied)}",
        "",
    ]

    (PKG / "PACKAGE_NOTES.md").write_text("\n".join(notes), encoding="utf-8")

    (PKG / "STABLE_VERSION").write_text(PKG_NAME + "\n", encoding="utf-8")



    cl = ROOT / "CHANGELOG.md"

    entry = (

        f"\n## {PKG_NAME}\n"

        f"- date: {ts}\n"

        f"- silent multi-thread stable matrix 18r43 (workers=20 preheat=40 count=1000)\n"

        f"- fix: pending_sso mail_token cannot import as SSO; export importable session SSO only\n"

        f"- package: packages/{PKG_NAME}.zip (no overwrite of prior packages)\n"

    )

    if cl.exists():

        prev = cl.read_text(encoding="utf-8", errors="replace")

        if PKG_NAME not in prev:

            cl.write_text(prev.rstrip() + "\n" + entry, encoding="utf-8")

    else:

        cl.write_text("# Changelog\n" + entry, encoding="utf-8")

    shutil.copy2(cl, PKG / "CHANGELOG.md")



    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        for src in PKG.rglob("*"):

            if src.is_file():

                zf.write(src, arcname=str(Path(PKG_NAME) / src.relative_to(PKG)))



    h = hashlib.sha256(ZIP.read_bytes()).hexdigest()

    (PKG / "SHA256.txt").write_text(f"{h}  {ZIP.name}\n", encoding="utf-8")

    print(f"OK package dir={PKG}")

    print(f"OK zip={ZIP}")

    print(f"OK files={len(copied)} sha256={h[:16]}...")





if __name__ == "__main__":

    main()

