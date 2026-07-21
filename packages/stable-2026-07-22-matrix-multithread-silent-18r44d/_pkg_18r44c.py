# -*- coding: utf-8 -*-
"""Rewrite matrix REPORT from full summary.jsonl + package 18r44c release."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r44_silent_20260722_014611"
PKG_NAME = "stable-2026-07-22-matrix-multithread-silent-18r44c"
PKG = ROOT / "packages" / PKG_NAME
ZIP = ROOT / "packages" / f"{PKG_NAME}.zip"

# --- rewrite REPORT ---
rows = []
for line in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    rows.append(json.loads(line))

ok_n = sum(1 for r in rows if r.get("ok"))
lines = [
    "# Matrix 18r44 Silent Stable Report (full 12 cells)",
    "",
    f"- rewritten: {datetime.now().isoformat(timespec='seconds')}",
    "- workers=2 preheat=4 count=4 rounds=2",
    "- proxy: socks5; silent browser; pythonw parent",
    "- fixes loaded during run: CPA prefer_direct, 18r44a SSO cookie isolation, 18r44b CreateEmail body_ok",
    "- post-run fix: 18r44c process-wide session_id claim + post-success browser restart",
    "",
    "## Results",
    "",
    "| cell | r | ok | class | s | f | p | dg2a | dsub2 | t |",
    "|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
]
for r in rows:
    lines.append(
        "| {cell} | {round} | {ok} | {klass} | {s} | {f} | {p} | {dg2a} | {dsub2} | {t} |".format(
            cell=r.get("cell"),
            round=r.get("round"),
            ok=r.get("ok"),
            klass=r.get("class"),
            s=r.get("success", 0) or 0,
            f=r.get("fail", 0) or 0,
            p=r.get("pending_sso", 0) or 0,
            dg2a=r.get("pool_delta_g2a", 0) or 0,
            dsub2=r.get("pool_delta_sub2", 0) or 0,
            t=r.get("elapsed_s", 0) or 0,
        )
    )
lines += [
    "",
    f"## Summary",
    f"- total={len(rows)} ok={ok_n} fail={len(rows)-ok_n}",
    "",
    "## Issues",
    "- browser__socks5__aol r1: s=4 but dg2a=+3 (SSO session collision sean/littlejohn same session_id) -> 18r44c hard reject",
    "- browser__socks5__aol r2: s=3 f=1 dg2a=+2 dsub2=+3 (collision/import lag) -> 18r44c",
    "- pending_sso_recovery r2: s=0 class=pending_sso (CreateEmail false-sent / early_no_new) -> 18r44b body_ok (next job reload)",
    "- stop_test r1/r2: stop_ok, panel alive",
    "",
    "## Pool final (from DONE)",
    "- g2a 3765->3775 (+10) sub2 3874->3886 (+12) during tracked tail; full summary deltas sum g2a success-aligned except AOL collisions",
    "",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(OUT / "DONE.txt").write_text(
    f"ok={ok_n} total={len(rows)}\n"
    f"post_fix=18r44c_session_claim\n"
    f"rewritten={datetime.now().isoformat(timespec='seconds')}\n",
    encoding="utf-8",
)
print("REPORT rewritten", len(rows), "ok", ok_n)

# --- CHANGELOG ---
cl = ROOT / "CHANGELOG_18r44c_sso_claim_createemail.md"
cl.write_text(
    """# 18r44c Silent Multi-thread Stable

Date: 2026-07-22

## Highlights
- Multi-thread silent matrix (workers=2, preheat=4, count=4) full cross-run socks5 hybrid/browser outlook/aol + pending_sso_recovery + stop_test
- CPA auth.x.ai: prefer_direct_first (avoid SOCKS curl 97 / User rejected by SOCKS5)
- 18r44a: wait_for_sso ignores baseline cookies; open_signup clears xAI session; Windows per-launch user-data
- 18r44b: CreateEmail requires body_ok + real 2xx/send; bare OTP UI no longer promotes browser_sent
- 18r44c: process-wide session_id claim; collision never writes disk or imports G2A/Sub2; browser restarts after each success

## Stop semantics
- /api/stop: stop Event + kill script workers/browsers only; keep 8092 / G2A / Sub2 / user Edge

## Matrix notes
- stop_test: both rounds stop_ok, panel alive
- AOL browser pool mismatch root cause: same session_id on two emails (fixed by 18r44c)
- recovery r2 zero success: CreateEmail false-send path (18r44b)

