#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
18r24: classify fixed (no false email_login_fail on IMAP login OK); profile/sso classes.
Matrix cross-run orchestrator for grok-regkit web API.

Changelog:
- 2026-07-19r22: put_config no longer forces register_count=1 (preserve UI preference); job still /api/start count=1 per cell-round.
- 2026-07-19r21: OUT matrix_18r21_*; auto-retry stop_requested/empty_log once per cell-round;
  pairs with outlook early_no_new_mail 75s + hybrid 180s poll when actual_send>=1; plaintext logs.
- 2026-07-19r19: api()/wait_idle/run_one retry on URLError/10061/Connection refused with backoff;
  empty log class=empty_log; OUT matrix_18r19_*; pairs with hybrid 180s poll when actual_send>=1.
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

OUT = BASE / "matrix_runs" / datetime.now().strftime("matrix_18r21_%Y%m%d_%H%M%S")
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


def _is_conn_refused(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(
        k in msg
        for k in (
            "10061",
            "connection refused",
            "积极拒绝",
            "winerror 10061",
            "urlopen error",
            "remotely closed",
            "connectionreset",
            "timed out",
            "timeout",
        )
    ) and (
        "10061" in msg
        or "connection refused" in msg
        or "积极拒绝" in msg
        or "urlopen error" in msg
        or "connectionreset" in msg
        or "timed out" in msg
        or "timeout" in msg
    )


def api(method: str, path: str, body: dict | None = None, timeout: int = 60, retries: int = 5):
    """Call 8092 API with backoff on transient connection errors (10061 during brief restarts)."""
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_exc: BaseException | None = None
    attempts = max(1, int(retries or 1))
    for attempt in range(1, attempts + 1):
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
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not _is_conn_refused(exc):
                raise
            delay = min(12.0, 1.5 * attempt)
            log(
                f"[api-retry] {method} {path} attempt={attempt}/{attempts} "
                f"err={type(exc).__name__}: {exc} sleep={delay:.1f}s"
            )
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"api failed {method} {path}")


def classify(logs: str) -> str:
    """Failure/success taxonomy for matrix cells. Prefer specific terminal signals.

    IMPORTANT: do NOT match healthy log noise such as "IMAP login OK" or
    successful "confirmation code" fetch lines.
    """
    t = (logs or "")
    tl = t.lower()

    # Terminal counters first
    if re.search(r"任务结束。成功\s*1\s*\|\s*失败\s*0", t) or re.search(
        r"成功\s*1\s*\|\s*失败\s*0\s*\|\s*pending_sso\s*0", t
    ):
        return "success"

    rules = [
        ("stop_requested", ["stop requested", "force_stop", "stop requested from web"]),
        ("empty_log", ["<log fetch fail"]),
        ("early_no_new_mail", ["early_no_new_mail", "seen_new_after_send=0", "graph no post-send"]),
        (
            "rate_limit_mailbox",
            [
                "验证码过多",
                "create_email_rate_limited",
                "发送到此邮箱的验证码过多",
                "too many verification",
            ],
        ),
        (
            "create_email_fail",
            [
                "createemail fail",
                "create email fail",
                "发信失败",
                "switch_mailbox",
                "create_email_rate_limited",
            ],
        ),
        (
            "email_login_fail",
            [
                "邮箱登录失败",
                "获取邮箱失败",
                "imap login fail",
                "imap login failed",
                "login failed",
                "auth fail",
                "invalid credentials",
                "authentication failed",
                "preflight login fail",
                "aol ensure_login fail",
                "outlook login fail",
                "graph login fail",
            ],
        ),
        (
            "profile_fill_fail",
            [
                "最终注册页资料填写失败",
                "资料填写失败",
                "fill-failed",
                "no-submit-button",
                "filled-no-submit",
            ],
        ),
        (
            "sso_timeout",
            [
                "未获取到 sso cookie",
                "您正在登录",
                "signing-in",
                "wait_for_sso",
                "sso nudge",
            ],
        ),
        (
            "pending_sso",
            [
                "burn_mailbox_to_pending",
                "pending_sso saved",
                "-> pending_sso",
                "mailbox burned to pending_sso",
            ],
        ),
        (
            "signup_no_sso",
            [
                "protocol no sso",
                "no sso cookies=",
                "sso_len=0",
                "browser-fetch no sso",
            ],
        ),
        (
            "turnstile_fail",
            [
                "turnstile 获取 token 失败",
                "turnstile 二次复用失败",
                "turnstile token 失败",
            ],
        ),
        ("next_action_404", ["server action not found"]),
        ("consent_404", ["consent http 404", "consent 失败"]),
        (
            "verify_email_fail",
            ["verifyemail fail", "code invalid", "验证码错误", "invalid code"],
        ),
        (
            "proxy_fail",
            [
                "cannot complete socks5",
                "tunnel failed",
                "proxy error",
                "curl: (97)",
                "curl: (28)",
            ],
        ),
        ("cf_block", ["attention required", "just a moment", "cf challenge"]),
        ("ui_desync", ["ui desync", "ui fallback desync"]),
        (
            "browser_disconnect",
            ["page disconnected", "与页面的连接已断开"],
        ),
        (
            "password_error",
            [
                "账号密码错误",
                "incorrect password",
                "wrong password",
                "invalid password",
            ],
        ),
        ("success", ["注册成功", "sso 有效", "immediate sso", "已写入号池"]),
    ]
    for name, kws in rules:
        hit = False
        for k in kws:
            if k.isascii():
                if k.lower() in tl:
                    hit = True
                    break
            elif k in t:
                hit = True
                break
        if not hit:
            continue
        if name == "success" and ("成功 0" in t or "失败 1" in t or "fail=1" in tl):
            continue
        return name
    if "success" in tl and "fail" in tl:
        return "mixed"
    return "unknown"



