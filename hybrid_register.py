"""Hybrid Grok registration: protocol RPC + browser tokens.

Used by Web/CLI when config register_mode == "hybrid".

Changelog:
- 2026-07-17f: 修复 Web 停止竞态：打开注册页时传入 should_stop，浏览器被停止关闭后
  不再继续 new_tab；停止操作不计为注册失败，也不输出误导性的 NoneType 堆栈。
- 2026-07-17e: 协议 curl 超时(0 bytes)根因修复：跳过已有候选时的 curl chunk discover；
  SignUp 超时降至 18s；curl 超时/status=0 立即停止协议重试（不再试 hardcoded 死哈希）；
  协议失败后优先浏览器同源 fetch SignUp，再 UI 点提交；详细网络路径日志不脱敏。
- 2026-07-17d: SignUp 提交前强制刷新 castle（不再复用 CreateEmail 旧 token）；
  200 无 sso 详细日志（body/set-cookie/hints）；协议失败后浏览器 UI 资料提交兜底；
  注册成功/登录失败邮箱从 AOL/Outlook 账号池文件永久删除。
- 2026-07-17c: 邮箱登录失败自动换下一个（最多 20 次）；preflight 预登录；
  CreateEmail 后等 3s 再查信；AOL/Outlook 扫 ALL 文件夹（非仅 Inbox/Junk）。
  修复缩进损坏导致 IndentationError 无法启动。
- 2026-07-17b: CreateEmail 发信证据门禁 + since_ts 查信。
"""
from __future__ import annotations

import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent

from browser.token_harvester import BrowserTokenSession  # noqa: E402
from protocol.grpc_client import AuthManagementClient  # noqa: E402
from protocol.session import ProtocolSession  # noqa: E402


def load_next_action_from_capture() -> str:
    rpc = ROOT / "capture_out" / "rpc"
    for name in ("03_SignUpSubmit.req.headers.json",):
        p = rpc / name
        if p.is_file():
            try:
                import json

                h = json.loads(p.read_text(encoding="utf-8"))
                return h.get("next-action") or h.get("Next-Action") or ""
            except Exception:
                pass
    if rpc.is_dir():
        import json

        for f in rpc.glob("*.req.headers.json"):
            try:
                h = json.loads(f.read_text(encoding="utf-8"))
                if h.get("next-action"):
                    return h["next-action"]
            except Exception:
                pass
    return ""



def save_next_action_to_capture(action: str, log: Callable[[str], None] | None = None) -> None:
    """Persist a known-good next-action so later runs prefer a live working hash."""
    act = (action or "").strip()
    if not act:
        return
    try:
        import json

        rpc = ROOT / "capture_out" / "rpc"
        rpc.mkdir(parents=True, exist_ok=True)
        path = rpc / "03_SignUpSubmit.req.headers.json"
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data["next-action"] = act
        data["Next-Action"] = act
        data["_saved_by"] = "hybrid_register"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if log:
            log(f"[hybrid] saved working next-action hash={act[:20]}... len={len(act)}")
    except Exception as exc:
        if log:
            log(f"[hybrid] save next-action fail: {exc}")


