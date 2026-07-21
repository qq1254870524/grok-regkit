"""When REPORT ready: update docs, build package, git commit/tag/push/release.
Does NOT overwrite existing packages/tags.
"""
from __future__ import annotations
import json, os, shutil, subprocess, time, zipfile
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
TAG = "stable-2026-07-19-matrix-singlethread-18r29"
PKG_DIR = ROOT / "packages" / TAG
ZIP_PATH = ROOT / "packages" / f"{TAG}.zip"
STATE = ROOT / "matrix_runs" / "_publish_18r29_state.txt"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with STATE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def reclassify_summary_pending_burns():
    """18r29f post-hoc: if round log has burn markers, class early_no_new_mail -> pending_sso."""
    sj = OUT / "summary.jsonl"
    if not sj.exists():
        return 0
    rows = []
    fixed = 0
    for line in sj.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("class") in ("early_no_new_mail", "sso_timeout") or (r.get("fail", 0) > 0 and r.get("pending_sso", 0) == 0 and not r.get("ok")):
            logp = OUT / f"{r.get('cell')}_r{int(r.get('round') or 0):02d}.log"
            if logp.exists():
                txt = logp.read_text(encoding="utf-8", errors="replace")
                markers = (
                    "pending_sso saved",
                    "mailbox burned to pending_sso",
                    "browser/cli mail fail -> pending_sso",
                    "browser mail fail -> pending_sso",
                    "pending_sso:browser_code_fail",
                    "pending_sso:early_no",
                )
                if any(m in txt for m in markers):
                    r["class"] = "pending_sso"
                    r["pending_sso"] = max(1, int(r.get("pending_sso") or 0))
                    r["fail"] = 0
                    r["ok"] = False
                    r["reclassified_18r29f"] = True
                    fixed += 1
                elif ("未找到邮箱输入框" in txt) or ("inputs=none" in txt.lower()) or ("未找到邮箱输入框或注册按钮" in txt):
                    r["class"] = "create_email_fail"
                    r["reclassified_18r29g"] = True
                    fixed += 1
        rows.append(r)
    if fixed:
        sj.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        log(f"reclassified_summary_pending_burns fixed={fixed}")
    return fixed
def run(cmd, check=True):
    log("RUN " + " ".join(cmd) if isinstance(cmd, list) else str(cmd))
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if p.stdout:
        log(p.stdout[-2000:])
    if p.stderr:
        log("ERR " + p.stderr[-1500:])
    if check and p.returncode != 0:
        raise SystemExit(p.returncode)
    return p

# wait report
log("waiting REPORT")
while not (OUT / "REPORT.md").exists():
    time.sleep(20)
log("REPORT found")
time.sleep(3)

