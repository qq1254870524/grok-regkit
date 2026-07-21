# -*- coding: utf-8 -*-
"""18r44c: process-wide SSO session_id claim + hard reject collisions before save/import."""
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
path = ROOT / "grok_register_ttk.py"
text = path.read_text(encoding="utf-8")
orig = text

# header bump
old_h = "# 18r44a: browser SSO isolation — reject stale sso cookie across same-worker multi-account; clear xAI session cookies on open_signup; Windows per-launch user-data"
new_h = (
    "# 18r44c: process-wide session_id claim — reject same SSO session_id across workers/emails before disk/G2A/Sub2; restart browser after each browser success\n"
    + old_h
)
if "18r44c:" not in text:
    text = text.replace(old_h, new_h, 1)
    text = text.replace(
        "Changelog:\n- 2026-07-22r44a:",
        "Changelog:\n- 2026-07-22r44c: 进程级 session_id 认领：同 session_id 第二邮箱禁止写盘/入池（防 G2A 少号）；browser 每号成功后 clear cookie + restart_browser 硬隔离。\n- 2026-07-22r44a:",
        1,
    )

helper = '''
# 18r44c: process-wide SSO session_id registry (prevent cross-account collision import)
_SSO_SESSION_CLAIM_LOCK = threading.Lock()
_SSO_SESSION_CLAIMS = {}  # session_id -> email


def _extract_sso_session_id(raw_token):
    """Decode xAI session JWT payload.session_id; empty if not parseable."""
    token = _normalize_sso_token(raw_token)
    if not token or token.count(".") != 2:
        return ""
    try:
        import base64 as _b64
        import json as _json
        pl = token.split(".")[1]
        pad = "=" * ((4 - len(pl) % 4) % 4)
        data = _json.loads(_b64.urlsafe_b64decode(pl + pad))
        sid = str((data or {}).get("session_id") or "").strip()
        return sid
    except Exception:
        return ""


def claim_sso_session_or_reject(raw_token, email="", log_callback=None):
    """Claim session_id for email. Returns (ok, session_id, owner_email).

    If another email already claimed this session_id, returns ok=False.
    Same email re-claim is allowed (idempotent).
    """
    log = log_callback or (lambda m: None)
    sid = _extract_sso_session_id(raw_token)
    em = str(email or "").strip().lower()
    if not sid:
        # no sid: allow but warn (cannot dedupe)
        try:
            log(f"[!] sso session_id missing email={email or '-'} — cannot hard-dedupe")
        except Exception:
            pass
        return True, "", ""
    with _SSO_SESSION_CLAIM_LOCK:
        owner = _SSO_SESSION_CLAIMS.get(sid)
        if owner and owner != em:
            try:
                log(
                    f"[!] SSO session collision REJECTED email={email} "
                    f"sid={sid[:13]}... already_owned_by={owner}"
                )
            except Exception:
                pass
            return False, sid, owner
        _SSO_SESSION_CLAIMS[sid] = em or owner or sid
        try:
            log(f"[*] SSO session claimed email={email or '-'} sid={sid[:13]}...")
        except Exception:
            pass
        return True, sid, em


def release_sso_session_claim(raw_token, email=""):
    """Optional release if registration fails after claim (not required for hard reject path)."""
    sid = _extract_sso_session_id(raw_token)
    em = str(email or "").strip().lower()
    if not sid:
        return
    with _SSO_SESSION_CLAIM_LOCK:
        owner = _SSO_SESSION_CLAIMS.get(sid)
        if owner and (not em or owner == em):
            _SSO_SESSION_CLAIMS.pop(sid, None)


'''

# insert helper after _is_importable_session_sso
marker = "def add_token_to_grok2api_local_pool(raw_token, email=\"\", log_callback=None):"
if "def claim_sso_session_or_reject" not in text:
    if marker not in text:
        raise SystemExit("marker add_token missing")
    text = text.replace(marker, helper + marker, 1)

