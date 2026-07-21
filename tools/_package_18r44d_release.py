# -*- coding: utf-8 -*-
"""Package stable-2026-07-22-matrix-multithread-silent-18r44d (no overwrite)."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
PKG_NAME = "stable-2026-07-22-matrix-multithread-silent-18r44d"
PKG = ROOT / "packages" / PKG_NAME
ZIP = ROOT / "packages" / f"{PKG_NAME}.zip"

SKIP_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", "packages",
    ".venv", "venv", "chrome_profiles", "profiles", "data", "logs",
    "accounts", "cookies", "cache", "_hot", "matrix_runs",
    ".chrome-data", "chrome-data",
}
INCLUDE_TOP = {
    "web", "protocol", "cpa_xai", "tools", "scripts", "tests", "browser",
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

多线程**静默稳定**版本 **18r44d**（追加发行，**不覆盖** 18r44c/18r43*）。

构建时间: {datetime.now().isoformat(timespec="seconds")}

## 本版关键修复

1. **SOCKS5 预检后再开浏览器**
   - `quick_check_proxy` / `pick_live_proxy` / `ensure_live_proxy_before_browser`
   - `start_browser` 启动 Chromium 前强制 LIVE 预检
   - 坏代理冷却 + `mark_proxy_bad`，降低首次 Chromium interstitial
2. **G2A 双目标入池（8010 + 8011→8020）**
   - `get_grok2api_remote_targets()` primary + mirror_v3
   - `config.json`: `grok2api_mirror_remote_base` / `grok2api_mirror_remote_app_key`
   - 新注册 SSO 同时写 8010 与桥 8011（v3 8020）
3. **回填工具** `tools/_backfill_8010_to_8011_18r44d.py`
   - 从 8010 拉真实 SSO 分批 POST 到 8011（服务端去重）
4. **矩阵实测** `matrix_18r44c_validate_20260722_031216`
   - 6/6 ok：browser AOL x2、pending_sso_recovery x2、stop_test x2
   - 入池 delta 与 success 对齐（8010/Sub2）

## 配置提示

```json
{{
  "grok2api_remote_base": "http://127.0.0.1:8010",
  "grok2api_mirror_remote_base": "http://127.0.0.1:8011",
  "grok2api_auto_add_remote": true
}}
```

8020 Go 版不要直接打旧 `/admin/api/tokens*`，走 8011 兼容桥。

## 变更文件（核心）

- grok_register_ttk.py
- worker_coord.py
- tools/_backfill_8010_to_8011_18r44d.py
- web/server.py（stop/status 既有逻辑）

## 校验

- py_compile 通过
- 矩阵 6/6 ok
- 8092 热载：需重启 web 进程后双写生效
"""
    (PKG / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    # update root CHANGELOG append
    cl = ROOT / "CHANGELOG.md"
    entry = f"""
## {PKG_NAME} — {datetime.now().strftime('%Y-%m-%d')}

- SOCKS5 LIVE 预检后再启动 Chromium，降低 interstitial 首开失败
- G2A 双写：8010 primary + 8011 mirror(v3/8020)
- 回填脚本 8010→8011；矩阵 18r44c 6/6 实测通过
- 不覆盖既有 packages/tags
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
    (PKG / "MANIFEST.json").write_text(json.dumps({"name": PKG_NAME, "files": manifest, "count": len(manifest)}, indent=2), encoding="utf-8")
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
