#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastAPI control plane for grok-regkit.

2026-07-18e: job metrics add pending_sso/skipped; progress regex parses extended
18r28c: pending job reloads hybrid_register+mail modules
stats; POST /api/pending-sso/recover starts secondary SSO recovery job.
2026-07-18d: Sub2API pool status in /api/integration (healthy/count/open URL),
pending-SSO account files in /api/accounts, dedicated /api/sub2api/status.
2026-07-19-live-metrics2: session stats + mid-job markers + phase + live last_event tick + broader waiting_code patterns;
2026-07-18b: parse hybrid/browser progress logs and update success/fail in
_job_state while a job is running, so Web UI metrics refresh in real time.
2026-07-18c: added CPA OAuth JSON directory import API for Sub2API.
2026-07-18f: UI docs for CPA raw vs sub2api-data; mailbox login failure detail logs in providers.
2026-07-18g: Sub2API probe 401/fingerprint 强制 invalidate + 重登，恢复 account_count 显示。
2026-07-17b: added Sub2API post-import usability verification settings.
2026-07-17: added Sub2API SSO-to-OAuth settings; password is masked and preserved
when the Web UI submits the masked placeholder.
"""

from __future__ import annotations

import asyncio
import re
import collections
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

# Project root = parent of web/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

import grok_register_ttk as engine  # noqa: E402

ACCESS_PASSWORD = (os.getenv("GROK_REGISTER_ACCESS_PASSWORD") or "").strip()
HOST = (os.getenv("GROK_REGISTER_HOST") or "127.0.0.1").strip()
PORT = int(os.getenv("GROK_REGISTER_PORT") or "8092")

# Optional grok2api / token-pool integration (override via env)
G2A_INTERNAL_BASE = (
    os.getenv("GROK2API_INTERNAL_URL") or "http://127.0.0.1:8010"
).strip().rstrip("/")
G2A_PUBLIC_URL = (
    os.getenv("GROK2API_PUBLIC_URL") or "http://127.0.0.1:8010"
).strip().rstrip("/")

WEB_DIR = Path(__file__).resolve().parent
INDEX_HTML = WEB_DIR / "index.html"

SECRET_FIELDS = {
    "duckmail_api_key",
    "cloudflare_api_key",
    "yyds_api_key",
    "yyds_jwt",
    "grok2api_remote_app_key",
    "sub2api_admin_password",
    "proxy",
    "proxy_pass",
}

# In-memory sessions: token -> expiry ts
_sessions: Dict[str, float] = {}
_SESSION_TTL = 86400 * 7

_job_lock = threading.Lock()
_job_thread: Optional[threading.Thread] = None
_controller: Optional[engine.CliStopController] = None
_log_buffer: Deque[str] = collections.deque(maxlen=2000)
_log_seq = 0
_log_cond = threading.Condition()
_job_state: Dict[str, Any] = {
    "running": False,
    "success": 0,
    "fail": 0,
    "pending_sso": 0,
    "skipped": 0,
    "target": 0,
    "job_kind": "",
    "last_accounts_file": "",
    "started_at": None,
    "finished_at": None,
    "error": "",
    # current-job only counters reset each start; session_* survive matrix restarts
    "session_success": 0,
    "session_fail": 0,
    "session_pending_sso": 0,
    "session_skipped": 0,
    "phase": "idle",
    "last_event": "",
    "updated_at": None,
    "jobs_started": 0,
    "jobs_finished": 0,
}
_progress_seen_ok: set = set()
_progress_seen_pending: set = set()
_progress_seen_fail: set = set()
_job_baseline_session: Dict[str, int] = {
    "success": 0,
    "fail": 0,
    "pending_sso": 0,
    "skipped": 0,
}


app = FastAPI(title="Grok Register", version="1.0.0")


def _beijing_hms() -> str:
    try:
        from zoneinfo import ZoneInfo
        import datetime as _dt

        return _dt.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%H:%M:%S")
    except Exception:
        # 无 zoneinfo 时退回 UTC+8
        return time.strftime("%H:%M:%S", time.gmtime(time.time() + 8 * 3600))


def _append_log(message: str) -> None:
    global _log_seq
    ts = _beijing_hms()
    line = f"[{ts}] {message}"
    with _log_cond:
        _log_buffer.append(line)
        _log_seq += 1
        _log_cond.notify_all()


_PROGRESS_RE = re.compile(
    r"(?:当前统计|混合任务结束|任务结束|pending_sso 恢复结束)[^0-9]{0,40}"
    r"成功\s*(\d+)\s*\|\s*失败\s*(\d+)"
    r"(?:\s*\|\s*pending_sso\s*(\d+))?"
    r"(?:\s*\|\s*跳过\(池空\)\s*(\d+))?"
)
_OK_EVENT_RE = re.compile(
    r"(?:\[hybrid\]\[\+\]\s*OK|OK immediate SSO\+pool path|session sso ready).*?(?:email=)?([\w.+-]+@[\w.-]+)?",
    re.I,
)
_PENDING_EVENT_RE = re.compile(
    r"(?:pending_sso saved|mailbox burned to pending_sso).*?(?:email=)?([\w.+-]+@[\w.-]+)?",
    re.I,
)
_FAIL_EVENT_RE = re.compile(
    r"(?:\[hybrid\]\[-\]|注册失败|signup_unconfirmed|job error:).*?(?:email=)?([\w.+-]+@[\w.-]+)?",
    re.I,
)


def _set_phase(phase: str, event: str = "") -> None:
    with _job_lock:
        _job_state["phase"] = phase
        if event:
            _job_state["last_event"] = event[:180]
        _job_state["updated_at"] = time.time()


def _bump_session_from_job_totals() -> None:
    """Map absolute current-job counters onto session totals using job baseline."""
    with _job_lock:
        for key in ("success", "fail", "pending_sso", "skipped"):
            cur = int(_job_state.get(key) or 0)
            base = int(_job_baseline_session.get(key) or 0)
            sess_key = f"session_{key}"
            _job_state[sess_key] = base + cur
        _job_state["updated_at"] = time.time()


def _update_job_progress_from_log(message: str) -> None:
    """Keep Web success/fail/pending/skipped metrics live while a job is running."""
    text = str(message or "")
    low = text.lower()

        # Lightweight phase tracking so UI is not stuck at zeros with no context.
    # Always keep last_event ticking so the browser feels live even when counters stay 0 mid-account.
    with _job_lock:
        if _job_state.get("running"):
            _job_state["last_event"] = text[:180]
            _job_state["updated_at"] = time.time()

    if "starting registration" in low or "混合任务启动" in text or "混合模式启动" in text or "开始第" in text:
        _set_phase("starting", text)
    elif (
        "createemail" in low
        or "使用邮箱注册" in text
        or "open signup" in low
        or "next-action ready" in low
        or "scrape next-action" in low
    ):
        _set_phase("create_email", text)
    elif (
        "poll code" in low
        or "开始查邮件" in text
        or "outlook poll" in low
        or "aol poll" in low
        or "outlook graph" in low
        or "post-send new-mail" in low
        or "early_no_new_mail" in low
        or "waiting for code" in low
        or "mail poll" in low
        or "imap" in low
        or "aol preflight" in low
        or "aol imap" in low
        or "list folders" in low
        or "graph via" in low
        or "mail_token" in low
    ):
        _set_phase("waiting_code", text)
    elif "verifyemail" in low or ("code=" in low and ("outlook code" in low or "clean" in low or "[hybrid] code=" in low)):
        _set_phase("verify_code", text)
    elif "sign-up try" in low or "sign-up final" in low or "signup" in low and "sso_len" in low:
        _set_phase("signup", text)
    elif "sso materialize" in low or "session sso" in low or "authcode_pkce" in low:
        _set_phase("sso", text)
    elif "consent" in low or "mint_method" in low or "[cpa]" in low or "sub2api" in low:
        _set_phase("post_process", text)
    elif "混合任务结束" in text or "web job thread finished" in low or "当前统计" in text:
        _set_phase("finished", text)

    match = _PROGRESS_RE.search(text)
    if match:
        success = int(match.group(1))
        fail = int(match.group(2))
        pending = match.group(3)
        skipped = match.group(4)
        with _job_lock:
            _job_state["success"] = success
            _job_state["fail"] = fail
            if pending is not None:
                _job_state["pending_sso"] = int(pending)
            if skipped is not None:
                _job_state["skipped"] = int(skipped)
            _job_state["updated_at"] = time.time()
            _job_state["last_event"] = text[:180]
        _bump_session_from_job_totals()
        return

    # Mid-job markers (matrix count=1 stays at 0 until final 当前统计 otherwise).
    # Deduplicate: hybrid logs both short "[hybrid][+] OK email" and
    # "OK immediate SSO+pool path ... email=" for the same account.
    if (
        "OK immediate SSO+pool path" in text
        or re.search(r"\[hybrid\]\[\+\]\s*OK\s+[\w.+-]+@[\w.-]+", text)
        or ("session sso ready" in low and "email=" in low)
    ):
        em = re.search(r"[\w.+-]+@[\w.-]+", text)
        key = (em.group(0).lower() if em else text)[:120]
        with _job_lock:
            if key not in _progress_seen_ok:
                _progress_seen_ok.add(key)
                _job_state["success"] = int(_job_state.get("success") or 0) + 1
                _job_state["phase"] = "success"
                _job_state["last_event"] = text[:180]
                _job_state["updated_at"] = time.time()
        _bump_session_from_job_totals()
        return

    mpend = _PENDING_EVENT_RE.search(text)
    if mpend and ("pending_sso saved" in text or "mailbox burned to pending_sso" in text):
        key = (mpend.group(1) or text)[:120]
        with _job_lock:
            if key not in _progress_seen_pending:
                _progress_seen_pending.add(key)
                _job_state["pending_sso"] = max(
                    int(_job_state.get("pending_sso") or 0), len(_progress_seen_pending)
                )
                _job_state["phase"] = "pending_sso"
                _job_state["last_event"] = text[:180]
                _job_state["updated_at"] = time.time()
        _bump_session_from_job_totals()
        return

    mfail = _FAIL_EVENT_RE.search(text)
    if mfail and ("注册失败" in text or "signup_unconfirmed" in text or "job error:" in text or "[hybrid][-]" in text):
        key = (mfail.group(1) or text)[:120]
        with _job_lock:
            if key not in _progress_seen_fail:
                _progress_seen_fail.add(key)
                _job_state["fail"] = max(int(_job_state.get("fail") or 0), len(_progress_seen_fail))
                _job_state["phase"] = "fail"
                _job_state["last_event"] = text[:180]
                _job_state["updated_at"] = time.time()
        _bump_session_from_job_totals()


def _mask_value(key: str, value: Any) -> Any:
    if key not in SECRET_FIELDS:
        return value
    s = "" if value is None else str(value)
    if not s:
        return ""
    if len(s) <= 6:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def _proxy_list_raw_text(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Return editable multi-line proxy pool text for the web UI."""
    c = cfg if isinstance(cfg, dict) else dict(engine.config)
    inline = str(c.get("proxy_list") or "").strip()
    if inline:
        return inline.replace("\r\n", "\n").strip() + "\n"
    name = str(c.get("proxy_list_file") or "socks5_proxies.txt").strip() or "socks5_proxies.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return text.replace("\r\n", "\n").strip() + ("\n" if text.strip() else "")
    except Exception:
        pass
    return ""