# Gate schedule_post_registration at start
gate = '''def schedule_post_registration(
    email, password, sso, page=None, cookies=None, log_callback=None
):
    """After sso saved: NSFW + g2a + CPA. Prefer async so next account starts sooner.

    - enable_nsfw + nsfw_async=False → NSFW 同步（你需要立刻开时）
    - post_success_async=True → g2a / Sub2API / CPA（及 async NSFW）进后台
    - cookies: optional pre-exported jar (hybrid path has no live page)
    """
    log = log_callback or (lambda m: print(m, flush=True))
    # 18r44c: never import colliding session_id into G2A/Sub2
    try:
        ok_claim, sid, owner = claim_sso_session_or_reject(sso, email=email, log_callback=log)
        if not ok_claim:
            log(
                f"[!] skip post_registration due to SSO collision email={email} "
                f"sid={(sid or '')[:13]} owner={owner}"
            )
            return {"async": False, "queued": False, "skipped": "sso_session_collision", "owner": owner}
    except Exception as claim_exc:
        try:
            log(f"[!] sso session claim check fail (continue): {claim_exc}")
        except Exception:
            pass
'''

old_sched = '''def schedule_post_registration(
    email, password, sso, page=None, cookies=None, log_callback=None
):
    """After sso saved: NSFW + g2a + CPA. Prefer async so next account starts sooner.

    - enable_nsfw + nsfw_async=False → NSFW 同步（你需要立刻开时）
    - post_success_async=True → g2a / Sub2API / CPA（及 async NSFW）进后台
    - cookies: optional pre-exported jar (hybrid path has no live page)
    """
    log = log_callback or (lambda m: print(m, flush=True))
'''

if "skipped\": \"sso_session_collision\"" not in text and "sso_session_collision" not in text.split("def schedule_post_registration")[1][:800]:
    if old_sched not in text:
        raise SystemExit("schedule_post header not found exact")
    text = text.replace(old_sched, gate, 1)

# Browser MT: after wait_for_sso, claim before write; on collision -> pending + restart
old_mt = '''        try:
            sso = wait_for_sso_cookie(
                log_callback=wlog, cancel_callback=controller.should_stop
            )
        except Exception as sso_exc:
            msg = str(sso_exc)
            if "未获取到 sso cookie" in msg or "sso cookie" in msg.lower():
                try:
                    from hybrid_register import burn_mailbox_to_pending
                    burn_mailbox_to_pending(
                        email,
                        str(profile.get("password") or ""),
                        reason="browser_sso_timeout_likely_registered",
                        log=wlog,
                    )
                    wlog(
                        f"[!] browser/mt no SSO after profile submit -> pending_sso "
                        f"email={email} detail={msg}"
                    )
                except Exception as pend_exc:
                    wlog(f"[!] pending_sso save fail email={email}: {pend_exc}")
                raise Exception(
                    f"pending_sso:browser_sso_timeout email={email} {msg}"
                )
            raise
        try:
            line = f"{email}----{profile.get('password','')}----{sso}\\n"
            with open(accounts_output_file, "a", encoding="utf-8") as f:
                f.write(line)
            wlog(f"[+] browser/mt saved account line email={email}")
        except Exception as file_exc:
            wlog(f"[Debug] 保存账号文件失败: {file_exc}")
        page = _get_page()
        schedule_post_registration(
            email,
            str(profile.get("password") or ""),
            sso,
            page=page,
            log_callback=wlog,
        )
'''

