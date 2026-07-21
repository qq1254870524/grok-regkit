# -*- coding: utf-8 -*-
"""Package stable-2026-07-21-matrix-multithread-silent-18r42 (source-only, no overwrite)."""
from __future__ import annotations
import hashlib
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
PKG_NAME = "stable-2026-07-21-matrix-multithread-silent-18r42"
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
        if name.startswith("_CODEX_MATRIX_18r42") or name.startswith("MATRIX_18r42_") or (
            name.startswith("matrix_18r42_") and name.endswith("_summary.json")
        ) or name.startswith("_CODEX_MATRIX_18r42_BOARD") or name.startswith("_CODEX_MATRIX_18r42_LIVE"):
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
        "- multi-thread silent matrix 18r42 (workers=10 preheat=20 count=100)",
        "- hybrid + browser SOCKS5 outlook/aol x2 each",
        "- pending_sso recovery SOCKS5 x2",
        "- stop registration tests x2",
        "- SSO vs mail_token import fix (18r42d): reject mail_token as SSO; export importable session SSO",
        "- silence edge_safe (never minimize/kill user Edge)",
        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",
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
        f"- silent multi-thread matrix 18r42 completed packaging\n"
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
