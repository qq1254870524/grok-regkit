# -*- coding: utf-8 -*-
"""Package stable-2026-07-21-matrix-multithread-silent-18r43n (no overwrite)."""
from __future__ import annotations
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
PKG_NAME = "stable-2026-07-21-matrix-multithread-silent-18r43n"
PKG = ROOT / "packages" / PKG_NAME
ZIP = ROOT / "packages" / f"{PKG_NAME}.zip"

SKIP_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", "packages",
    ".venv", "venv", "chrome_profiles", "profiles", "data", "logs",
    "accounts", "cookies", "cache", "_hot",
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
    "tools/matrix_18r43_silent_stable_mt.py",
    "tools/start_matrix18r43_hidden.ps1",
    "tools/_parallel_sub2_fill_18r43n.py",
    "tools/_full_pool_fill_18r43n.py",
]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & SKIP_DIR_NAMES:
        return True
    name = path.name.lower()
    if name.endswith((".pyc", ".log", ".zip", ".sqlite3", ".db", ".bak")):
        return True
    if name.startswith(".") and name not in {".gitignore"}:
        return False
    if any(x in name for x in (
        "accounts_registered", "accounts_pending", "accounts_importable",
        "accounts_reregistered", "token.json",
    )):
        return True
    if name == "config.json":
        return True
    if name.endswith(".bak") or ".bak_" in name or name.endswith(".bak_18r43n"):
        return True
    if name.startswith("_tmp") or name.startswith("_fix_pkg") or name.startswith("_hot"):
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
        if len(rel.parts) == 1 and (rel.name in INCLUDE_ROOT_FILES or rel.suffix in {".py", ".md", ".ps1", ".txt"}):
            if not rel.name.startswith("_") and not rel.name.startswith("test_"):
                files.append(p)
    # always include core
    for rel in CORE_FILES:
        fp = ROOT / rel
        if fp.is_file() and fp not in files:
            files.append(fp)
    # matrix board docs only
    for p in (ROOT / "matrix_runs").glob("*18r43*"):
        if p.is_file() and p.suffix in {".md", ".json"} and not p.name.endswith(".jsonl"):
            if p.name.startswith("_CODEX_MATRIX_18r43") or p.name.endswith("_summary.json"):
                files.append(p)
    uniq = []
    seen = set()
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

多线程**静默稳定**版本 18r43n（追加发行，**不覆盖** 18r40/18r41/18r42）。

构建时间: {datetime.now().isoformat(timespec="seconds")}

## 本版修复（相对 18r42）

1. **Stop 逻辑**
   - `/api/stop` 立即 `running=false` + stop Event
   - 清理 pending/worker 线程，结束注册浏览器/chromedriver
   - **不杀** web / Sub2API / G2A / CPA / 用户 Microsoft Edge

2. **注册数量=成功配额**
   - `worker_coord` attempt 双 cap：`slots_started>=target` 且 `success>=target`
   - 修复 success 模式 `target*8` 导致 1000 设定跑出 1600+ 的问题

3. **代理池防清空**
   - `_sync_proxy_list_file(allow_clear=...)`
   - put_config 仅在 payload 含 `proxy_list` 时同步；空列表默认不擦非空文件

4. **Sub2API 管理凭据解析**
   - `sub2api_client._resolve_runtime_config()` 避免 “管理员邮箱未配置”

5. **号池回填彻底**
   - 回填源并入 `accounts*.txt` 的 **session SSO**
   - 拒绝 **mail_token**（`sso_len~2477 keys=['config']`）当 SSO
   - G2A 全量扫 accounts；pending dead mail_token 归档
   - 并行回填结果：missing 764 → ok=764 fail=0；Sub2 回填后 ~3861；G2A 3752

6. **静默 / 不打扰前台**
   - `pythonw` / Hidden 启动
   - force_kill 仅脚本 chrome/chromedriver，排除用户 Edge

7. **8092 可用性**
   - stop 不阻塞事件循环；结束注册≠杀 web 本身

## 运行参数参考（本版验证相关）

- 线程 / 预热 / 数量：矩阵交叉已测；大规模建议 workers=20 preheat=40 count=1000
- 注册模式：混合
- 代理：SOCKS5
- 邮箱：微软 / AOL / 二次补 SSO（session SSO only）

## 明确不覆盖

- `packages/stable-2026-07-21-matrix-multithread-18r40*`
- `packages/stable-2026-07-21-matrix-multithread-18r41*`
- `packages/stable-2026-07-21-matrix-multithread-silent-18r42*`

## 关联 G2A 双轨包

- 生产 Python+本地定制: `stable-2026-07-22-g2a-python-204rc4-peer-sub2`
- 上游 Go v3.0.7 评估: `stable-2026-07-22-g2a-upstream-go-v307`
- 说明见 g2a 仓库 `CHANGELOG_2026-07-21_upstream_v307_dual_track.md`

## 文件清单哈希

打包后见 `SHA256SUMS.txt`。
"""
    (PKG / "PACKAGE_NOTES.md").write_text(notes, encoding="utf-8")
    (PKG / "CHANGELOG_18r43n.md").write_text(notes, encoding="utf-8")
    for f in files:
        rel = f.relative_to(ROOT)
        target = PKG / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    # root changelog snippet append file
    cl = ROOT / "CHANGELOG.md"
    if cl.exists():
        shutil.copy2(cl, PKG / "CHANGELOG.md")
    all_files = [p for p in PKG.rglob("*") if p.is_file()]
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in all_files:
            zf.write(p, f"{PKG_NAME}/{p.relative_to(PKG).as_posix()}")
    sums = [f"{sha256(p)}  {p.relative_to(PKG).as_posix()}" for p in sorted(all_files, key=lambda x: str(x))]
    sums.append(f"{sha256(ZIP)}  {ZIP.name}")
    (PKG / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    with zipfile.ZipFile(ZIP, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(PKG / "SHA256SUMS.txt", f"{PKG_NAME}/SHA256SUMS.txt")
    meta = {
        "package": PKG_NAME,
        "zip": str(ZIP),
        "size": ZIP.stat().st_size,
        "sha256": sha256(ZIP),
        "file_count": len(all_files),
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "pool_fill": {"ok": 764, "fail": 0, "sub2": 3861, "g2a": 3752},
    }
    (PKG / "RELEASE_META.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