new_mt = '''        try:
            sso = wait_for_sso_cookie(
                log_callback=wlog, cancel_callback=controller.should_stop
            )
        except Exception as sso_exc:
            msg = str(sso_exc)
            if "未获取到 sso cookie" in msg or "sso cookie" in msg.lower():
                try:
                    from hybrid_register import burn_mailbox_to_pending
                    burn_mailbox_to_pending(
                        email,
                        str(profile.get("password") or ""),
                        reason="browser_sso_timeout_likely_registered",
                        log=wlog,
                    )
                    wlog(
                        f"[!] browser/mt no SSO after profile submit -> pending_sso "
                        f"email={email} detail={msg}"
                    )
                except Exception as pend_exc:
                    wlog(f"[!] pending_sso save fail email={email}: {pend_exc}")
                raise Exception(
                    f"pending_sso:browser_sso_timeout email={email} {msg}"
                )
            raise
        # 18r44c: hard reject reused session_id before disk/import
        ok_claim, sid, owner = claim_sso_session_or_reject(
            sso, email=email, log_callback=wlog
        )
        if not ok_claim:
            try:
                from hybrid_register import burn_mailbox_to_pending
                burn_mailbox_to_pending(
                    email,
                    str(profile.get("password") or ""),
                    reason="sso_session_collision",
                    log=wlog,
                    mail_token="",
                )
            except Exception as pend_exc:
                wlog(f"[!] collision pending save fail: {pend_exc}")
            try:
                _clear_xai_session_cookies(log_callback=wlog)
            except Exception:
                pass
            try:
                restart_browser(log_callback=wlog)
            except Exception as rb_exc:
                wlog(f"[!] collision restart_browser: {rb_exc}")
            raise Exception(
                f"pending_sso:sso_session_collision email={email} "
                f"sid={(sid or '')[:13]} owner={owner}"
            )
        try:
            line = f"{email}----{profile.get('password','')}----{sso}\\n"
            with open(accounts_output_file, "a", encoding="utf-8") as f:
                f.write(line)
            wlog(f"[+] browser/mt saved account line email={email}")
        except Exception as file_exc:
            wlog(f"[Debug] 保存账号文件失败: {file_exc}")
        page = _get_page()
        schedule_post_registration(
            email,
            str(profile.get("password") or ""),
            sso,
            page=page,
            log_callback=wlog,
        )
'''

if "pending_sso:sso_session_collision email=" not in text:
    if old_mt not in text:
        # try without escaped newline in source file - the file has real newline in f-string
        old_mt2 = old_mt.replace("\\\\n", "\\n")
        new_mt2 = new_mt.replace("\\\\n", "\\n")
        if old_mt2 not in text:
            raise SystemExit("mt block not found")
        text = text.replace(old_mt2, new_mt2, 1)
    else:
        text = text.replace(old_mt, new_mt, 1)

# Worker: after success, clear + restart browser for next slot
old_w = '''                try:
                    _register_one_browser(wlog)
                    coord.record_success()
                    wlog("[+] 注册成功")
                except RegistrationCancelled:
'''
new_w = '''                try:
                    _register_one_browser(wlog)
                    coord.record_success()
                    wlog("[+] 注册成功")
                    # 18r44c: hard isolate next account in same worker
                    try:
                        _clear_xai_session_cookies(log_callback=wlog)
                    except Exception:
                        pass
                    try:
                        restart_browser(log_callback=wlog)
                        wlog("[*] post-success browser restart for SSO isolation")
                    except Exception as rb_exc:
                        wlog(f"[!] post-success restart_browser: {rb_exc}")
                except RegistrationCancelled:
'''
if "post-success browser restart for SSO isolation" not in text:
    if old_w not in text:
        raise SystemExit("worker success block not found")
    text = text.replace(old_w, new_w, 1)

