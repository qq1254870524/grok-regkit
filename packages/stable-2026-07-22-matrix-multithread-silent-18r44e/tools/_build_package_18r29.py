"""Build 18r29 package + docs stub. Does not overwrite older packages."""
from __future__ import annotations
import json, shutil, zipfile, datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
TAG = "stable-2026-07-19-matrix-singlethread-18r29"
PKG_DIR = ROOT / "packages" / TAG
ZIP_PATH = ROOT / "packages" / f"{TAG}.zip"
OUT_MATRIX = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"

INCLUDE = [
    "hybrid_register.py",
    "grok_register_ttk.py",
    "outlook_mail.py",
    "aol_mail.py",
    "browser/token_harvester.py",
    "web/server.py",
    "web/static",
    "tools/matrix_cross_run.py",
    "cpa_export.py",
    "sub2api_client.py",
    "CHANGELOG.md",
    "STABLE_VERSION.md",
    "MATRIX_REPORT.md",
    "README.md",
    "RESTORE_NOTES.md",
    "requirements.txt",
]

def copy_path(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def main():
    if ZIP_PATH.exists():
        raise SystemExit(f"refuse overwrite existing {ZIP_PATH}")
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)
    for rel in INCLUDE:
        src = ROOT / rel
        if src.exists():
            copy_path(src, PKG_DIR / rel)
    # matrix report if present
    if (OUT_MATRIX / "REPORT.md").exists():
        shutil.copy2(OUT_MATRIX / "REPORT.md", PKG_DIR / "MATRIX_18r29_REPORT.md")
    if (OUT_MATRIX / "summary.jsonl").exists():
        shutil.copy2(OUT_MATRIX / "summary.jsonl", PKG_DIR / "MATRIX_18r29_summary.jsonl")
    meta = {
        "tag": TAG,
        "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "purpose": "single-thread stable matrix 18r29 + outlook identity_confirm_blocked 1078",
    }
    (PKG_DIR / "PACKAGE_META.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PKG_DIR.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(PKG_DIR.parent).as_posix())
    print("OK", ZIP_PATH, ZIP_PATH.stat().st_size)

if __name__ == "__main__":
    main()