def _sync_proxy_list_file(text: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    """Write proxy pool text to list file and keep config.proxy_list in sync."""
    c = cfg if isinstance(cfg, dict) else engine.config
    cleaned_lines = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        cleaned_lines.append(s)
    body = ("\n".join(cleaned_lines) + "\n") if cleaned_lines else ""
    name = str(c.get("proxy_list_file") or "socks5_proxies.txt").strip() or "socks5_proxies.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except Exception as exc:
        _append_log(f"[!] 写入代理池文件失败: {exc}")
    c["proxy_list"] = body.rstrip("\n")
    if not os.path.isabs(name):
        c["proxy_list_file"] = name
    try:
        if hasattr(engine, "_PROXY_POOL_CACHE"):
            engine._PROXY_POOL_CACHE = {"mtime": None, "path": None, "items": []}
        if hasattr(engine, "load_proxy_list"):
            engine.load_proxy_list(c, force_reload=True)
    except Exception:
        pass
    return body


def _outlook_accounts_raw_text(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Return editable multi-line Outlook account pool text for the web UI.

    File is the live source of truth after runtime login-fail/register deletes.
    """
    c = cfg if isinstance(cfg, dict) else dict(engine.config)
    name = str(c.get("outlook_accounts_file") or "outlook_accounts.txt").strip() or "outlook_accounts.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return text.replace('\r\n', '\n').strip() + ('\n' if text.strip() else "")
    except Exception:
        pass
    inline = str(c.get("outlook_accounts") or "").strip()
    if inline:
        return inline.replace('\r\n', '\n').strip() + '\n'
    return ""



def _aol_accounts_raw_text(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Return editable multi-line AOL account pool text for the web UI.

    File is the live source of truth after runtime login-fail/register deletes.
    """
    c = cfg if cfg is not None else engine.config
    name = str(c.get("aol_accounts_file") or "aol_accounts.txt").strip() or "aol_accounts.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8", errors="ignore").replace('\r\n', '\n').rstrip("\n")
        except Exception:
            pass
    inline = str(c.get("aol_accounts") or "").strip()
    return inline.replace('\r\n', '\n').rstrip('\n') if inline else ""


def _public_config() -> Dict[str, Any]:
    engine.load_config()
    cfg = dict(engine.config)
    if cfg.get("cpa_management_key"):
        cfg["cpa_management_key"] = "***"
    # Always expose full editable proxy pool text in the web panel
    cfg["proxy_list"] = _proxy_list_raw_text(cfg).rstrip("\n")
    cfg["outlook_accounts"] = _outlook_accounts_raw_text(cfg).rstrip('\n')
    cfg["aol_accounts"] = _aol_accounts_raw_text(cfg).rstrip('\n')
    masked = {k: _mask_value(k, v) for k, v in cfg.items()}
    for key in SECRET_FIELDS:
        raw = cfg.get(key, "")
        masked[f"has_{key}"] = bool(str(raw or "").strip())
    # proxy_list must remain fully editable (contains passwords); never mask it
    masked["proxy_list"] = cfg.get("proxy_list") or ""
    masked["proxy_list_count"] = len(
        [
            ln
            for ln in str(masked["proxy_list"]).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    )
    # outlook_accounts fully editable in web (email----password----totp)
    masked["outlook_accounts"] = cfg.get("outlook_accounts") or ""
    masked["outlook_accounts_count"] = len(
        [
            ln
            for ln in str(masked["outlook_accounts"]).splitlines()
            if ln.strip() and not ln.strip().startswith("#") and "@" in ln
        ]
    )
    # AOL accounts fully editable in web (email----password/app-password)
    masked["aol_accounts"] = cfg.get("aol_accounts") or ""
    masked["aol_accounts_count"] = len(
        [
            ln
            for ln in str(masked.get("aol_accounts") or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#") and "@" in ln
        ]
    )
    return masked


def _require_auth(x_access_key: Optional[str]) -> None:
    if not ACCESS_PASSWORD:
        return
    key = (x_access_key or "").strip()
    if not key:
        raise HTTPException(status_code=401, detail="access key required")
    # Accept raw password or issued session token
    if key == ACCESS_PASSWORD:
        return
    exp = _sessions.get(key)
    if exp and exp > time.time():
        return
    if exp:
        _sessions.pop(key, None)
    raise HTTPException(status_code=403, detail="invalid access key")


def _issue_token(password: str) -> str:
    raw = f"{password}:{secrets.token_hex(16)}:{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()
    _sessions[token] = time.time() + _SESSION_TTL
    return token


class AuthBody(BaseModel):
    password: str = ""


class StartBody(BaseModel):
    # 单次任务上限（2G 机器仍建议分批；允许 1000 方便面板一次提交）
    count: int = Field(default=1, ge=1, le=1000)


class ConfigBody(BaseModel):
    duckmail_api_key: Optional[str] = None
    cloudflare_api_base: Optional[str] = None
    cloudflare_api_key: Optional[str] = None
    cloudflare_auth_mode: Optional[str] = None
    cloudflare_path_domains: Optional[str] = None
    cloudflare_path_accounts: Optional[str] = None
    cloudflare_path_token: Optional[str] = None
    cloudflare_path_messages: Optional[str] = None
    proxy: Optional[str] = None
    proxy_mode: Optional[str] = None
    proxy_airport_url: Optional[str] = None
    proxy_api_url: Optional[str] = None
    proxy_api_num: Optional[int] = None
    proxy_api_format: Optional[str] = None
    proxy_api_type: Optional[str] = None
    proxy_quality_api: Optional[str] = None
    proxy_host_lookup_api: Optional[str] = None
    proxy_quality_check: Optional[bool] = None
    proxy_check_entry_host: Optional[bool] = None
    proxy_check_exit_ippure: Optional[bool] = None
    proxy_max_fraud_score: Optional[int] = None
    proxy_require_residential: Optional[bool] = None
    proxy_require_country_match: Optional[bool] = None
    proxy_reject_datacenter_org: Optional[bool] = None
    proxy_reject_hosting_flag: Optional[bool] = None
    proxy_quality_max_tries: Optional[int] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[str] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None
    proxy_country: Optional[str] = None
    proxy_delimiter: Optional[str] = None
    proxy_duration: Optional[str] = None
    proxy_user_template: Optional[str] = None
    proxy_session: Optional[str] = None
    enable_nsfw: Optional[bool] = None
    nsfw_async: Optional[bool] = None
    post_success_async: Optional[bool] = None
    cpa_export_enabled: Optional[bool] = None
    cpa_auto_add: Optional[bool] = None
    cpa_auth_dir: Optional[str] = None
    cpa_remote_url: Optional[str] = None
    cpa_management_key: Optional[str] = None
    cpa_remote_upload: Optional[bool] = None
    cpa_prefer_authcode: Optional[bool] = None

    register_count: Optional[int] = None
    register_mode: Optional[str] = None
    user_agent: Optional[str] = None
    grok2api_auto_add_local: Optional[bool] = None
    grok2api_local_token_file: Optional[str] = None
    grok2api_pool_name: Optional[str] = None
    grok2api_auto_add_remote: Optional[bool] = None
    grok2api_remote_base: Optional[str] = None
    grok2api_remote_app_key: Optional[str] = None
    sub2api_auto_add: Optional[bool] = None
    sub2api_base_url: Optional[str] = None
    sub2api_admin_email: Optional[str] = None
    sub2api_admin_password: Optional[str] = None
    sub2api_group_ids: Optional[List[int]] = None
    sub2api_concurrency: Optional[int] = None
    sub2api_priority: Optional[int] = None
    sub2api_timeout_sec: Optional[int] = None
    sub2api_verify_after_add: Optional[bool] = None
    sub2api_require_verify_success: Optional[bool] = None
    sub2api_verify_attempts: Optional[int] = None
    sub2api_verify_timeout_sec: Optional[int] = None
    sub2api_verify_retry_delay_sec: Optional[int] = None
    sub2api_cpa_import_dir: Optional[str] = None
    sub2api_cpa_update_existing: Optional[bool] = None
    defaultDomains: Optional[str] = None
    email_provider: Optional[str] = None
    proxy_list_file: Optional[str] = None
    proxy_list: Optional[str] = None
    proxy_scheme: Optional[str] = None
    proxy_rotate: Optional[bool] = None
    proxy_no_direct_fallback: Optional[bool] = None
    yyds_api_key: Optional[str] = None
    yyds_jwt: Optional[str] = None
    outlook_accounts: Optional[str] = None
    outlook_accounts_file: Optional[str] = None
    outlook_client_id: Optional[str] = None
    outlook_token_cache: Optional[str] = None
    aol_accounts: Optional[str] = None
    aol_accounts_file: Optional[str] = None


def _run_job(count: int, job_kind: str = "register") -> None:
    global _controller
    def log_cb_early(msg: str) -> None:
        _append_log(str(msg))

    controller = engine.CliStopController(log_callback=log_cb_early)
    global _progress_seen_ok, _progress_seen_pending, _progress_seen_fail
    with _job_lock:
        _controller = controller
        _job_state["running"] = True
        _job_state["success"] = 0
        _job_state["fail"] = 0
        _job_state["pending_sso"] = 0
        _job_state["skipped"] = 0
        _job_state["target"] = count
        _job_state["job_kind"] = job_kind
        _job_state["error"] = ""
        _job_state["started_at"] = time.time()
        _job_state["finished_at"] = None
        _job_state["phase"] = "starting"
        _job_state["last_event"] = f"job start kind={job_kind} count={count}"
        _job_state["updated_at"] = time.time()
        _job_state["jobs_started"] = int(_job_state.get("jobs_started") or 0) + 1
        # session counters keep accumulating across matrix rounds
        _job_baseline_session["success"] = int(_job_state.get("session_success") or 0)
        _job_baseline_session["fail"] = int(_job_state.get("session_fail") or 0)
        _job_baseline_session["pending_sso"] = int(_job_state.get("session_pending_sso") or 0)
        _job_baseline_session["skipped"] = int(_job_state.get("session_skipped") or 0)
        _progress_seen_ok = set()
        _progress_seen_pending = set()
        _progress_seen_fail = set()

    def log_cb(msg: str) -> None:
        text = str(msg)
        _append_log(text)
        _update_job_progress_from_log(text)

    try:
        engine.load_config()
        if job_kind == "pending_sso_recovery":
            import importlib
            import sys as _sys
            # 18r28c: always reload hybrid + pending so mail_token lookup / Turnstile fixes apply without full process restart.
            for _mod_name in (
                "aol_mail",
                "outlook_mail",
                "browser.token_harvester",
                "hybrid_register",
                "pending_sso_recovery",
            ):
                try:
                    if _mod_name in _sys.modules:
                        importlib.reload(_sys.modules[_mod_name])
                    else:
                        importlib.import_module(_mod_name)
                        importlib.reload(_sys.modules[_mod_name])
                except Exception as _rel_exc:
                    _append_log(f"[!] reload {_mod_name} fail: {_rel_exc}")
            import pending_sso_recovery as _pending_mod
            importlib.reload(_pending_mod)
            result = _pending_mod.run_pending_sso_recovery_job(
                count, log_callback=log_cb, controller=controller
            )
        else:
            # Prefer freshly loaded path helpers when modules were patched mid-process.
            try:
                import importlib
                for _mod_name in (
                    "outlook_mail",
                    "aol_mail",
                    "sub2api_client",
                    "grok_register_ttk",
                    "hybrid_register",
                ):
                    try:
                        _m = importlib.import_module(_mod_name)
                        importlib.reload(_m)
                    except Exception:
                        pass
            except Exception:
                pass
            result = engine.run_registration_job(
                count, log_callback=log_cb, controller=controller
            )
        with _job_lock:
            _job_state["success"] = int(result.get("success") or 0)
            _job_state["fail"] = int(result.get("fail") or 0)
            _job_state["pending_sso"] = int(result.get("pending_sso") or 0)
            _job_state["skipped"] = int(result.get("skipped") or 0)
            _job_state["last_accounts_file"] = str(result.get("accounts_file") or "")
            _job_state["updated_at"] = time.time()
            _job_state["phase"] = "finished"
        _bump_session_from_job_totals()
    except Exception as exc:
        _append_log(f"[!] job error: {exc}")
        with _job_lock:
            _job_state["error"] = str(exc)
            _job_state["phase"] = "error"
            _job_state["updated_at"] = time.time()
    finally:
        with _job_lock:
            _job_state["running"] = False
            _job_state["finished_at"] = time.time()
            _job_state["jobs_finished"] = int(_job_state.get("jobs_finished") or 0) + 1
            if not _job_state.get("phase") or _job_state.get("phase") == "starting":
                _job_state["phase"] = "idle"
            _job_state["updated_at"] = time.time()
            _controller = None
        _append_log("[*] web job thread finished")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


@app.head("/", include_in_schema=False)
async def root_head():
    return Response(status_code=200, headers={"Cache-Control": "no-store"})


@app.get("/health")
async def health():
    return {"ok": True, "service": "grok-register"}


@app.get("/monitor/status")
async def monitor_status():
    with _job_lock:
        running = bool(_job_state["running"])
    return {
        "ok": True,
        "service": "grok-register",
        "running_job": running,
    }


def _probe_g2a(app_key: str = "") -> Dict[str, Any]:
    """Check local/public grok2api and optional account count.

    Online = process reachable. Prefer /health (no auth). Do NOT use /v1/models
    alone: it returns 401 without a chat API key and was falsely shown as 离线.
    """
    import urllib.error
    import urllib.request

    result: Dict[str, Any] = {
        "ok": False,
        "internal_base": G2A_INTERNAL_BASE,
        "public_url": G2A_PUBLIC_URL,
        "admin_url": f"{G2A_PUBLIC_URL}/admin/login",
        "account_count": None,
        "error": "",
    }

    def _http_status(url: str, timeout: float = 4.0) -> int:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "grok-register-integration"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return int(resp.status)
        except urllib.error.HTTPError as exc:
            # Any HTTP response means the process is up (401/403 still "online")
            return int(exc.code)
        except Exception:
            raise

    # 1) Liveness — /health is unauthenticated on grok2api
    probe_errors: list[str] = []
    for path in ("/health", "/", "/v1/models"):
        url = f"{G2A_INTERNAL_BASE}{path}"
        try:
            status = _http_status(url, timeout=4.0)
            # reachable if we got any HTTP status (incl. 401/403/404/307)
            if 100 <= status < 600:
                result["ok"] = True
                break
        except Exception as exc:
            probe_errors.append(f"{path}: {exc}")
    if not result["ok"]:
        result["error"] = "; ".join(probe_errors) or "unreachable"
        return result

    # 2) Optional account count via admin API (needs app_key / 管理密码)
    key = (app_key or "").strip()
    if not key:
        engine.load_config()
        key = str(engine.config.get("grok2api_remote_app_key") or "").strip()
    if key and "*" not in key:
        try:
            url = f"{G2A_INTERNAL_BASE}/admin/api/tokens?app_key={urllib.parse.quote(key)}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=6) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                tokens = payload.get("tokens") if isinstance(payload, dict) else None
                if isinstance(tokens, list):
                    result["account_count"] = len(tokens)
                elif isinstance(tokens, dict):
                    # older full-pool shape: { "ssoBasic": [...] }
                    n = 0
                    for v in tokens.values():
                        if isinstance(v, list):
                            n += len(v)
                    result["account_count"] = n
        except Exception as exc:
            result["error"] = f"online; tokens: {exc}"
    return result



def _probe_sub2api(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Probe Sub2API health and grok account pool size. Never returns secrets."""
    cfg = cfg or {}
    base = str(cfg.get("sub2api_base_url") or "http://127.0.0.1:8080").strip().rstrip("/")
    admin_email = str(cfg.get("sub2api_admin_email") or "").strip()
    admin_password = str(cfg.get("sub2api_admin_password") or "").strip()
    auto_add = bool(cfg.get("sub2api_auto_add", True))
    public_url = base or "http://127.0.0.1:8080"
    result: Dict[str, Any] = {
        "ok": False,
        "healthy": False,
        "reachable": False,
        "base_url": public_url,
        "public_url": public_url,
        "admin_url": f"{public_url}/",
        "accounts_url": f"{public_url}/",
        "account_count": None,
        "auto_add": auto_add,
        "has_admin_email": bool(admin_email),
        "has_admin_password": bool(admin_password),
        "error": "",
    }
    if not base:
        result["error"] = "sub2api_base_url empty"
        return result

    import urllib.request

    for path in ("/api/v1/health", "/health", "/"):
        try:
            req = urllib.request.Request(f"{base}{path}", method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:
                code = int(getattr(resp, "status", 200) or 200)
                if 200 <= code < 500:
                    result["reachable"] = True
                    break
        except Exception as exc:
            result["error"] = f"reach: {type(exc).__name__}: {exc}"
    if not result["reachable"]:
        return result

    if not admin_email or not admin_password:
        result["ok"] = True
        result["healthy"] = True
        result["error"] = "online; need admin credentials for account_count"
        return result

    try:
        from sub2api_client import get_client, invalidate_client_cache

        client = get_client(cfg, log_callback=None)
        try:
            listed = client.list_accounts(platform="grok", page=1, page_size=1)
        except Exception as first_exc:
            msg = str(first_exc)
            if (
                "401" in msg
                or "fingerprint" in msg.lower()
                or "please login again" in msg.lower()
                or "unauthorized" in msg.lower()
            ):
                try:
                    invalidate_client_cache(cfg)
                except Exception:
                    pass
                client = get_client(cfg, log_callback=None, force_new=True)
                try:
                    client.invalidate_auth(reset_session=True, reason="probe_retry")
                except Exception:
                    pass
                listed = client.list_accounts(platform="grok", page=1, page_size=1)
            else:
                raise
        raw = listed.get("raw") if isinstance(listed.get("raw"), dict) else {}
        total = raw.get("total")
        if total is None and isinstance(raw.get("pagination"), dict):
            total = raw.get("pagination", {}).get("total")
        if total is None:
            items = listed.get("items") or []
            total = len(items)
        try:
            result["account_count"] = int(total)
        except Exception:
            result["account_count"] = None
        result["ok"] = True
        result["healthy"] = True
        result["error"] = ""
    except Exception as exc:
        result["ok"] = True
        result["healthy"] = result["reachable"]
        result["error"] = f"online; accounts: {type(exc).__name__}: {exc}"
    return result


@app.get("/api/integration")
async def api_integration(x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    engine.load_config()
    cfg = engine.config
    remote_base = str(cfg.get("grok2api_remote_base") or "").strip()
    remote_key = str(cfg.get("grok2api_remote_app_key") or "").strip()
    g2a = _probe_g2a(remote_key)
    sub2 = _probe_sub2api(cfg)
    linked = bool(cfg.get("grok2api_auto_add_remote")) and bool(remote_base) and bool(remote_key)
    return {
        "ok": True,
        "g2a": g2a,
        "sub2api": sub2,
        "linked": linked,
        "config": {
            "auto_add_remote": bool(cfg.get("grok2api_auto_add_remote")),
            "remote_base": remote_base or g2a["internal_base"],
            "pool_name": cfg.get("grok2api_pool_name") or "ssoBasic",
            "has_app_key": bool(remote_key),
            "sub2api_auto_add": bool(cfg.get("sub2api_auto_add", True)),
            "sub2api_base_url": str(cfg.get("sub2api_base_url") or "http://127.0.0.1:8080").strip().rstrip("/"),
            "has_sub2api_admin_email": bool(str(cfg.get("sub2api_admin_email") or "").strip()),
            "has_sub2api_admin_password": bool(str(cfg.get("sub2api_admin_password") or "").strip()),
        },
        "defaults": {
            "remote_base": G2A_INTERNAL_BASE,
            "public_url": G2A_PUBLIC_URL,
            "admin_url": f"{G2A_PUBLIC_URL}/admin/login",
            "pool_name": "ssoBasic",
            "sub2api_base_url": "http://127.0.0.1:8080",
            "sub2api_accounts_url": "http://127.0.0.1:8080/",
        },
    }


class LinkG2ABody(BaseModel):
    app_key: str = ""
    enable: bool = True
    remote_base: str = ""
    pool_name: str = "ssoBasic"


@app.post("/api/integration/link")
async def api_integration_link(body: LinkG2ABody, x_access_key: Optional[str] = Header(None)):
    """One-click wire register → local grok2api token pool."""
    _require_auth(x_access_key)
    engine.load_config()
    base = (body.remote_base or G2A_INTERNAL_BASE).strip().rstrip("/")
    key = (body.app_key or "").strip()
    if not key or "*" in key:
        # keep existing key if masked / empty and already set
        existing = str(engine.config.get("grok2api_remote_app_key") or "").strip()
        if existing:
            key = existing
        else:
            key = "grok2api"  # default admin password of fresh install
    engine.config["grok2api_remote_base"] = base
    engine.config["grok2api_remote_app_key"] = key
    engine.config["grok2api_pool_name"] = (body.pool_name or "ssoBasic").strip() or "ssoBasic"
    engine.config["grok2api_auto_add_remote"] = bool(body.enable)
    engine.config["grok2api_auto_add_local"] = False
    engine.save_config()
    # probe after link
    g2a = _probe_g2a(key)
    return {
        "ok": True,
        "linked": bool(body.enable),
        "g2a": g2a,
        "config": _public_config(),
    }


@app.post("/api/auth")
async def api_auth(body: AuthBody):
    if not ACCESS_PASSWORD:
        return {"ok": True, "needs_auth": False, "token": ""}
    if (body.password or "").strip() != ACCESS_PASSWORD:
        return JSONResponse({"ok": False, "detail": "invalid password"}, status_code=403)
    token = _issue_token(body.password.strip())
    return {"ok": True, "needs_auth": True, "token": token}


@app.get("/api/config")
async def api_get_config(x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    return {"ok": True, "config": _public_config(), "needs_auth": bool(ACCESS_PASSWORD)}


@app.put("/api/config")
async def api_put_config(body: ConfigBody, x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    engine.load_config()
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in SECRET_FIELDS and isinstance(value, str):
            stripped = value.strip()
            # Empty string clears the secret.
            if stripped == "":
                engine.config[key] = ""
                continue
            # Masked placeholder from GET — keep previous value.
            if "*" in stripped:
                continue
        engine.config[key] = value
    # Server hard-forces proxy quality (env GROK_FORCE_PROXY_QUALITY default on).
    # Cliproxy white: judge EXIT residential via IPPure; entry gateway may be Zenlayer.
    force_q = os.environ.get("GROK_FORCE_PROXY_QUALITY", "1").strip().lower()
    if force_q in ("1", "true", "yes", "on"):
        engine.config["proxy_quality_check"] = True
        engine.config["proxy_check_exit_ippure"] = True
        engine.config["proxy_reject_datacenter_org"] = True
        # Do not force entry hard-reject — white API entry is shared DC by design.
        engine.config["proxy_entry_hard_reject"] = False
    # Web panel SOCKS5 pool: save textarea -> config + socks5_proxies.txt
    if "proxy_list" in updates or str(engine.config.get("proxy_mode") or "").strip().lower() in (
        "socks5_list",
        "socks5_pool",
        "proxy_list",
        "list",
        "socks5",
    ):
        _sync_proxy_list_file(str(engine.config.get("proxy_list") or ""), engine.config)
    # Outlook account pool: keep textarea + outlook_accounts.txt in sync
    if "outlook_accounts" in updates:
        raw = str(engine.config.get("outlook_accounts") or "")
        name = str(engine.config.get("outlook_accounts_file") or "outlook_accounts.txt").strip() or "outlook_accounts.txt"
        path = Path(name) if os.path.isabs(name) else (ROOT / name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = raw.rstrip('\n')
            path.write_text((body + '\n') if body else "", encoding="utf-8")
            engine.config["outlook_accounts_file"] = name
        except Exception as exc:
            _append_log(f"[!] write outlook_accounts file failed: {exc}")
        try:
            import outlook_mail as _om
            _om.get_pool(engine.config, force_reload=True)
        except Exception:
            pass
    # AOL account pool: keep textarea + aol_accounts.txt in sync
    if "aol_accounts" in updates:
        raw = str(engine.config.get("aol_accounts") or "")
        name = str(engine.config.get("aol_accounts_file") or "aol_accounts.txt").strip() or "aol_accounts.txt"
        path = Path(name) if os.path.isabs(name) else (ROOT / name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = raw.rstrip("\n")
            path.write_text((body + "\n") if body else "", encoding="utf-8")
            engine.config["aol_accounts_file"] = name
        except Exception as exc:
            _append_log(f"[!] write aol_accounts file failed: {exc}")
        try:
            import aol_mail as _am
            _am.get_pool(engine.config, force_reload=True)
        except Exception:
            pass
    engine.save_config()
    return {"ok": True, "config": _public_config()}


@app.get("/api/status")
async def api_status(x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    with _job_lock:
        state = dict(_job_state)
    return {"ok": True, **state}


@app.post("/api/proxy/test")
async def api_proxy_test(x_access_key: Optional[str] = Header(None)):
    """Test current proxy mode (airport / Cliproxy / custom) and probe exit via IPPure."""
    _require_auth(x_access_key)
    engine.load_config()
    logs: List[str] = []

    def _log(msg: str) -> None:
        logs.append(str(msg))

    try:
        mode = str(engine.config.get("proxy_mode") or "").strip().lower()
        if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
            proxy = engine.fetch_cliproxy_white_proxy(engine.config, log_callback=_log)
        else:
            proxy = engine.resolve_runtime_proxy(
                engine.config, log_callback=_log, fetch_live=True
            )
            if not proxy:
                raise RuntimeError("当前模式无可用代理（直连或未配置）")
            try:
                pool_n = len(engine.load_proxy_list(engine.config)) if hasattr(engine, "load_proxy_list") else 0
            except Exception:
                pool_n = 0
            if mode in ("socks5_list", "socks5_pool", "proxy_list", "list", "socks5"):
                _log(f"[+] SOCKS5通用池 选用: {proxy} | 池大小={pool_n}")
            else:
                _log(f"[+] 当前代理: {proxy}")
        quality = None
        try:
            quality = engine.probe_proxy_with_ippure(
                proxy,
                quality_api=str(
                    engine.config.get("proxy_quality_api") or "https://my.ippure.com/v1/info"
                ),
            )
            if quality:
                _log(
                    f"[*] 出口 IPPure: ip={quality.get('ip')} "
                    f"country={quality.get('countryCode')} "
                    f"fraud={quality.get('fraudScore')} "
                    f"residential={quality.get('isResidential')} "
                    f"org={quality.get('asOrganization') or quality.get('org') or ''}"
                )
        except Exception as qe:
            logs.append(f"[!] 复检 IPPure 失败: {qe}")
        return {"ok": True, "proxy": proxy, "quality": quality, "logs": logs}
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "detail": str(exc), "logs": logs},
            status_code=400,
        )


@app.post("/api/start")
async def api_start(body: StartBody, x_access_key: Optional[str] = Header(None)):
    global _job_thread
    _require_auth(x_access_key)
    with _job_lock:
        if _job_state["running"]:
            raise HTTPException(status_code=409, detail="job already running")
        # clear log for new run but keep last few
        _append_log(f"[*] starting registration count={body.count}")
        t = threading.Thread(target=_run_job, args=(body.count,), daemon=True)
        _job_thread = t
        t.start()
    return {"ok": True, "started": True, "count": body.count}


@app.post("/api/stop")
async def api_stop(x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    with _job_lock:
        ctrl = _controller
        running = bool(_job_state.get("running"))
    # Always try hard cleanup: even if job state is stale, kill browsers.
    _append_log("[!] stop requested from web")
    try:
        if ctrl is not None:
            ctrl.stop(force_cleanup=True)
        else:
            engine.force_stop_registration(
                log_callback=_append_log, reason="web_stop_no_controller"
            )
    except TypeError:
        # older controller without force_cleanup kw
        try:
            if ctrl is not None:
                ctrl.stop()
        except Exception:
            pass
        try:
            engine.force_stop_registration(
                log_callback=_append_log, reason="web_stop_fallback"
            )
        except Exception as exc:
            _append_log(f"[!] force_stop after stop failed: {exc}")
    except Exception as exc:
        _append_log(f"[!] stop cleanup error: {exc}")
        try:
            engine.force_stop_registration(
                log_callback=_append_log, reason="web_stop_exception"
            )
        except Exception:
            pass
    return {
        "ok": True,
        "stopped": bool(running or ctrl is not None),
        "running_was": running,
        "had_controller": ctrl is not None,
        "detail": (
            "stopped and browser cleanup attempted"
            if (running or ctrl is not None)
            else "no running job (browser cleanup attempted)"
        ),
    }


@app.get("/api/logs")
async def api_logs(
    request: Request,
    x_access_key: Optional[str] = Header(None),
    after: int = Query(0, ge=0),
):
    _require_auth(x_access_key)

    async def event_stream():
        last = after
        while True:
            if await request.is_disconnected():
                break
            with _log_cond:
                # snapshot
                buf = list(_log_buffer)
                seq = _log_seq
            # emit new lines relative to after
            start_idx = max(0, len(buf) - (seq - last)) if seq >= last else 0
            if last == 0:
                start_idx = 0
            else:
                # lines with global indices (seq - len + i)
                start_idx = max(0, len(buf) - (seq - last))
            new_lines = buf[start_idx:]
            for line in new_lines:
                yield f"data: {line}\n\n"
            last = seq
            # wait a bit for more
            await asyncio.sleep(0.5)
            with _log_cond:
                if _log_seq == last and not _job_state["running"]:
                    # keep connection for a short idle then continue
                    pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/logs/snapshot")
async def api_logs_snapshot(
    x_access_key: Optional[str] = Header(None),
    limit: int = Query(200, ge=1, le=2000),
):
    _require_auth(x_access_key)
    with _log_cond:
        lines = list(_log_buffer)[-limit:]
        seq = _log_seq
    return {"ok": True, "seq": seq, "lines": lines}



@app.post("/api/logs/clear")
async def api_logs_clear(x_access_key: Optional[str] = Header(None)):
    """Clear server-side log buffer so Web '清空显示' stays empty."""
    _require_auth(x_access_key)
    global _log_seq
    with _log_cond:
        _log_buffer.clear()
        _log_seq += 1
        seq = _log_seq
        _log_cond.notify_all()
    return {"ok": True, "seq": seq, "cleared": True}


class CpaImportBody(BaseModel):
    directory: Optional[str] = None
    file: Optional[str] = None
    limit: Optional[int] = 0
    verify: Optional[bool] = False
    update_existing: Optional[bool] = True
    stop_on_error: Optional[bool] = False



@app.get("/api/sub2api/status")
async def api_sub2api_status(x_access_key: Optional[str] = Header(None)):
    """Refresh Sub2API pool status: healthy + grok account_count. No secrets."""
    _require_auth(x_access_key)
    engine.load_config()
    sub2 = _probe_sub2api(engine.config)
    return {"ok": True, "sub2api": sub2}


@app.post("/api/sub2api/import-cpa")
async def api_sub2api_import_cpa(body: CpaImportBody, x_access_key: Optional[str] = Header(None)):
    """Import CLIProxy/CPA xai-*.json OAuth files into Sub2API admin accounts."""
    _check_auth(x_access_key)
    cfg = engine.load_config()
    directory = (body.directory or cfg.get("sub2api_cpa_import_dir") or "").strip()
    file_path = (body.file or "").strip()
    if not directory and not file_path:
        raise HTTPException(status_code=400, detail="directory 或 file 必填")
    update_existing = True if body.update_existing is None else bool(body.update_existing)
    if body.update_existing is None and "sub2api_cpa_update_existing" in cfg:
        update_existing = bool(cfg.get("sub2api_cpa_update_existing"))
    verify = bool(body.verify)
    limit = int(body.limit or 0)
    stop_on_error = bool(body.stop_on_error)

    def _job_log(msg: str) -> None:
        try:
            engine.append_log(msg)
        except Exception:
            pass

    try:
        from sub2api_client import import_cpa_dir_to_sub2api, import_cpa_file_to_sub2api
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"sub2api_client 不可用: {exc}") from exc

    try:
        if file_path:
            result = await asyncio.to_thread(
                import_cpa_file_to_sub2api,
                file_path,
                config=cfg,
                log_callback=_job_log,
                update_existing=update_existing,
                verify_after_import=verify,
            )
            return {
                "ok": bool(result.get("ok")),
                "mode": "file",
                "account_id": result.get("account_id"),
                "action": result.get("action") or result.get("mode"),
                "email": result.get("email") or "",
                "usable": result.get("usable"),
                "source": Path(str(result.get("source") or file_path)).name,
            }
        summary = await asyncio.to_thread(
            import_cpa_dir_to_sub2api,
            directory,
            config=cfg,
            log_callback=_job_log,
            update_existing=update_existing,
            verify_after_import=verify,
            limit=limit,
            stop_on_error=stop_on_error,
        )
        return {
            "ok": bool(summary.get("ok")),
            "mode": "directory",
            "directory": summary.get("directory"),
            "total": summary.get("total"),
            "imported": summary.get("imported"),
            "created": summary.get("created"),
            "updated": summary.get("updated"),
            "failed": summary.get("failed"),
            "errors": summary.get("errors") or [],
            "results": (summary.get("results") or [])[:50],
        }
    except HTTPException:
        raise
    except Exception as exc:
        _job_log(f"[!] Sub2API CPA 导入异常: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)[:500]) from exc


class PendingRecoverBody(BaseModel):
    count: int = Field(0, ge=0, le=500)


@app.post("/api/pending-sso/recover")
async def api_pending_sso_recover(
    body: PendingRecoverBody = PendingRecoverBody(),
    x_access_key: Optional[str] = Header(None),
):
    """Start secondary SSO recovery for pending accounts."""
    global _job_thread
    _require_auth(x_access_key)
    with _job_lock:
        if _job_state["running"]:
            raise HTTPException(status_code=409, detail="job already running")
        count = int(body.count or 0)
        _append_log(f"[*] starting pending_sso recovery count={count or 'all'}")
        t = threading.Thread(
            target=_run_job,
            args=(count,),
            kwargs={"job_kind": "pending_sso_recovery"},
            daemon=True,
        )
        _job_thread = t
        t.start()
    return {"ok": True, "started": True, "count": count, "job_kind": "pending_sso_recovery"}


@app.get("/api/accounts")
async def api_accounts_list(x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    files = sorted(ROOT.glob("accounts_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        }
        for f in files[:50]
    ]
    pending_fixed = ROOT / "accounts_registered_pending_sso.txt"
    pending_files = sorted(ROOT.glob("accounts_no_sso_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    pending_count = 0
    if pending_fixed.is_file():
        try:
            pending_count = sum(
                1
                for ln in pending_fixed.read_text(encoding="utf-8", errors="ignore").splitlines()
                if ln.strip() and not ln.strip().startswith("#") and "----" in ln
            )
        except Exception:
            pending_count = 0
    pending = {
        "fixed_file": pending_fixed.name if pending_fixed.is_file() else "",
        "fixed_count": pending_count,
        "timestamped": [
            {"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime}
            for f in pending_files[:20]
        ],
    }
    return {"ok": True, "files": items, "pending_sso": pending}


@app.get("/api/accounts/download")
async def api_accounts_download(
    x_access_key: Optional[str] = Header(None),
    name: Optional[str] = Query(None),
):
    _require_auth(x_access_key)
    if name:
        # prevent path traversal
        safe = Path(name).name
        path = ROOT / safe
        allowed = (
            (safe.startswith("accounts_") and safe.endswith(".txt"))
            or safe == "accounts_registered_pending_sso.txt"
            or (safe.startswith("accounts_no_sso_") and safe.endswith(".txt"))
        )
        if not allowed or not path.is_file():
            raise HTTPException(status_code=404, detail="file not found")
    else:
        files = sorted(ROOT.glob("accounts_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise HTTPException(status_code=404, detail="no accounts file")
        path = files[0]
    return FileResponse(
        path,
        filename=path.name,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "web.server:app",
        host=HOST,
        port=PORT,
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()