def _account_scan_dirs() -> list[Path]:
    """Dirs that may contain successful Grok account dumps."""
    dirs = [
        ROOT,
        Path.home() / "Desktop" / "Gark",
        Path.home() / "Desktop" / "Grok",
        Path.home() / "Desktop" / "grok-regkit",
        Path(r"C:/Users/zhang/Desktop/Gark"),
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        try:
            key = str(d.resolve()) if d.exists() else str(d)
        except Exception:
            key = str(d)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _registry_path() -> Path:
    return ROOT / "registered_emails_registry.txt"


def load_registered_emails() -> set[str]:
    """Emails already saved as successful Grok registrations (multi-dir + local registry)."""
    out: set[str] = set()
    reg = _registry_path()
    if reg.is_file():
        try:
            for line in reg.read_text(encoding="utf-8", errors="ignore").splitlines():
                email = (line.split("----")[0] or line.strip() or "").strip().lower()
                if email and "@" in email:
                    out.add(email)
        except Exception:
            pass
    patterns = ("accounts*.txt", "accounts_hybrid_*.txt", "accounts_browser_*.txt")
    for base in _account_scan_dirs():
        if not base.exists() or not base.is_dir():
            continue
        for pat in patterns:
            try:
                for pth in base.glob(pat):
                    try:
                        for line in pth.read_text(encoding="utf-8", errors="ignore").splitlines():
                            email = (line.split("----")[0] or "").strip().lower()
                            if email and "@" in email:
                                out.add(email)
                    except Exception:
                        continue
            except Exception:
                continue
    return out


def remember_registered_email(email: str, log: Callable[[str], None] | None = None) -> None:
    """Append email to local registry so future runs skip it even if accounts file is elsewhere."""
    em = (email or "").strip().lower()
    if not em or "@" not in em:
        return
    try:
        path = _registry_path()
        existing: set[str] = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                e = (line.split("----")[0] or line.strip() or "").strip().lower()
                if e:
                    existing.add(e)
        if em not in existing:
            with path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(em + "\n")
            if log:
                log(f"[hybrid] registry +1 registered email: {em} (total_was={len(existing)})")
    except Exception as exc:
        if log:
            log(f"[hybrid] registry write fail: {exc}")


def mark_outlook_registered(email: str, log: Callable[[str], None] | None = None) -> None:
    """Mark registered and permanently remove mailbox from AOL/Outlook pools."""
    remember_registered_email(email, log)
    remove_mailbox_from_pool(email, reason="registered", log=log)


def remove_mailbox_from_pool(
    email: str,
    reason: str = "removed",
    log: Callable[[str], None] | None = None,
) -> None:
    """Permanently delete email from AOL/Outlook account pool files."""
    em = (email or "").strip()
    if not em:
        return
    em_l = em.lower()
    try:
        from grok_register_ttk import config as _cfg
    except Exception:
        _cfg = {}

    # AOL / AIM
    try:
        import aol_mail as am

        pool = getattr(am, "_POOL", None)
        if pool is None:
            try:
                pool = am.get_pool(_cfg, log_callback=log)
            except Exception:
                pool = getattr(am, "_POOL", None)
        if pool is not None and hasattr(pool, "remove_account"):
            pool.remove_account(em, reason=reason)
        elif pool is not None:
            # fallback release bad
            try:
                pool.release(em, ok=False, bad=True)
            except Exception:
                pass
    except Exception as exc:
        if log:
            log(f"[hybrid] AOL pool remove fail email={em}: {exc}")

    # Outlook / Hotmail / Live
    try:
        import outlook_mail as om

        pool = getattr(om, "_POOL", None)
        if pool is None:
            try:
                pool = om.get_pool(_cfg, log_callback=log)
            except Exception:
                pool = getattr(om, "_POOL", None)
        if pool is not None and hasattr(pool, "remove_account"):
            pool.remove_account(em, reason=reason)
        elif pool is not None:
            with om._POOL_LOCK:
                for acc in list(pool.accounts):
                    if acc.identity() == em_l:
                        acc.status = "registered" if reason == "registered" else "bad"
                        acc.cooldown_until = time.time() + 86400 * 365
                        if log:
                            log(f"[hybrid] Outlook marked {acc.status}: {em}")
                        break
    except Exception as exc:
        if log:
            log(f"[hybrid] Outlook pool remove fail email={em}: {exc}")


def register_one_hybrid(
    *,
    log: Callable[[str], None],
    proxy: str = "",
    user_agent: str = "",
    next_action: str = "",
    accounts_file: Path,
    should_stop: Optional[Callable[[], bool]] = None,
    post_success: bool = True,
) -> bool:
    """Register one account via hybrid path. Returns True on SSO success.

    Each account uses its own browser session (open at start, close at end).
    """
    from grok_register_ttk import (
        build_profile,
        get_email_and_token,
        get_oai_code,
        schedule_post_registration,
    )

    stop = should_stop or (lambda: False)
    t0 = time.time()
    action = (next_action or load_next_action_from_capture() or "").strip()

    try:
        with BrowserTokenSession(log=log) as browser:
            if stop():
                return False
            log("[browser] open signup page for this account")
            browser.open_signup(cancel_callback=stop)
            browser.install_network_hook()
            action = action or browser.scrape_next_action() or action
            log(f"[hybrid] next-action ready len={len(action or '')} value={action or ''}")

            registered = load_registered_emails()
            email, mail_token = "", ""
            for _try in range(20):
                if stop():
                    return False
                try:
                    email, mail_token = get_email_and_token()
                except Exception as get_exc:
                    log(f"[hybrid] 获取邮箱失败(池内可能都登录失败): {get_exc}")
                    return False
                if not email:
                    log("[hybrid] no fresh email available (pool exhausted / all registered?)")
                    return False
                if email.lower() in registered:
                    log(f"[hybrid] skip already-registered local email: {email}")
                    try:
                        em_l = email.lower()
                        from grok_register_ttk import config as _cfg_skip
                        if em_l.endswith(("@aol.com", "@aim.com")):
                            import aol_mail as om_skip
                            om_skip.get_pool(_cfg_skip, log_callback=log).release(email, ok=True)
                        else:
                            import outlook_mail as om_skip
                            pool = om_skip.get_pool(_cfg_skip, log_callback=log)
                            pool.release(email, ok=True)
                            mark_outlook_registered(email, log)
                    except Exception as rel_exc:
                        log(f"[hybrid] release/skip email: {rel_exc}")
                    email, mail_token = "", ""
                    continue

                log(
                    f"[hybrid] email={email} mail_token_len={len(str(mail_token or ''))} "
                    f"mail_token={mail_token}"
                )

                # Pre-login mailbox BEFORE CreateEmail; fail -> next email
                try:
                    from grok_register_ttk import config as _cfg_pre, get_email_provider as _gep

                    prov = str(_gep() or "").strip().lower()
                    em_l = (email or "").lower()
                    is_aol = False
                    try:
                        import aol_mail as _am
                        is_aol = _am.is_aol_provider(prov) or em_l.endswith(("@aol.com", "@aim.com"))
                    except Exception:
                        is_aol = em_l.endswith(("@aol.com", "@aim.com"))
                    if is_aol:
                        import aol_mail as am
                        pre = am.preflight_mailbox(
                            _cfg_pre, mail_token, email, log_callback=log, top=15
                        )
                        log(
                            f"[hybrid] AOL pre-login OK email={email} "
                            f"auth={pre.get('auth')} total={pre.get('total')} "
                            f"counts={pre.get('folder_counts')} "
                            f"scanned_folders={pre.get('scanned_folders')} top={pre.get('top')}"
                        )
                    else:
                        import outlook_mail as om
                        pre = om.preflight_mailbox(
                            _cfg_pre, mail_token, email, log_callback=log, top=25
                        )
                        log(
                            f"[hybrid] Outlook pre-login OK email={email} "
                            f"auth={pre.get('auth')} "
                            f"counts={pre.get('folder_counts')} total={pre.get('total')} "
                            f"scanned_folders={pre.get('scanned_folders')} top={pre.get('top')}"
                        )
                    break
                except Exception as pre_exc:
                    log(
                        f"[hybrid] mailbox pre-login FAIL email={email}: {pre_exc} | "
                        f"换下一个邮箱 continue try={_try + 1}/20"
                    )
                    try:
                        em_l2 = (email or "").lower()
                        bad = any(
                            x in str(pre_exc)
                            for x in (
                                "AUTHENTICATIONFAILED",
                                "Invalid credentials",
                                "LOGIN",
                                "password login failed",
                                "MFA/TOTP",
                                "401",
                                "invalid_grant",
                                "AADSTS",
                                "authentication failed",
                            )
                        )
                        if bad:
                            remove_mailbox_from_pool(email, reason="login_fail", log=log)
                        else:
                            # temporary: release back to idle/cooldown without permanent delete
                            from grok_register_ttk import config as _cfg_pre2
                            if em_l2.endswith(("@aol.com", "@aim.com")):
                                import aol_mail as am2
                                am2.get_pool(_cfg_pre2, log_callback=log).release(
                                    email, ok=False, bad=False
                                )
                            else:
                                import outlook_mail as om2
                                om2.get_pool(_cfg_pre2, log_callback=log).release(
                                    email, ok=False, bad=False
                                )
                    except Exception as rel_pre:
                        log(f"[hybrid] pre-login release email: {rel_pre}")
                    email, mail_token = "", ""
                    continue
            else:
                log("[hybrid] 连续尝试邮箱均失败（登录/预检），放弃本号")
                return False

            if not email:
                log("[hybrid] no fresh email available after retries")
                return False
            if stop():
                return False

            # Browser UI submit triggers native CreateEmail (passes CF). Capture castle from that request.
            castle = browser.harvest_castle_via_email_submit(email, timeout=45)

            browser_cookies = browser.export_cookies()
            if not castle or len(castle) < 1000 or not str(castle).startswith("IBYIll"):
                log(
                    f"[hybrid] bad castle len={len(castle or '')} head={(castle or '')[:24]}"
                )
                return False

            ua = browser.browser_user_agent() or user_agent or ""
            sess = ProtocolSession(
                proxy=(proxy or "").strip(),
                user_agent=ua,
                impersonate="chrome131",
            )
            # Prefer fresh signup cookies; strip old sso so server doesn't treat as logged-in.
            jar = dict(browser_cookies or {})
            for stale in ("sso", "sso-rw"):
                jar.pop(stale, None)
            sess.set_cookies(jar)
            client = AuthManagementClient(sess)
            if action:
                client.next_action = action

            # Strict CreateEmail evidence: never skip polling on "have castle only".
            st = browser.create_email_status_via_browser()
            log(
                f"[hybrid] CreateEmail UI click status={st.get('status')} seen={st.get('seen')} "
                f"ok={st.get('ok')} net_hits={st.get('net_hits')} sent={st.get('sent')} "
                f"reason={st.get('reason')} castle_len={len(castle)}"
            )
            browser_sent = bool(st.get("sent"))
            protocol_sent = False
            if browser_sent:
                log(
                    f"[hybrid] CreateEmail via browser OK (skip protocol) "
                    f"castle_len={len(castle)} reason={st.get('reason')}"
                )
            else:
                try:
                    click2 = browser.click_email_continue_for_create(email)
                    log(f"[hybrid] CreateEmail re-click={click2}")
                    time.sleep(2.5)
                    st = browser.create_email_status_via_browser()
                    browser_sent = bool(st.get("sent"))
                    log(
                        f"[hybrid] CreateEmail after re-click status={st.get('status')} "
                        f"seen={st.get('seen')} ok={st.get('ok')} sent={st.get('sent')} "
                        f"reason={st.get('reason')}"
                    )
                except Exception as re_exc:
                    log(f"[hybrid] CreateEmail re-click error: {re_exc}")

            if not browser_sent:
                r1 = client.create_email_validation_code(email, castle)
                log(f"[hybrid] CreateEmail protocol status={r1['status']} castle_len={len(castle)}")
                if r1["status"] >= 400:
                    body_hint = ""
                    try:
                        raw = r1.get("raw") or b""
                        if b"cloudflare" in raw[:500].lower() or b"<!DOCTYPE" in raw[:200]:
                            body_hint = " (Cloudflare block)"
                    except Exception:
                        pass
                    log(f"[hybrid] CreateEmail fail{body_hint} strings={r1.get('strings')[:2]}")
                    log(
                        "[hybrid] CreateEmail 未真正发信（UI 无 seen/ok 且协议失败），"
                        "跳过 180s 空等验证码"
                    )
                    return False
                protocol_sent = True
                log(f"[hybrid] CreateEmail via protocol OK status={r1['status']}")

            if not browser_sent and not protocol_sent:
                log("[hybrid] CreateEmail 无发信迹象，禁止空等验证码")
                return False
            if stop():
                return False

            send_ts = time.time()
            log(
                f"[hybrid] CreateEmail done send_ts={send_ts:.3f} email={email} "
                f"browser_sent={browser_sent} protocol_sent={protocol_sent}; "
                f"wait 3s before poll mail (AOL/Outlook ALL folders)"
            )
            # Wait 3s after send so Graph has time to receive; support cancel.
            for _w in range(30):
                if stop():
                    log("[hybrid] stop during post-CreateEmail 3s wait")
                    return False
                if time.time() - send_ts >= 3.0:
                    break
                time.sleep(0.1)
            log(
                f"[hybrid] 开始查邮件 email={email} timeout=180s since_ts={send_ts:.3f} "
                f"elapsed_since_send={time.time() - send_ts:.2f}s "
                f"(scan ALL mail folders; cancel 支持已启用)"
            )
            code = get_oai_code(
                mail_token,
                email,
                log_callback=log,
                cancel_callback=stop,
                since_ts=send_ts,
            )
            clean = str(code or "").replace("-", "").strip()
            if not clean:
                log("[hybrid] no mail code")
                return False
            log(f"[hybrid] code={clean}")

            r2 = client.verify_email_validation_code(email, clean)
            log(f"[hybrid] VerifyEmail status={r2['status']}")
            if r2["status"] >= 400:
                log(f"[hybrid] VerifyEmail fail {r2.get('strings')[:5]}")
                return False
            if stop():
                return False

            given, family, password = build_profile()
            try:
                client.validate_password(email, password)
            except Exception:
                pass

            if stop():
                log("[hybrid] stop before turnstile")
                return False
            turnstile = browser.get_turnstile_token(timeout=90, inject=True, cancel_callback=stop)
            if stop():
                log("[hybrid] stop after turnstile")
                return False
            if len(turnstile) < 80:
                log(f"[hybrid] turnstile short len={len(turnstile)}")
                return False

            # CRITICAL: frontend mints a NEW castle via createRequestToken() on every SignUp.
            # Reusing CreateEmail castle often yields HTTP 200 RSC fragment with no sso cookie.
            castle2 = browser.read_captured_castle() or castle
            if len(castle2) < 1000:
                castle2 = castle
            log(
                f"[hybrid] mint fresh castle for SignUp (old_len={len(castle2)} "
                f"old_head={(castle2 or '')[:36]})"
            )
            try:
                fresh_castle = browser.get_castle_token_injected(timeout=20) or ""
                if (not fresh_castle or len(fresh_castle) < 1000) and hasattr(
                    browser, "get_castle_token"
                ):
                    fresh_castle = browser.get_castle_token(timeout=15) or fresh_castle
                if fresh_castle and len(fresh_castle) >= 1000:
                    castle2 = fresh_castle
                    log(
                        f"[hybrid] fresh castle ok len={len(castle2)} "
                        f"head={castle2[:48]}"
                    )
                else:
                    log(
                        f"[hybrid] fresh castle weak len={len(fresh_castle or '')}; "
                        f"reuse previous head={(castle2 or '')[:36]}"
                    )
            except Exception as castle_exc:
                log(f"[hybrid] fresh castle mint fail: {castle_exc}; reuse previous")

            browser_cookies = browser.export_cookies()
            jar2 = dict(browser_cookies or {})
            for stale in ("sso", "sso-rw"):
                jar2.pop(stale, None)
            sess.set_cookies(jar2)
            # Build next-action candidates. Prefer browser (CF/proxy already working).
            # Hardcoded known is last resort only — xAI redeploys invalidate it (404).
            known = "7f50061dd2f5b389a530e4a048d5fdf0c48d1d9259"
            candidates: list[str] = []

            def _add_action(val: str, src: str):
                v = (val or "").strip()
                if not v:
                    return
                if v not in candidates:
                    candidates.append(v)
                    log(
                        f"[hybrid] next-action candidate[{len(candidates)}] "
                        f"src={src} hash={v[:20]}... len={len(v)}"
                    )

            log("[hybrid] resolving next-action after turnstile…")
            try:
                scraped = browser.scrape_next_action() or ""
                _add_action(scraped, "browser_scrape")
            except Exception as scrape_exc:
                log(f"[hybrid] browser scrape next-action fail: {scrape_exc}")
            _add_action(action, "earlier_or_capture")
            if stop():
                return False
            _add_action(load_next_action_from_capture(), "capture_file")
            # curl chunk discover often hangs 20s with 0 bytes when SOCKS/proxy path is dead
            # for accounts.x.ai static chunks. Skip if we already have live candidates.
            if candidates:
                log(
                    f"[hybrid] skip curl chunk discover "
                    f"(have {len(candidates)} live candidate(s); avoid 20s timeout)"
                )
            else:
                try:
                    client.next_action = ""
                    discovered = client.discover_next_action(timeout=8) or ""
                    _add_action(discovered, "chunk_discover")
                except Exception as disc_exc:
                    log(f"[hybrid] chunk discover next-action fail: {disc_exc}")
            if stop():
                return False
            if not candidates:
                # Dead hash only when nothing else — expected 404 after redeploy.
                _add_action(known, "hardcoded_fallback")
            if not candidates:
                log("[hybrid] no next-action candidates at all")
                return False
            if stop():
                return False

            def _mint_castle_for_try(try_idx: int) -> str:
                nonlocal castle2
                if try_idx == 1:
                    return castle2
                try:
                    c = browser.get_castle_token_injected(timeout=12) or ""
                    if c and len(c) >= 1000:
                        castle2 = c
                        log(
                            f"[hybrid] re-mint castle for try {try_idx} "
                            f"len={len(c)} head={c[:40]}"
                        )
                        return c
                except Exception as exc:
                    log(f"[hybrid] re-mint castle fail try={try_idx}: {exc}")
                return castle2

            def _do_signup(act: str, castle_tok: str):
                # Short timeout: curl path often hangs 40s with 0 bytes on bad proxy.
                return client.create_user_via_server_action(
                    email=email,
                    code=clean,
                    given_name=given,
                    family_name=family,
                    password=password,
                    turnstile_token=turnstile,
                    castle_token=castle_tok,
                    next_action=act,
                    conversion_id=str(uuid.uuid4()),
                    timeout=18,
                )

            def _extract_sso(resp: dict) -> str:
                s = (resp or {}).get("sso") or ""
                if not s:
                    ck = (resp or {}).get("cookies") or {}
                    s = ck.get("sso") or ck.get("sso-rw") or ""
                return s or ""

            def _is_protocol_network_dead(st, body: str) -> bool:
                low = (body or "").lower()
                if st in (0, None):
                    return True
                return any(
                    k in low
                    for k in (
                        "curl: (28)",
                        "operation timed out",
                        "timed out after",
                        "0 bytes received",
                        "connection timed out",
                        "failed to perform",
                        "proxy",
                        "could not resolve",
                        "connection reset",
                        "ssl connect error",
                    )
                )

            def _log_signup_diag(idx: int, resp: dict, path: str = "protocol") -> None:
                body = str((resp or {}).get("text") or "")
                sc = (resp or {}).get("set_cookie_blob") or ""
                hints = (resp or {}).get("error_hints") or []
                redir = (resp or {}).get("redirect_url") or ""
                log(
                    f"[hybrid] sign-up diag path={path} try={idx} status={resp.get('status')} "
                    f"sso_len={len(_extract_sso(resp))} text_len={resp.get('text_len') or len(body)} "
                    f"castle_len={resp.get('castle_len')} turnstile_len={resp.get('turnstile_len')} "
                    f"tos={resp.get('tos_accepted_version')} redirect={redir!r} "
                    f"hints={hints} cookies={list(((resp.get('cookies') or {}).keys()))[:16]}"
                )
                if body:
                    log(f"[hybrid] sign-up body_head={body[:500]!r}")
                    if len(body) > 500:
                        log(f"[hybrid] sign-up body_tail={body[-400:]!r}")
                if sc:
                    log(f"[hybrid] sign-up set-cookie={sc[:500]!r}")

            r3 = {}
            sso = ""
            body_txt = ""
            protocol_network_dead = False
            for idx, act in enumerate(candidates, 1):
                if stop():
                    return False
                try:
                    jar3 = dict(browser.export_cookies() or {})
                    for stale in ("sso", "sso-rw"):
                        jar3.pop(stale, None)
                    sess.set_cookies(jar3)
                except Exception:
                    pass
                castle_tok = _mint_castle_for_try(idx)
                client.next_action = act
                log(
                    f"[hybrid] sign-up try {idx}/{len(candidates)} path=protocol/curl "
                    f"next-action={act[:20]}... castle_len={len(castle_tok)} timeout=18s"
                )
                t_try = time.time()
                try:
                    r3 = _do_signup(act, castle_tok)
                except Exception as signup_exc:
                    log(f"[hybrid] sign-up try {idx} exception: {signup_exc}")
                    r3 = {
                        "status": 0,
                        "text": str(signup_exc),
                        "cookies": {},
                        "sso": "",
                        "error_hints": ["exception"],
                    }
                sso = _extract_sso(r3)
                body_txt = str(r3.get("text") or "")
                st = r3.get("status")
                log(
                    f"[hybrid] sign-up try {idx} status={st} sso_len={len(sso)} "
                    f"elapsed={time.time() - t_try:.1f}s body={body_txt[:180]!r}"
                )
                if not sso:
                    _log_signup_diag(idx, r3, path="protocol/curl")
                if sso:
                    try:
                        save_next_action_to_capture(act, log)
                    except Exception:
                        pass
                    break
                low = body_txt.lower()
                # Keep keywords specific — avoid matching random RSC noise.
                if any(
                    k in low
                    for k in (
                        "already registered",
                        "already exists",
                        "email already",
                        "account already",
                        "signinmethods",
                        "sign_in_methods",
                        "email_already",
                        "already_exists",
                        "isloggedinwithsso",
                    )
                ):
                    log(
                        f"[hybrid] email/account state blocks sign-up, stop candidates: "
                        f"{body_txt[:240]}"
                    )
                    try:
                        mark_outlook_registered(email, log)
                    except Exception:
                        pass
                    break
                if _is_protocol_network_dead(st, body_txt):
                    protocol_network_dead = True
                    log(
                        "[hybrid] protocol network DEAD (curl timeout/0-byte/proxy) — "
                        "stop further protocol candidates; switch to browser same-origin path"
                    )
                    break
                if st == 404 or "server action not found" in low:
                    log(f"[hybrid] next-action {act[:16]} invalid (404/not found), try next")
                    continue
                log(
                    f"[hybrid] sign-up try {idx} no sso (status={st}); "
                    f"continue next candidate with fresh castle"
                )
            log(
                f"[hybrid] sign-up final status={r3.get('status')} sso_len={len(sso)} "
                f"elapsed={time.time() - t0:.1f}s protocol_network_dead={protocol_network_dead}"
            )
            if not sso:
                log(
                    f"[hybrid] protocol no sso cookies={list((r3.get('cookies') or {}).keys())[:12]} "
                    f"body={body_txt[:240]}"
                )
                if stop():
                    return False
                # Prefer browser same-origin fetch: browser already passed CF/proxy to accounts.x.ai
                live_acts = [c for c in candidates if c != known] or list(candidates)
                log(
                    f"[hybrid] browser same-origin fetch SignUp "
                    f"candidates={len(live_acts)} email={email}"
                )
                for bidx, act in enumerate(live_acts[:3], 1):
                    if stop():
                        return False
                    try:
                        castle_tok = _mint_castle_for_try(bidx + 10)
                        log(
                            f"[hybrid] browser-fetch try {bidx}/{min(3, len(live_acts))} "
                            f"next-action={act[:20]}... castle_len={len(castle_tok)}"
                        )
                        t_bf = time.time()
                        br = browser.fetch_signup_server_action(
                            email=email,
                            code=clean,
                            given_name=given,
                            family_name=family,
                            password=password,
                            turnstile_token=turnstile,
                            castle_token=castle_tok,
                            next_action=act,
                            conversion_id=str(uuid.uuid4()),
                            router_state_tree=getattr(client, "router_state_tree", "") or "",
                            timeout=25,
                        )
                        sso = _extract_sso(br) or ""
                        if not sso:
                            try:
                                jar_b = browser.export_cookies() or {}
                                sso = jar_b.get("sso") or jar_b.get("sso-rw") or ""
                            except Exception:
                                pass
                        body_txt = str((br or {}).get("text") or body_txt)
                        r3 = br or r3
                        log(
                            f"[hybrid] browser-fetch try {bidx} status={br.get('status')} "
                            f"sso_len={len(sso)} elapsed={time.time() - t_bf:.1f}s "
                            f"body={str(br.get('text') or '')[:180]!r}"
                        )
                        if not sso:
                            _log_signup_diag(bidx, br or {}, path="browser-fetch")
                        if sso:
                            try:
                                save_next_action_to_capture(act, log)
                            except Exception:
                                pass
                            break
                        st_b = br.get("status")
                        low_b = str(br.get("text") or "").lower()
                        if st_b == 404 or "server action not found" in low_b:
                            log(f"[hybrid] browser-fetch next-action {act[:16]} invalid, try next")
                            continue
                    except Exception as bf_exc:
                        log(f"[hybrid] browser-fetch try {bidx} error: {bf_exc}")
                if not sso and not stop():
                    log(
                        "[hybrid] browser-fetch no sso; UI profile submit fallback "
                        f"email={email} given={given} family={family}"
                    )
                    try:
                        ui_sso = browser.submit_profile_and_wait_sso(
                            given_name=given,
                            family_name=family,
                            password=password,
                            turnstile_token=turnstile,
                            timeout=90,
                            cancel_callback=stop,
                        )
                        if ui_sso:
                            sso = ui_sso
                            log(f"[hybrid] browser UI fallback sso ok len={len(sso)}")
                        else:
                            log("[hybrid] browser UI fallback got no sso")
                    except Exception as ui_exc:
                        log(f"[hybrid] browser UI fallback error: {ui_exc}")
            if not sso:
                log(
                    f"[hybrid] no sso after protocol+browser-fetch+UI cookies="
                    f"{list((r3.get('cookies') or {}).keys())[:12]} body={body_txt[:240]}"
                )
                return False

            # Hybrid often gets set-cookie *wrapper* JWT (~2k). CPA needs real session sso (~150).
            try:
                from protocol.sso_util import (
                    is_session_sso,
                    is_wrapper_sso,
                    materialize_sso_via_browser,
                    materialize_sso_via_http,
                )

                if is_wrapper_sso(sso) or not is_session_sso(sso):
                    log(f"[hybrid] sso looks like set-cookie wrapper len={len(sso)}; materialize…")
                    from grok_register_ttk import _get_page

                    page = _get_page()
                    sess_sso = ""
                    if page is not None:
                        sess_sso = materialize_sso_via_browser(
                            page, sso, log=log, timeout=40
                        )
                    if not sess_sso or not is_session_sso(sess_sso):
                        jar = dict(browser.export_cookies() or {})
                        sess_sso = materialize_sso_via_http(
                            sso,
                            proxy=(proxy or "").strip(),
                            extra_cookies=jar,
                            log=log,
                        ) or sess_sso
                    if sess_sso and is_session_sso(sess_sso):
                        log(f"[hybrid] session sso ready len={len(sess_sso)}")
                        sso = sess_sso
                    else:
                        log(
                            f"[hybrid] WARN still wrapper/non-session sso len={len(sso)}; "
                            f"CPA mint may fail until browser path works"
                        )
            except Exception as e:
                log(f"[hybrid] sso materialize: {e}")

            line = f"{email}----{password}----{sso}\n"
            try:
                with accounts_file.open("a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                log(f"[hybrid] save file fail: {e}")

            log(f"[hybrid][+] OK {email}")
            try:
                mark_outlook_registered(email, log)
            except Exception:
                pass
            if post_success:
                try:
                    # Export full browser jar (cf_clearance + sso) for CPA protocol mint
                    jar_full = dict(browser.export_cookies() or {})
                    if sso:
                        jar_full["sso"] = sso
                        jar_full["sso-rw"] = jar_full.get("sso-rw") or sso
                    cookie_list = [
                        {"name": k, "value": v, "domain": ".x.ai", "path": "/"}
                        for k, v in jar_full.items()
                        if k and v is not None
                    ]
                    log(f"[hybrid] post cookies={len(cookie_list)} for CPA/g2a")
                    schedule_post_registration(
                        email,
                        password,
                        sso,
                        page=None,
                        cookies=cookie_list,
                        log_callback=log,
                    )
                except Exception as e:
                    log(f"[hybrid] post_success: {e}")
            log(f"[hybrid] account success elapsed={time.time()-t0:.1f}s email={email}")
            return True
    except Exception as e:
        if stop():
            log("[hybrid] 已按停止请求中断当前账号，不计为注册失败")
            return False
        log(f"[hybrid] exception: {e}")
        try:
            log(traceback.format_exc())
        except Exception:
            pass
        return False


def run_hybrid_registration_job(count, log_callback=None, controller=None):
    """Web/CLI entry compatible with run_registration_job return shape."""
    import grok_register_ttk as engine

    log = log_callback or engine.cli_log
    if controller is None:
        controller = engine.CliStopController()

    success_count = 0
    fail_count = 0
    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_hybrid_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] 混合模式启动，目标数量: {count}")
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")

    mode = str(engine.config.get("proxy_mode", "direct") or "direct")
    try:
        resolved_proxy = engine.apply_resolved_proxy_to_config(
            log_callback=log, fetch_live=True
        )
    except Exception as proxy_exc:
        log(f"[!] 获取/解析代理失败: {proxy_exc}")
        raise

    if resolved_proxy:
        # Full proxy URL in logs (no redaction), per user request.
        log(f"[*] 代理模式: {mode} | {resolved_proxy}")
    else:
        log(f"[*] 代理模式: {mode or 'direct'}（直连）")

    next_action = load_next_action_from_capture()
    try:
        scan_dirs = [str(d) for d in _account_scan_dirs() if d.exists()]
        log(f"[hybrid] scan registered account dirs: {scan_dirs}")
        registered = load_registered_emails()
        log(f"[hybrid] already-registered emails loaded: {len(registered)}")
        if registered:
            for em in list(registered)[:500]:
                mark_outlook_registered(em, None)
            sample = ", ".join(list(sorted(registered))[:5])
            log(f"[hybrid] pre-marked Outlook pool; sample: {sample}")
    except Exception as pre_exc:
        log(f"[hybrid] pre-mark registered outlook fail: {pre_exc}")
    ua = str(engine.config.get("user_agent") or "")
    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    try:
        i = 0
        while i < count:
            if controller.should_stop():
                break
            log(f"--- [hybrid] 开始第 {i + 1}/{count} 个账号 ---")
            ok = register_one_hybrid(
                log=log,
                proxy=proxy,
                user_agent=ua,
                next_action=next_action,
                accounts_file=Path(accounts_output_file),
                should_stop=controller.should_stop,
                post_success=True,
            )
            if controller.should_stop():
                log("[*] 当前账号因停止请求中断，统计保持不变")
                break
            if ok:
                success_count += 1
            else:
                fail_count += 1
            i += 1
            log(f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count}")
            engine.sleep_with_cancel(1, controller.should_stop)
    except KeyboardInterrupt:
        controller.stop()
        log("[!] 收到 Ctrl+C，正在停止")
    except Exception as exc:
        log(f"[!] 混合任务异常: {exc}")
        try:
            log(traceback.format_exc())
        except Exception:
            pass
    finally:
        # Stop browser immediately so Web「停止」不会留下 Chromium 僵尸进程
        try:
            if controller.should_stop():
                engine.force_stop_registration(log_callback=log, reason="hybrid_job_stopped")
            else:
                engine.stop_browser(log_callback=log)
        except Exception as stop_exc:
            log(f"[!] hybrid finally stop browser: {stop_exc}")
            try:
                engine.force_kill_registration_browsers(log_callback=log)
            except Exception:
                pass
        # Don't block job end for long CPA browser mint (SSO already saved).
        try:
            engine.wait_post_success_queue(timeout=15 if controller.should_stop() else 45, log_callback=log)
        except Exception:
            pass
        try:
            engine.cleanup_runtime_memory(log_callback=log, reason="混合任务结束")
        except Exception:
            pass
        log(f"[*] 混合任务结束。成功 {success_count} | 失败 {fail_count}")

    return {
        "success": success_count,
        "fail": fail_count,
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
    }