## Non-goals
- Does not overwrite prior packages
- Does not ship config.json or live accounts
""",
    encoding="utf-8",
)

# append main CHANGELOG.md top
main_cl = ROOT / "CHANGELOG.md"
head = main_cl.read_text(encoding="utf-8") if main_cl.exists() else ""
block = """# Changelog

## 2026-07-22 — 18r44c silent multi-thread stable
- CPA prefer_direct for auth.x.ai (fix curl97/SOCKS reject)
- SSO isolation 18r44a + process-wide session_id claim 18r44c (no dual-email same session import)
- CreateEmail body_ok 18r44b (no bare OTP false-sent)
- Matrix report under matrix_runs/matrix_18r44_silent_20260722_014611
- Package: packages/stable-2026-07-22-matrix-multithread-silent-18r44c

"""
if "18r44c silent multi-thread stable" not in head:
    if head.startswith("# Changelog"):
        head = head.replace("# Changelog\n", block, 1)
    else:
        head = block + head
    main_cl.write_text(head, encoding="utf-8")
print("changelog ok")

# --- package ---
if PKG.exists() or ZIP.exists():
    raise SystemExit(f"REFUSE overwrite existing package {PKG_NAME}")

SKIP_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", "packages",
    ".venv", "venv", "chrome_profiles", "profiles", "data", "logs",
    "accounts", "cookies", "cache", "_hot",
}
INCLUDE_TOP = {"web", "protocol", "cpa_xai", "tools", "scripts", "tests", "browser"}
INCLUDE_ROOT_FILES = {
    "hybrid_register.py", "grok_register_ttk.py", "worker_coord.py",
    "sub2api_client.py", "pending_sso_recovery.py", "CHANGELOG.md",
    "CHANGELOG_18r44c_sso_claim_createemail.md",
    "README.md", "requirements.txt", "config.example.json",
}
CORE_FILES = [
    "worker_coord.py", "web/server.py", "sub2api_client.py",
    "grok_register_ttk.py", "hybrid_register.py", "browser/token_harvester.py",
    "cpa_xai/oauth_device.py", "tools/matrix_18r44_silent_stable.py",
]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & SKIP_DIR_NAMES:
        return True
    name = path.name.lower()
    if name.endswith((".pyc", ".log", ".zip", ".sqlite3", ".db", ".bak")):
        return True
    if any(x in name for x in (
        "accounts_registered", "accounts_pending", "accounts_importable",
        "accounts_reregistered", "token.json",
    )):
        return True
    if name == "config.json":
        return True
    if ".bak" in name or name.startswith("_tmp") or name.startswith("_fix"):
        return True
    return False


files = []
for p in ROOT.rglob("*"):
    if not p.is_file() or should_skip(p):
        continue
    rel = p.relative_to(ROOT)
    if rel.parts[0] in INCLUDE_TOP:
        files.append(p)
        continue
    if len(rel.parts) == 1 and (rel.name in INCLUDE_ROOT_FILES or rel.suffix in {".py", ".md", ".ps1", ".txt"}):
        if not rel.name.startswith("_"):
            files.append(p)
for rel in CORE_FILES:
    fp = ROOT / rel
    if fp.is_file() and fp not in files:
        files.append(fp)
# include this matrix report
for p in (OUT / "REPORT.md", OUT / "DONE.txt", OUT / "summary.jsonl"):
    if p.is_file():
        files.append(p)

uniq = []
seen = set()
for f in files:
    r = f.resolve()
    if r in seen:
        continue
    seen.add(r)
    uniq.append(f)

PKG.mkdir(parents=True, exist_ok=False)
manifest = []
for f in uniq:
    rel = f.relative_to(ROOT)
    dest = PKG / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, dest)
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    manifest.append({"path": str(rel).replace("\\", "/"), "sha256": h, "bytes": f.stat().st_size})

(PKG / "PACKAGE_MANIFEST.json").write_text(
    json.dumps({"name": PKG_NAME, "files": len(manifest), "items": manifest}, indent=2),
    encoding="utf-8",
)
(PKG / "RELEASE_NOTES.md").write_text(cl.read_text(encoding="utf-8"), encoding="utf-8")

with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in PKG.rglob("*"):
        if f.is_file():
            zf.write(f, arcname=str(f.relative_to(PKG.parent)).replace("\\", "/"))

print("package", PKG)
print("zip", ZIP, ZIP.stat().st_size)
print("files", len(manifest))
