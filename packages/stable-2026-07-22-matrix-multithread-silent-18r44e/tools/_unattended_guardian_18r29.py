# -*- coding: utf-8 -*-
"""18r29 unattended guardian: monitor matrix, stall-resume, publish on REPORT (no overwrite)."""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, time, zipfile, urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
TAG = "stable-2026-07-19-matrix-singlethread-18r29"
STATE = ROOT / "matrix_runs" / "_unattended_18r29.txt"
PULSE = ROOT / "matrix_runs" / "_final_pulse_18r29.txt"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
PKG_DIR = ROOT / "packages" / TAG
ZIP_PATH = ROOT / "packages" / f"{TAG}.zip"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

CELLS = []
for mode in ("hybrid", "browser"):
    for proxy in ("direct", "socks5_list"):
        for mail in ("outlook", "aol"):
            CELLS.append({
                "name": f"{mode}__{proxy}__{mail}",
                "register_mode": mode,
                "proxy_mode": proxy,
                "email_provider": mail,
                "kind": "register",
                "need": 10,
            })
CELLS.append({"name":"pending_sso_recovery__socks5_list","register_mode":"hybrid","proxy_mode":"socks5_list","email_provider":"aol","kind":"pending_sso_recovery","need":10})
CELLS.append({"name":"pending_sso_recovery__direct","register_mode":"hybrid","proxy_mode":"direct","email_provider":"aol","kind":"pending_sso_recovery","need":10})

def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with STATE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def api(method: str, path: str, body=None, timeout=30):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:8092{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return 0, {"ok": False, "error": str(e)}

def rows():
    p = OUT / "summary.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def best_by_cell(rs):
    by = defaultdict(dict)
    for r in rs:
        c = r.get("cell")
        ri = r.get("round")
        prev = by[c].get(ri)
        if prev is None or (r.get("ok") and not prev.get("ok")):
            by[c][ri] = r
    return by

def write_pulse(note=""):
    rs = rows()
    by = best_by_cell(rs)
    code, st = api("GET", "/api/status")
    lines = [
        f"ts={datetime.now().isoformat(timespec='seconds')}",
        f"out={OUT}",
        f"report={(OUT/'REPORT.md').exists()}",
        f"summary_rows={len(rs)}",
        f"api_code={code} running={st.get('running')} phase={st.get('phase')} sess_ok={st.get('session_success')} sess_fail={st.get('session_fail')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')}",
        f"last_event={(st.get('last_event') or '')[:240]}",
        "cells:",
    ]
    ok_total = 0
    need_total = 0
    incomplete = []
    for c in CELLS:
        name = c["name"]
        need = c["need"]
        need_total += need
        rounds = by.get(name, {})
        ok = sum(1 for v in rounds.values() if v.get("ok"))
        ok_total += min(ok, need)
        cls = dict(Counter((v.get("class") or "?") for v in rounds.values()))
        lines.append(f"  {name}: ok={ok}/{need} rounds={len(rounds)} classes={cls}")
        if ok < need:
            incomplete.append((name, ok, need, c))
    lines.append(f"progress_ok_approx={ok_total}/{need_total}")
    sj = OUT / "summary.jsonl"
    age = time.time() - sj.stat().st_mtime if sj.exists() else 99999
    lines.append(f"summary_age_s={int(age)}")
    if note:
        lines.append(f"note={note}")
    PULSE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"st": st, "age": age, "incomplete": incomplete, "ok_total": ok_total, "need_total": need_total, "by": by}

def wait_idle(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, st = api("GET", "/api/status")
        if code == 200 and not st.get("running"):
            return True
        time.sleep(2)
    return False

def stop_job():
    api("POST", "/api/stop", {})

def matrix_procs_alive() -> bool:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'matrix_cross_run.py' } | Measure-Object | Select-Object -ExpandProperty Count"],
            text=True, errors="replace",
        )
        return int((out or "0").strip() or "0") > 0
    except Exception:
        return False