def wait_idle(timeout: int = 30) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            code, st = api("GET", "/api/status", timeout=15, retries=3)
            if code == 200 and not st.get("running"):
                return True
        except Exception as exc:
            log(f"[wait_idle] status not ready: {type(exc).__name__}: {exc}")
        time.sleep(1)
    return False


def stop_job() -> None:
    try:
        api("POST", "/api/stop", {})
    except Exception:
        pass


def put_config(cell: dict) -> None:
    # Do NOT set register_count here — that is the user's UI preference.
    # Matrix isolation uses POST /api/start {"count": 1} only (see run_one).
    body = {
        "register_mode": cell["register_mode"],
        "proxy_mode": cell["proxy_mode"],
        "email_provider": cell["email_provider"],
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
        # 18r17/r19: NO redaction — full plaintext logs for diagnosis (user request)
        (OUT / f"{name}_r{round_i:02d}.log").write_text(logs, encoding="utf-8")
        if not rec["class"]:
            if rec["ok"]:
                rec["class"] = "success"
            elif rec["pending_sso"] > 0:
                rec["class"] = "pending_sso"
            elif not (logs or "").strip() or logs.startswith("<log fetch fail"):
                rec["class"] = "empty_log"
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
        f"# Matrix 18r21 Report",
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
            rec = run_one(cell, i)
            # 18r21: one automatic retry on infrastructure noise (stop/empty), not business fails
            if rec.get("class") in ("stop_requested", "empty_log", "runner_exception", "start_fail"):
                log(
                    f"[retry] {cell.get('name')} r{i} class={rec.get('class')} "
                    f"-> one more attempt after stop+idle"
                )
                stop_job()
                wait_idle(45)
                time.sleep(3)
                rec2 = run_one(cell, i)
                rec2["retried_from"] = rec.get("class")
                rec = rec2
            rows.append(rec)
            # short cool-down between jobs
            time.sleep(2)
    write_report(rows)
    ok_n = sum(1 for r in rows if r.get("ok"))
    log(f"DONE total={len(rows)} ok={ok_n} fail={len(rows)-ok_n} report={REPORT}")
    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

