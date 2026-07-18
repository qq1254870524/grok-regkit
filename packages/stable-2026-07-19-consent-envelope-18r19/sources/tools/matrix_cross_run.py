#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Matrix cross-run orchestrator for grok-regkit web API.

Changelog:
- 2026-07-19r18: CreateEmail dual-send lock via token_harvester; matrix OUT matrix_18r18_*
- 2026-07-19r17: matrix logs FULL plaintext (no SSO/password redaction);
  OUT dir matrix_18r18_*; classify 验证码过多 as rate_limit/create_email_fail;
  keep 10x10 cells + pending recovery.
- 2026-07-18r14: full matrix hybrid/browser x direct/socks5 x outlook/aol
  x 10 rounds + pending_sso recovery; classify failures.
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).name == "matrix_cross_run.py") else Path.cwd()
if (ROOT / "web" / "server.py").is_file():
    BASE = ROOT
else:
    BASE = Path(r"C:\Users\zhang\grok-regkit")

API = "http://127.0.0.1:8092"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
JOB_TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 720  # seconds per job
PENDING_ROUNDS = max(2, min(ROUNDS, 10))

OUT = BASE / "matrix_runs" / datetime.now().strftime("matrix_18r18_%Y%m%d_%H%M%S")
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = OUT / "summary.jsonl"
REPORT = OUT / "REPORT.md"

CELLS = []
for mode in ("hybrid", "browser"):
    for proxy in ("direct", "socks5_list"):
        for mail in ("outlook", "aol"):
            CELLS.append(
                {
                    "name": f"{mode}__{proxy}__{mail}",
                    "register_mode": mode,
                    "proxy_mode": proxy,
                    "email_provider": mail,
                    "kind": "register",
                }
            )
CELLS.append(
    {
        "name": "pending_sso_recovery__socks5_list",
        "register_mode": "hybrid",
        "proxy_mode": "socks5_list",
        "email_provider": "aol",
        "kind": "pending_sso_recovery",
    }
)
CELLS.append(
    {
        "name": "pending_sso_recovery__direct",
        "register_mode": "hybrid",
        "proxy_mode": "direct",
        "email_provider": "aol",
        "kind": "pending_sso_recovery",
    }
)


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with (OUT / "runner.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, body: dict | None = None, timeout: int = 60):
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"detail": str(e)}
        except Exception:
            payload = {"detail": raw[:500] or str(e)}
        return e.code, payload


def classify(logs: str) -> str:
    t = logs.lower()
    rules = [
        ("stop_requested", ["stop requested", "force_stop", "stop requested from web"]),
        ("email_login_fail", ["邮箱登录失败", "imap login", "login failed", "auth fail", "invalid credentials", "获取邮箱失败"]),
        ("create_email_fail", ["createemail", "create email", "发信失败", "发送到此邮箱的验证码过多", "too many", "rate_limited", "switch_mailbox"]),
        ("rate_limit_mailbox", ["验证码过多", "create_email_rate_limited", "retry in", "minutes}} 后重试"]),
        ("verify_email_fail", ["verifyemail", "验证码", "code invalid", "spo-", "confirmation code"]),
        ("turnstile_fail", ["turnstile", "cf_clearance", "人机"]),
        ("next_action_404", ["server action not found", "next-action", "next action"]),
        ("signup_no_sso", ["no sso", "sso_len=0", "protocol no sso", "pending_sso", "无 sso"]),
        ("consent_404", ["consent http 404", "consent 失败"]),
        ("proxy_fail", ["proxy", "socks", "tunnel", "connection refused", "curl: (28)", "timed out", "ippure", "非住宅"]),
        ("cf_block", ["cf_clearance", "cloudflare", "attention required", "just a moment"]),
        ("ui_desync", ["ui fallback", "desync", "email-page", "hasprofile"]),
        ("browser_disconnect", ["page disconnected", "与页面的连接已断开", "new_tab", "nonetype"]),
        ("rate_limit", ["rate limit", "too many requests", "429", "重试"]),
        ("password_error", ["账号密码错误", "incorrect password", "wrong password", "invalid password"]),
        ("success", ["success=1", "注册成功", "sso 有效", "immediate sso", "sso_len="]),
    ]
    for name, kws in rules:
        if any(k in t for k in kws):
            # success only if also not no-sso heavy fail
            if name == "success" and ("success 0" in t or "失败 1" in t or "fail=1" in t):
                continue
            return name
    if "success" in t and "fail" in t:
        return "mixed"
    return "unknown"


def wait_idle(timeout: int = 30) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, st = api("GET", "/api/status")
        if code == 200 and not st.get("running"):
            return True
        time.sleep(1)
    return False


def stop_job() -> None:
    try:
        api("POST", "/api/stop", {})
    except Exception:
        pass