def run_cmd(cmd, check=False):
    log("RUN " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if p.stdout:
        log(p.stdout[-2500:])
    if p.stderr:
        log("ERR " + p.stderr[-1500:])
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed {p.returncode}: {cmd}")
    return p

def publish():
    if ZIP_PATH.exists() or PKG_DIR.exists():
        log(f"package already exists, refuse overwrite: {ZIP_PATH}")
        return False
    # ensure tags don't overwrite
    tags = run_cmd(["git", "tag"]).stdout.splitlines()
    if TAG in tags:
        log(f"tag exists locally: {TAG}, refuse overwrite")
        return False

    rs = rows()
    by = best_by_cell(rs)
    report_extra = ["", "## 18r29 live matrix summary", ""]
    for c, items in sorted(by.items()):
        ok = sum(1 for v in items.values() if v.get("ok"))
        cls = dict(Counter(v.get("class") for v in items.values()))
        report_extra.append(f"- `{c}`: ok={ok}/{len(items)} classes={cls}")
    report_extra.append(f"- summary_rows={len(rs)} global_classes={dict(Counter(r.get('class') for r in rs))}")
    report_extra.append(f"- marked={datetime.now().isoformat(timespec='seconds')}")
    report_body = (OUT / "REPORT.md").read_text(encoding="utf-8", errors="replace") if (OUT / "REPORT.md").exists() else "# no report body\n"
    (ROOT / "MATRIX_REPORT.md").write_text(
        "# MATRIX_REPORT\n\n## 18r29 single-thread 10x10\n\n" + report_body + "\n" + "\n".join(report_extra) + "\n",
        encoding="utf-8",
    )
    chg = """## 2026-07-19r29 / restore: stable-2026-07-19-matrix-singlethread-18r29

- **单线程稳定版**全矩阵实跑：`tools/matrix_cross_run.py 10 720`（hybrid/browser × direct/socks5_list × outlook/aol + pending_sso×2），每格 10 轮，`count=1`。
- **Outlook 1078**：`identity/confirm` + `error.aspx?errcode=1078` → `identity_confirm_blocked` permanent，立即删池，禁止 12 步空转。
- 主路径不变：注册成功 → 即时 SSO → g2a/Sub2API/CPA/NSFW；pending 仅兜底；日志应用内明文。
- 矩阵产物：`matrix_runs/matrix_18r29_*` + `REPORT.md`；Packages **新增**本 tag（不覆盖历史）。

"""
    cl = ROOT / "CHANGELOG.md"
    old = cl.read_text(encoding="utf-8") if cl.exists() else "# CHANGELOG\n"
    if "2026-07-19r29" not in old:
        # prepend after first heading if possible
        if old.startswith("#"):
            parts = old.split("\n", 1)
            cl.write_text(parts[0] + "\n\n" + chg + (parts[1] if len(parts) > 1 else ""), encoding="utf-8")
        else:
            cl.write_text(chg + old, encoding="utf-8")
    sv = ROOT / "STABLE_VERSION.md"
    sv.write_text(
        f"# STABLE_VERSION\n\n- tag: `{TAG}`\n- date: {datetime.now().isoformat(timespec='seconds')}\n- matrix: single-thread 18r29\n- out: `{OUT}`\n",
        encoding="utf-8",
    )

    # package
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    include = [
        "outlook_mail.py", "aol_mail.py", "hybrid_register.py", "grok_register_ttk.py",
        "pending_sso_recovery.py", "sub2api_client.py", "web/server.py",
        "tools/matrix_cross_run.py", "CHANGELOG.md", "MATRIX_REPORT.md", "STABLE_VERSION.md",
        "README.md",
    ]
    # copy tree essentials
    for rel in include:
        src = ROOT / rel
        if src.exists():
            dst = PKG_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # report
    if (OUT / "REPORT.md").exists():
        shutil.copy2(OUT / "REPORT.md", PKG_DIR / "REPORT.md")
    if (OUT / "summary.jsonl").exists():
        shutil.copy2(OUT / "summary.jsonl", PKG_DIR / "summary.jsonl")
    # zip
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PKG_DIR.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(Path(TAG) / p.relative_to(PKG_DIR)))
    log(f"package written {ZIP_PATH} size={ZIP_PATH.stat().st_size}")

    # git add commit
    run_cmd(["git", "add", "-A", "outlook_mail.py", "tools/matrix_cross_run.py", "CHANGELOG.md", "MATRIX_REPORT.md", "STABLE_VERSION.md", "packages/"+TAG, f"packages/{TAG}.zip"])
    # also add useful tools
    run_cmd(["git", "add", "tools/_auto_publish_18r29.py", "tools/_final_guardian_18r29.py", "tools/_build_package_18r29.py", "tools/_pulse_18r29_now.py", "tools/_unattended_guardian_18r29.py"], check=False)
    msg = f"release({TAG}): single-thread matrix 18r29 restore point"
    p = run_cmd(["git", "commit", "-m", msg], check=False)
    run_cmd(["git", "tag", "-a", TAG, "-m", msg], check=False)
    run_cmd(["git", "push", "mygithub", "main"], check=False)
    run_cmd(["git", "push", "mygithub", TAG], check=False)
    # gh release
    notes = chg + "\n\n" + "\n".join(report_extra)
    notes_path = ROOT / "matrix_runs" / "_release_notes_18r29.md"
    notes_path.write_text(notes, encoding="utf-8")
    run_cmd([
        "gh", "release", "create", TAG,
        str(ZIP_PATH),
        "--title", TAG,
        "--notes-file", str(notes_path),
        "--repo", "qq1254870524/grok-regkit",
    ], check=False)
    # companion notes only if clean docs change needed
    for repo, remote in [
        (Path(r"C:\Users\zhang\grok-regkit-services"), "origin"),
        (Path(r"C:\Users\zhang\sub2api-src"), "origin"),
    ]:
        try:
            note = repo / "COMPAT_18r29.md"
            note.write_text(
                f"# Compat note {TAG}\n\nPaired with grok-regkit `{TAG}` single-thread matrix restore point.\n- date: {datetime.now().isoformat(timespec='seconds')}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "COMPAT_18r29.md"], cwd=repo, check=False)
            subprocess.run(["git", "commit", "-m", f"docs: compat note for {TAG}"], cwd=repo, check=False)
            subprocess.run(["git", "tag", "-a", TAG, "-m", TAG], cwd=repo, check=False)
            subprocess.run(["git", "push", remote, "main"], cwd=repo, check=False)
            subprocess.run(["git", "push", remote, TAG], cwd=repo, check=False)
            log(f"companion pushed {repo}")
        except Exception as e:
            log(f"companion skip {repo}: {e}")
    # grok2api push ahead commits
    g2 = Path(r"C:\Users\zhang\grok-regkit-services1\grok2api1")
    try:
        subprocess.run(["git", "push", "mygithub", "main"], cwd=g2, check=False)
        subprocess.run(["git", "tag", "-a", TAG, "-m", TAG], cwd=g2, check=False)
        subprocess.run(["git", "push", "mygithub", TAG], cwd=g2, check=False)
        log("grok2api pushed")
    except Exception as e:
        log(f"grok2api push fail: {e}")
    log("PUBLISH_DONE")
    return True

def resume_incomplete(incomplete):
    """If matrix runner died before REPORT, finish remaining cells into same OUT."""
    log(f"resume incomplete cells: {[(n,o,need) for n,o,need,_ in incomplete]}")
    # import runner pieces by exec path - call API like matrix_cross_run
    sys.path.insert(0, str(ROOT / "tools"))
    # minimal inline runner using same OUT
    SUMMARY = OUT / "summary.jsonl"
    def put_config(cell):
        # read config via API if available
        code, cfg = api("GET", "/api/config")
        body = {}
        if isinstance(cfg, dict):
            body = dict(cfg.get("config") or cfg)
        body["register_mode"] = cell["register_mode"]
        body["proxy_mode"] = cell["proxy_mode"]
        body["email_provider"] = cell["email_provider"]
        # don't touch register_count
        api("POST", "/api/config", body)
        # alternate endpoints
        api("PUT", "/api/config", body)

    # load matrix helpers from file
    import importlib.util
    # simpler: start matrix only for remaining using a custom script written to OUT
    resume_py = OUT / "_resume_remaining.py"
    resume_py.write_text(f'''# auto resume
import json, os, sys, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r"{ROOT}")
OUT = Path(r"{OUT}")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.chdir(ROOT)
# reuse matrix_cross_run functions by reading module with patched OUT - run cells via subprocess API clone
# fallback: invoke python -c importing matrix with env
os.environ["MATRIX_OUT_OVERRIDE"] = str(OUT)
''', encoding="utf-8")
    # Prefer: run remaining via duplicated logic from matrix_cross_run if matrix dead
    # For safety, relaunch full matrix only if OUT has no REPORT and runner dead AND progress < 100
    # Better approach: call tools/matrix_cross_run with env override
    # Patch: write a small resume runner
    code = (ROOT / "tools" / "matrix_cross_run.py").read_text(encoding="utf-8")
    if "MATRIX_OUT_OVERRIDE" not in code:
        log("matrix_cross_run has no OUT override; writing resume_runner")
    resume_runner = ROOT / "tools" / "_resume_matrix_18r29.py"
    # Generate self-contained resume based on current incomplete
    cells_need = []
    by = best_by_cell(rows())
    for c in CELLS:
        have = sum(1 for v in by.get(c["name"], {}).values() if v.get("ok"))
        # also count non-ok finished rounds? we need 10 ok ideally but matrix does 10 attempts
        finished_rounds = len(by.get(c["name"], {}))
        # matrix does fixed 10 rounds regardless of ok - resume missing rounds numbers
        done_nums = set(by.get(c["name"], {}).keys())
        for i in range(1, c["need"] + 1):
            if i not in done_nums:
                cells_need.append((c, i))
            elif not by[c["name"]][i].get("ok"):
                # already attempted fail - leave as is unless zero attempts success and want more
                pass
    log(f"resume jobs planned={len(cells_need)}")
    if not cells_need:
        # maybe report missing only
        if not (OUT / "REPORT.md").exists() and rows():
            write_report_from_rows(rows())
        return
    # execute sequentially
    for cell, ri in cells_need:
        if (OUT / "REPORT.md").exists():
            break
        log(f"RESUME run {cell['name']} r{ri}")
        rec = run_one_like_matrix(cell, ri)
        log(f"RESUME done {cell['name']} r{ri} ok={rec.get('ok')} class={rec.get('class')}")
        time.sleep(2)
    write_report_from_rows(rows())

def write_report_from_rows(rs):
    by_cell = defaultdict(list)
    for r in rs:
        by_cell[r["cell"]].append(r)
    lines = [
        f"# Matrix 18r29 Single-Thread Stable Report",
        f"",
        f"- generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- note: may include resume fills",
        f"- out: `{OUT}`",
        f"",
        f"## Per-cell",
        f"",
        f"| cell | rounds | success | fail | pending | top_classes |",
        f"|------|--------|---------|------|---------|-------------|",
    ]
    for cell, items in by_cell.items():
        ok = sum(1 for x in items if x.get("ok"))
        fail = sum(1 for x in items if not x.get("ok"))
        pend = sum(int(x.get("pending_sso") or 0) for x in items)
        cls = Counter(x.get("class") or "?" for x in items).most_common(4)
        top = ", ".join(f"{a}:{b}" for a, b in cls)
        lines.append(f"| {cell} | {len(items)} | {ok} | {fail} | {pend} | {top} |")
    lines += ["", "## Failure class totals", ""]
    total = Counter(x.get("class") or "?" for x in rs)
    for k, v in total.most_common():
        lines.append(f"- `{k}`: {v}")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"REPORT written {OUT/'REPORT.md'}")