# summarize
rows = []
if (OUT / "summary.jsonl").exists():
    rows = [json.loads(x) for x in (OUT / "summary.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
by = defaultdict(list)
for r in rows:
    by[r.get("cell")].append(r)
report_extra = ["", "## 18r29 live matrix summary", ""]
for c, items in sorted(by.items()):
    rounds = {}
    for it in items:
        ri = it.get("round")
        prev = rounds.get(ri)
        if prev is None or (it.get("ok") and not prev.get("ok")):
            rounds[ri] = it
    ok = sum(1 for v in rounds.values() if v.get("ok"))
    cls = dict(Counter(v.get("class") for v in rounds.values()))
    report_extra.append(f"- `{c}`: ok={ok}/{len(rounds)} classes={cls}")
report_extra.append("")
report_extra.append(f"- summary_rows={len(rows)} global_classes={dict(Counter(r.get('class') for r in rows))}")
report_extra.append(f"- marked={datetime.now().isoformat(timespec='seconds')}")
report_body = (OUT / "REPORT.md").read_text(encoding="utf-8", errors="replace")
(ROOT / "MATRIX_REPORT.md").write_text(
    "# MATRIX_REPORT\n\n## 18r29 single-thread 10x10\n\n" + report_body + "\n" + "\n".join(report_extra) + "\n",
    encoding="utf-8",
)

chg = """## 2026-07-19r29 / restore: stable-2026-07-19-matrix-singlethread-18r29

- **单线程稳定版**全矩阵实跑：`tools/matrix_cross_run.py 10 720`（hybrid/browser × direct/socks5_list × outlook/aol + pending_sso×2），每格 10 轮，`count=1`。
- **Outlook 1078**：`identity/confirm` + `error.aspx?errcode=1078` → `identity_confirm_blocked` permanent，立即删池，禁止 12 步空转。
- 主路径不变：注册成功 → 即时 SSO → g2a/Sub2API/CPA/NSFW；pending 仅兜底；日志应用内明文。
- **18r29b**：browser `early_no_new_mail`/验证码超时 → `burn_mailbox_to_pending` + 删池，与 hybrid 对齐。
- **18r29c**：`sub2api_client.import_grok_sso` 对上游 429/rate-limit 退避重试 5 次（5/12/25/40/60s）；Sub2API `sso_device.go` device/code 429 退避。
- **18r29d**：矩阵 classify 优先识别 pending burn 标记，避免 early_no 覆盖 pending。
- **18r29k**：后处理顺序 NSFW→G2A→CPA→Sub2API；`import_after_success_prefer_cpa` 优先 CPA OAuth 入 Sub2API，失败落盘 + `backfill_missing_sub2api_from_cpa_and_sso`；`reconcile_pools` 对账 TXT/token/G2A/Sub2API/CPA；Web 热加载后 Sub2API 导入不再因旧模块缺符号失败。
- **18r29j**：pending 仅一次登录；失败 hybrid 重注册；矩阵 guardian 同 OUT 续跑。
- **18r29e**：browser 路径 `pending_sso:*` 异常计入 pending 而非 fail，结束日志带 pending_sso 计数。
- **18r29f**：burn 成功即累计 pending_sso；burn 后空失败/页未就绪不硬 fail；矩阵 run_one 以日志 burn 标记优先归 pending。
- 矩阵产物：`matrix_runs/matrix_18r29_*` + `REPORT.md`；Packages **新增**本 tag（不覆盖历史）。

"""
cl = ROOT / "CHANGELOG.md"
old = cl.read_text(encoding="utf-8") if cl.exists() else "# CHANGELOG\n"
if "2026-07-19r29" not in old:
    if old.startswith("# CHANGELOG"):
        cl.write_text(old.replace("# CHANGELOG\n", "# CHANGELOG\n\n" + chg, 1), encoding="utf-8")
    else:
        cl.write_text(chg + old, encoding="utf-8")

sv = f"""# STABLE_VERSION — known-good restore points

> **当前推荐还原点**：`{TAG}`（单线程矩阵 18r29 稳定版）  
> **业务代码完美点（pending 一次登录）**：`stable-2026-07-19-pending-one-login-18r28h`  
> **历史 packages/releases 一律保留，禁止覆盖。**

## Latest — {TAG}（18r29）

| 项 | 值 |
|----|----|
| Tag / Release | `{TAG}` |
| Marked at | {datetime.now().date().isoformat()} |
| Purpose | 单线程 10 轮交叉矩阵稳定 + Outlook 1078 永久剔号 |
| Repo | https://github.com/qq1254870524/grok-regkit |
| Package | `packages/{TAG}.zip` |

### 还原

```bash
git fetch mygithub --tags
git checkout {TAG}
```

## 历史

见 git tags / `packages/stable-2026-07-19-*.zip`（全部保留）。
"""
(ROOT / "STABLE_VERSION.md").write_text(sv, encoding="utf-8")

# package
if ZIP_PATH.exists():
    log(f"zip exists skip rebuild {ZIP_PATH}")
else:
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)
    include = [
        "hybrid_register.py", "grok_register_ttk.py", "outlook_mail.py", "aol_mail.py", "sub2api_client.py",
        "browser", "web", "tools/matrix_cross_run.py", "cpa_export.py",
        "CHANGELOG.md", "STABLE_VERSION.md", "MATRIX_REPORT.md", "README.md", "RESTORE_NOTES.md",
        "requirements.txt",
    ]
    for rel in include:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = PKG_DIR / rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    if (OUT / "REPORT.md").exists():
        shutil.copy2(OUT / "REPORT.md", PKG_DIR / "MATRIX_18r29_REPORT.md")
    if (OUT / "summary.jsonl").exists():
        shutil.copy2(OUT / "summary.jsonl", PKG_DIR / "MATRIX_18r29_summary.jsonl")
    (PKG_DIR / "PACKAGE_META.json").write_text(json.dumps({"tag": TAG, "built_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PKG_DIR.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(PKG_DIR.parent).as_posix())
    log(f"package {ZIP_PATH} size={ZIP_PATH.stat().st_size}")

# git
run(["git", "add", "-A", "outlook_mail.py", "hybrid_register.py", "grok_register_ttk.py", "sub2api_client.py", "tools/matrix_cross_run.py", "tools/reconcile_pools.py", "tools/_backfill_sub2api_18r29k.py", "CHANGELOG.md", "STABLE_VERSION.md", "MATRIX_REPORT.md", "packages/" + TAG, "packages/" + TAG + ".zip"], check=False)
# add new tool helpers if tracked wanted
run(["git", "status", "-sb"], check=False)
msg = "release(18r29): single-thread matrix stable + outlook 1078 permanent burn"
p = run(["git", "commit", "-m", msg], check=False)
tp = subprocess.run(["git", "rev-parse", TAG], cwd=ROOT, capture_output=True, text=True)
if tp.returncode == 0:
    log(f"tag already exists {TAG}, skip retag")
else:
    run(["git", "tag", TAG])
run(["git", "push", "mygithub", "HEAD:main"], check=False)
run(["git", "push", "mygithub", TAG], check=False)
# release
notes = ROOT / "matrix_runs" / "_release_notes_18r29.md"
notes.write_text(chg + "\n" + "\n".join(report_extra) + "\n", encoding="utf-8")
run([
    "gh", "release", "create", TAG,
    str(ZIP_PATH),
    "--repo", "qq1254870524/grok-regkit",
    "--title", TAG,
    "--notes-file", str(notes),
], check=False)
log("DONE publish attempt")