def put_config(cell: dict) -> None:
    body = {
        "register_mode": cell["register_mode"],
        "proxy_mode": cell["proxy_mode"],
        "email_provider": cell["email_provider"],
        "register_count": 1,
        # keep post-process on for realism; quality stays server-forced
        "proxy_no_direct_fallback": True if cell["proxy_mode"] != "direct" else False,
        "enable_nsfw": True,
        "cpa_export_enabled": True,
        "sub2api_auto_add": True,
        "grok2api_auto_add_remote": True,
    }
    code, resp = api("PUT", "/api/config", body)
    if code not in (200, 201):
        raise RuntimeError(f"put config failed {code} {resp}")


def snapshot_logs(limit: int = 400) -> str:
    code, data = api("GET", f"/api/logs/snapshot?limit={limit}")
    if code != 200:
        return f"<log fetch fail {code}>"
    if isinstance(data, dict):
        lines = data.get("lines") or data.get("logs") or data.get("items") or []
        if isinstance(lines, list):
            return "\n".join(str(x) for x in lines)
        if isinstance(data.get("text"), str):
            return data["text"]
    return str(data)[:50000]


def run_one(cell: dict, round_i: int) -> dict:
    name = cell["name"]
    kind = cell["kind"]
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
    }
    t0 = time.time()
    try:
        if not wait_idle(60):
            stop_job()
            wait_idle(30)
        put_config(cell)
        api("POST", "/api/logs/clear", {})
        if kind == "pending_sso_recovery":
            code, resp = api("POST", "/api/pending-sso/recover", {"count": 1})
        else:
            code, resp = api("POST", "/api/start", {"count": 1})
        if code not in (200, 201):
            rec["error"] = f"start failed {code} {resp}"
            rec["class"] = "start_fail"
            return rec
        # poll
        while True:
            elapsed = time.time() - t0
            if elapsed > JOB_TIMEOUT:
                log(f"[timeout] {name} r{round_i} >{JOB_TIMEOUT}s -> stop")
                stop_job()
                time.sleep(3)
                rec["error"] = "job_timeout"
                rec["class"] = "timeout"
                break
            code, st = api("GET", "/api/status")
            if code == 200 and not st.get("running"):
                rec["success"] = int(st.get("success") or 0)
                rec["fail"] = int(st.get("fail") or 0)
                rec["pending_sso"] = int(st.get("pending_sso") or 0)
                rec["skipped"] = int(st.get("skipped") or 0)
                rec["error"] = str(st.get("error") or "")
                rec["ok"] = rec["success"] > 0 and rec["fail"] == 0
                break
            time.sleep(4)
        logs = snapshot_logs(500)
        # 18r17: NO redaction — full plaintext logs for diagnosis (user request)
        (OUT / f"{name}_r{round_i:02d}.log").write_text(logs, encoding="utf-8")
        if not rec["class"]:
            if rec["ok"]:
                rec["class"] = "success"
            elif rec["pending_sso"] > 0:
                rec["class"] = "pending_sso"
            else:
                rec["class"] = classify(logs)
        # if success counter 0 but log shows sso acquired
        if not rec["ok"] and re.search(r"sso_len=(1[5-9]|\d{3,})", logs):
            rec["class"] = rec["class"] or "possible_sso_log_only"
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["class"] = "runner_exception"
        (OUT / f"{name}_r{round_i:02d}.exc").write_text(traceback.format_exc(), encoding="utf-8")
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["finished"] = datetime.now().isoformat(timespec="seconds")
    with SUMMARY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(
        f"[{name}] r{round_i}/{ROUNDS if kind=='register' else PENDING_ROUNDS} "
        f"ok={rec['ok']} class={rec['class']} s={rec['success']} f={rec['fail']} "
        f"p={rec['pending_sso']} t={rec['elapsed_s']}s err={rec['error'][:80]}"
    )
    return rec


def write_report(rows: list[dict]) -> None:
    from collections import Counter, defaultdict

    by_cell: dict[str, list] = defaultdict(list)
    for r in rows:
        by_cell[r["cell"]].append(r)
    lines = [
        f"# Matrix 18r17 Report",
        f"",
        f"- generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- rounds_per_register_cell: {ROUNDS}",
        f"- pending_rounds: {PENDING_ROUNDS}",
        f"- job_timeout_s: {JOB_TIMEOUT}",
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
    total = Counter(x.get("class") or "?" for x in rows)
    for k, v in total.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Notes", "", "- Logs under this directory are FULL plaintext (no SSO/password redaction) per 18r17.", ""]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    log(f"OUT={OUT}")
    log(f"ROUNDS={ROUNDS} JOB_TIMEOUT={JOB_TIMEOUT} cells={len(CELLS)}")
    # ensure idle
    if not wait_idle(10):
        stop_job()
        wait_idle(30)
    rows: list[dict] = []
    for cell in CELLS:
        n = PENDING_ROUNDS if cell["kind"] != "register" else ROUNDS
        for i in range(1, n + 1):
            rows.append(run_one(cell, i))
            # short cool-down between jobs
            time.sleep(2)
    write_report(rows)
    ok_n = sum(1 for r in rows if r.get("ok"))
    log(f"DONE total={len(rows)} ok={ok_n} fail={len(rows)-ok_n} report={REPORT}")
    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