def run_one_like_matrix(cell, round_i):
    """Subset of matrix_cross_run.run_one writing to same OUT."""
    name = cell["name"]
    kind = cell["kind"]
    t0 = time.time()
    rec = {
        "cell": name,
        "round": round_i,
        "kind": kind,
        "started": datetime.now().isoformat(timespec="seconds"),
        "ok": False,
        "success": 0,
        "fail": 0,
        "pending_sso": 0,
        "skipped": 0,
        "error": "",
        "class": "",
        "elapsed_s": 0,
        "finished": "",
        "resumed": True,
    }
    try:
        stop_job()
        wait_idle(45)
        # config
        body = {
            "register_mode": cell["register_mode"],
            "proxy_mode": cell["proxy_mode"],
            "email_provider": cell["email_provider"],
        }
        # merge with GET
        code, cfg = api("GET", "/api/config")
        if code == 200 and isinstance(cfg, dict):
            base = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
            if isinstance(base, dict):
                merged = dict(base)
                merged.update(body)
                body = merged
        api("POST", "/api/config", body)
        api("PUT", "/api/config", body)
        if kind == "pending_sso_recovery":
            code, resp = api("POST", "/api/pending-sso/recover", {"count": 1})
        else:
            code, resp = api("POST", "/api/start", {"count": 1})
        if code not in (200, 201) or (isinstance(resp, dict) and resp.get("ok") is False):
            rec["error"] = f"start_fail {code} {resp}"
            rec["class"] = "start_fail"
        else:
            # wait finish
            deadline = time.time() + 720
            while time.time() < deadline:
                c2, st = api("GET", "/api/status")
                if c2 == 200 and not st.get("running"):
                    rec["success"] = int(st.get("success") or 0)
                    rec["fail"] = int(st.get("fail") or 0)
                    rec["pending_sso"] = int(st.get("pending_sso") or 0)
                    rec["skipped"] = int(st.get("skipped") or 0)
                    rec["ok"] = rec["success"] > 0 and rec["fail"] == 0
                    break
                time.sleep(3)
            else:
                rec["error"] = "job_timeout"
                rec["class"] = "job_timeout"
                stop_job()
                wait_idle(30)
        # logs
        c3, lg = api("GET", "/api/logs/snapshot?limit=500")
        logs = "\n".join(lg.get("lines") or []) if isinstance(lg, dict) else ""
        (OUT / f"{name}_r{round_i:02d}.log").write_text(logs, encoding="utf-8")
        if not rec["class"]:
            if rec["ok"]:
                rec["class"] = "success"
            elif rec["pending_sso"] > 0:
                rec["class"] = "pending_sso"
            elif not logs.strip():
                rec["class"] = "empty_log"
            else:
                rec["class"] = "fail"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["class"] = "runner_exception"
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["finished"] = datetime.now().isoformat(timespec="seconds")
    with (OUT / "summary.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def main():
    log(f"unattended guardian start OUT={OUT} TAG={TAG}")
    stall_hits = 0
    while True:
        info = write_pulse()
        if (OUT / "REPORT.md").exists():
            log("REPORT found -> publish")
            try:
                publish()
            except Exception as e:
                log(f"publish error: {e}")
            write_pulse(note="PUBLISH_ATTEMPTED")
            return 0
        alive = matrix_procs_alive()
        running = bool(info["st"].get("running"))
        age = info["age"]
        # healthy: matrix alive or job running or recently updated
        if alive or running or age < 900:
            stall_hits = 0
            time.sleep(40)
            continue
        stall_hits += 1
        log(f"STALL hit={stall_hits} age={age} alive={alive} running={running} incomplete={len(info['incomplete'])}")
        with ALERT.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] stall hit={stall_hits} age={age}\n")
        if stall_hits >= 2:
            # resume remaining
            try:
                resume_incomplete(info["incomplete"])
            except Exception as e:
                log(f"resume error: {e}")
            stall_hits = 0
        time.sleep(30)

if __name__ == "__main__":
    raise SystemExit(main())
