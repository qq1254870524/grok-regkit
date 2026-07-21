# -*- coding: utf-8 -*-
"""Package stable-2026-07-22-matrix-multithread-silent-18r44e (no overwrite)."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
PKG_NAME = "stable-2026-07-22-matrix-multithread-silent-18r44e"
PKG = ROOT / "packages" / PKG_NAME
ZIP = ROOT / "packages" / f"{PKG_NAME}.zip"

SKIP_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", "packages",
    ".venv", "venv", "chrome_profiles", "profiles", "data", "logs",
    "accounts", "cookies", "cache", "_hot", "matrix_runs",
    ".chrome-data", "chrome-data", "cpa_auths", "cpa_xai",
}
INCLUDE_TOP = {
    "web", "protocol", "tools", "scripts", "tests", "browser",
}
INCLUDE_ROOT_FILES = {
    "hybrid_register.py", "grok_register_ttk.py", "worker_coord.py",
    "sub2api_client.py", "pending_sso_recovery.py", "CHANGELOG.md",
    "README.md", "requirements.txt", "config.example.json",
}
CORE_FILES = [
    "worker_coord.py",
    "web/server.py",
    "sub2api_client.py",
    "grok_register_ttk.py",
    "hybrid_register.py",
    "browser/token_harvester.py",
    "tools/matrix_18r44_silent_stable.py",
    "tools/_backfill_8010_to_8011_18r44d.py",
    "tools/_pending_sso_full_monitor_18r44e.py",
    "tools/_package_18r44e_release.py",
    "tools/start_web8092_hidden.ps1",
    "tools/start_hidden.ps1",
]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(p in SKIP_DIR_NAMES for p in rel.parts):
        return True
    name = path.name.lower()
    if name.endswith((".pyc", ".log", ".zip", ".sqlite3", ".db", ".bak")):
        return True
    if any(x in name for x in (
        "accounts_registered", "accounts_pending", "accounts_importable",
        "accounts_reregistered", "token.json", "config.json",
    )):
        return True
    if ".bak" in name or name.startswith("_tmp"):
        return True
    return False


def collect_files():
    files = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or should_skip(p):
            continue
        rel = p.relative_to(ROOT)
        if rel.parts[0] in INCLUDE_TOP:
            files.append(p)
            continue
        if len(rel.parts) == 1 and (
            rel.name in INCLUDE_ROOT_FILES or rel.suffix in {".py", ".md", ".ps1", ".txt"}
        ):
            if not rel.name.startswith("test_"):
                files.append(p)
    # include cpa_xai python only
    for p in (ROOT / "cpa_xai").rglob("*.py"):
        if p.is_file() and "__pycache__" not in p.parts:
            files.append(p)
    for rel in CORE_FILES:
        fp = ROOT / rel
        if fp.is_file() and fp not in files:
            files.append(fp)
    uniq, seen = [], set()
    for f in files:
        r = f.resolve()
        if r in seen:
            continue
        seen.add(r)
        uniq.append(f)
    return uniq


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def main():
    if PKG.exists() or ZIP.exists():
        raise SystemExit(f"REFUSE overwrite existing {PKG_NAME}")
    files = collect_files()
    PKG.mkdir(parents=True)
    notes = f"""# {PKG_NAME}

## 版本定位

多线程**静默稳定**版本 **18r44e**（追加发行，**不覆盖** 18r44d/18r44c）。

构建时间: {datetime.now().isoformat(timespec="seconds")}

## 本版关键（二次补 SSO 全链路实测 + 修复）

### 实跑结果 `matrix_runs/pending_sso_full_20260722_040327`
| r | class | success | fail | ΔG2A | ΔSub2 | ΔCPA |
|---:|---|---:|---:|---:|---:|---:|
| 1 | success | 5 | 0 | 5 | 5 | 5 |
| 2 | success | 7 | 0 | 7 | 7 | 7 |

- **合计成功 12**，号池与 CPA 全对齐（base g2a 3786→3798 / sub2 3897→3909 / cpa 2529→2541）
- **无 pool_gap**，无真·入池失败，无 CPA 导出失败（authcode mint 成功）
- **停止注册实测 ok=True**：`running_before=true` → `running_after=false`，面板 8092 仍存活，网关 8010/8011/8080 保留

### 代码修复
1. **Sub2 可用性验证**
   - 网络 Read timeout / ConnectionError 自动延长超时并额外重试
   - 文案改为「可用性验证未通过(账号已入池,仅观察)」，避免误判为入池失败
   - `require_verify_success=false` 时 create 成功即入池成功
2. **监控 FAIL 误报**
   - 排除 `fail=0`、`ok=2 fail=0`、`非入池失败` 等假 FAILHIT
3. **继承 18r44d**
   - SOCKS5 LIVE 预检后再开浏览器
   - G2A 双写 8010 primary + 8011 mirror→8020

## 工具
- `tools/_pending_sso_full_monitor_18r44e.py` — 二次补 SSO 多轮 + 入池/CPA + stop 监控
- `tools/_backfill_8010_to_8011_18r44d.py` — 8010→8011 回填

## 校验
- pending_sso 2 轮 success，入池 1:1
- `/api/stop` stop_ok
- py_compile 通过
"""
    (PKG / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    # copy report if present
    rep = ROOT / "matrix_runs" / "pending_sso_full_20260722_040327" / "REPORT.md"
    if rep.is_file():
        (PKG / "PENDING_SSO_REPORT.md").write_text(rep.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

    cl = ROOT / "CHANGELOG.md"
    entry = f"""
## {PKG_NAME} — {datetime.now().strftime('%Y-%m-%d')}

- 二次补 SSO 全链路实跑 2 轮：success 5+7=12，G2A/Sub2/CPA 增量 1:1，无 pool_gap
- 停止注册实测：stop Event + 清 running + 异步清浏览器；面板存活，网关保留
- Sub2 可用性验证：网络超时延长重试；日志不再误报「入池失败」
- 监控 FAIL_PAT 排除 fail=0 / 非入池失败 假阳性
- 不覆盖 18r44d/18r44c packages/tags
"""
    if cl.exists():
        old = cl.read_text(encoding="utf-8", errors="replace")
        if PKG_NAME not in old:
            cl.write_text(entry + "\n" + old, encoding="utf-8")
    else:
        cl.write_text("# Changelog\n" + entry, encoding="utf-8")

    manifest = []
    for src in files:
        rel = src.relative_to(ROOT)
        dst = PKG / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest.append({"path": str(rel).replace("\\", "/"), "sha256": sha256(src), "bytes": src.stat().st_size})
    (PKG / "MANIFEST.json").write_text(
        json.dumps({"name": PKG_NAME, "files": manifest, "count": len(manifest)}, indent=2),
        encoding="utf-8",
    )
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PKG.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(PKG.parent)).replace("\\", "/"))
    print("PKG", PKG)
    print("ZIP", ZIP, ZIP.stat().st_size)
    print("FILES", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