# Also gate serial GUI path (class method) - claim before write
old_gui = '''                    self.results.append({"email": email, "sso": sso, "profile": profile})
                    try:
                        line = f"{email}----{profile.get('password','')}----{sso}\\n"
                        with open(self.accounts_output_file, "a", encoding="utf-8") as f:
                            f.write(line)
                    except Exception as file_exc:
                        self.log(f"[Debug] 保存账号文件失败: {file_exc}")
                    # NSFW / g2a / CPA：默认后台，不阻塞下一号（功能仍执行）
                    schedule_post_registration(
'''
new_gui = '''                    ok_claim, sid, owner = claim_sso_session_or_reject(
                        sso, email=email, log_callback=self.log
                    )
                    if not ok_claim:
                        try:
                            from hybrid_register import burn_mailbox_to_pending
                            burn_mailbox_to_pending(
                                email,
                                str(profile.get("password") or ""),
                                reason="sso_session_collision",
                                log=self.log,
                            )
                        except Exception as pend_exc:
                            self.log(f"[!] collision pending save fail: {pend_exc}")
                        try:
                            _clear_xai_session_cookies(log_callback=self.log)
                            restart_browser(log_callback=self.log)
                        except Exception:
                            pass
                        raise Exception(
                            f"pending_sso:sso_session_collision email={email} "
                            f"sid={(sid or '')[:13]} owner={owner}"
                        )
                    self.results.append({"email": email, "sso": sso, "profile": profile})
                    try:
                        line = f"{email}----{profile.get('password','')}----{sso}\\n"
                        with open(self.accounts_output_file, "a", encoding="utf-8") as f:
                            f.write(line)
                    except Exception as file_exc:
                        self.log(f"[Debug] 保存账号文件失败: {file_exc}")
                    # NSFW / g2a / CPA：默认后台，不阻塞下一号（功能仍执行）
                    schedule_post_registration(
'''
if "self.results.append" in text and "ok_claim, sid, owner = claim_sso_session_or_reject" not in text.split("self.results.append")[0][-200:]:
    old_gui2 = old_gui.replace("\\\\n", "\\n")
    new_gui2 = new_gui.replace("\\\\n", "\\n")
    if old_gui2 in text:
        text = text.replace(old_gui2, new_gui2, 1)
    else:
        print("WARN: GUI block not found exact, skip")

# wait_for_sso: also reject baseline by session_id + previously claimed
# find baseline_sso = set(_collect_sso_cookie_values
old_base = '''    # 18r44a: ignore SSO cookies already present when wait starts (same-worker reuse)
    baseline_sso = set()
    try:
        baseline_sso = set(_collect_sso_cookie_values(_get_page()))
    except Exception:
        baseline_sso = set()
    if baseline_sso and log_callback:
        try:
            log_callback(
                f"[*] wait_for_sso: ignore baseline sso cookies n={len(baseline_sso)} "
                f"(prevent same-worker account collision)"
            )
        except Exception:
            pass
'''
new_base = '''    # 18r44a/c: ignore SSO cookies already present + already-claimed session_ids
    baseline_sso = set()
    baseline_sids = set()
    try:
        baseline_sso = set(_collect_sso_cookie_values(_get_page()))
        for _bv in list(baseline_sso):
            _bs = _extract_sso_session_id(_bv)
            if _bs:
                baseline_sids.add(_bs)
    except Exception:
        baseline_sso = set()
        baseline_sids = set()
    try:
        with _SSO_SESSION_CLAIM_LOCK:
            baseline_sids |= set(_SSO_SESSION_CLAIMS.keys())
    except Exception:
        pass
    if (baseline_sso or baseline_sids) and log_callback:
        try:
            log_callback(
                f"[*] wait_for_sso: ignore baseline sso cookies n={len(baseline_sso)} "
                f"sids={len(baseline_sids)} (prevent same-worker account collision)"
            )
        except Exception:
            pass
'''
if "baseline_sids" not in text:
    if old_base not in text:
        raise SystemExit("baseline block missing")
    text = text.replace(old_base, new_base, 1)

# reject when value's session_id in baseline_sids
# find: if value in baseline_sso or norm in baseline_sso:
old_rej = '''                    if value in baseline_sso or norm in baseline_sso:
'''
# Need more context - read file after first patches
if "baseline_sids" in text and "sid_full in baseline_sids" not in text:
    # expand rejection
    needle = "if value in baseline_sso or norm in baseline_sso:"
    idx = text.find(needle)
    if idx < 0:
        raise SystemExit("baseline reject if not found")
    # find the if block start - replace condition only
    text = text.replace(
        needle,
        "if value in baseline_sso or norm in baseline_sso or (_extract_sso_session_id(value) in baseline_sids if baseline_sids else False):",
        1,
    )

if text == orig:
    print("NO CHANGES")
    sys.exit(1)

path.write_text(text, encoding="utf-8")
print("patched", path)
print("len delta", len(text) - len(orig))
# sanity compile
import py_compile
py_compile.compile(str(path), doraise=True)
print("compile ok")
