from pathlib import Path
import ast

# ========== hybrid_register.py ==========
hr = Path('hybrid_register.py')
text = hr.read_text(encoding='utf-8')

if '18r28e:' not in text.split('Changelog',1)[-1][:900]:
    text = text.replace(
        'Changelog:\n',
        'Changelog:\n'
        '- 18r28e: mailbox provider 按邮箱域名优先（outlook/* 不走 AOL preflight）；'
        'forced_email preflight 失败立即返回，不再同号空转 20 次；'
        '配合 pending 登录失败立刻改注册。\n',
        1,
    )

helper = '''
def _mailbox_provider_is_aol(email: str, configured_provider: str = "") -> bool:
    """Route mailbox by email domain first; global provider only for ambiguous domains.

    Bug 18r28d: when UI email source=AOL, forced Outlook re-register incorrectly called
    aol_mail.preflight -> "AOL missing password for xxx@outlook.com".
    """
    em = str(email or "").strip().lower()
    prov = str(configured_provider or "").strip().lower()
    aol_suffixes = (
        "@aol.com", "@aim.com", "@verizon.net", "@love.com",
        "@ygm.com", "@games.com", "@wow.com",
    )
    outlook_suffixes = (
        "@outlook.com", "@hotmail.com", "@live.com", "@msn.com",
        "@office365.com", "@outlook.jp", "@outlook.fr", "@hotmail.co.uk",
    )
    if em.endswith(aol_suffixes):
        return True
    if em.endswith(outlook_suffixes):
        return False
    try:
        import aol_mail as _am
        if _am.is_aol_provider(prov):
            return True
    except Exception:
        pass
    if prov in {"aol", "aol_mail", "aol.com", "aim", "verizon_aol"}:
        return True
    if prov in {"outlook", "microsoft", "hotmail", "graph", "ms", "outlook_mail"}:
        return False
    return False


'''

if 'def _mailbox_provider_is_aol(' not in text:
    anchor = 'def _lookup_mail_token_from_pool(email: str, log=None) -> str:'
    if anchor not in text:
        raise SystemExit('anchor _lookup_mail_token_from_pool missing')
    text = text.replace(anchor, helper + anchor, 1)

old_pre = '''                    prov = str(_gep() or "").strip().lower()
                    em_l = (email or "").lower()
                    is_aol = False
                    try:
                        import aol_mail as _am
                        is_aol = _am.is_aol_provider(prov) or em_l.endswith(("@aol.com", "@aim.com"))
                    except Exception:
                        is_aol = em_l.endswith(("@aol.com", "@aim.com"))
                    if is_aol:'''

new_pre = '''                    prov = str(_gep() or "").strip().lower()
                    em_l = (email or "").lower()
                    # 18r28e: domain-first; never route @outlook to AOL because global source=AOL
                    is_aol = _mailbox_provider_is_aol(email, prov)
                    log(
                        f"[hybrid] mailbox preflight route email={email} "
                        f"is_aol={int(is_aol)} configured_provider={prov or '-'}"
                    )
                    if is_aol:'''

if old_pre not in text:
    raise SystemExit('old preflight block not found')
text = text.replace(old_pre, new_pre, 1)

old_fail2 = '''                    em_l2 = (email or "").lower()
                    is_aol_fail = em_l2.endswith(("@aol.com", "@aim.com"))
                    category = 'unknown'
                    auth_path = 'unknown'
                    permanent = False'''
new_fail2 = '''                    em_l2 = (email or "").lower()
                    is_aol_fail = _mailbox_provider_is_aol(email, "")
                    category = 'unknown'
                    auth_path = 'unknown'
                    permanent = False'''
if old_fail2 not in text:
    raise SystemExit('old fail classify not found')
text = text.replace(old_fail2, new_fail2, 1)

marker = '''                    except Exception as rel_pre:
                        log(f"[hybrid] pre-login release email: {rel_pre}")
                    email, mail_token = "", ""
                    continue'''
if marker not in text:
    raise SystemExit('preflight continue marker missing')
replacement = '''                    except Exception as rel_pre:
                        log(f"[hybrid] pre-login release email: {rel_pre}")
                    # 18r28e: forced_email is a specific pending mailbox — do NOT spin 20 times
                    if force_em:
                        log(
                            f"[hybrid] forced_email preflight failed once email={email} "
                            f"category={category} — abort re-register (keep pending)"
                        )
                        return _result(
                            STATUS_FAIL,
                            email=email,
                            detail=f"forced_email_preflight_fail:{category}:{pre_exc}",
                        )
                    email, mail_token = "", ""
                    continue'''
text = text.replace(marker, replacement, 1)

hr.write_text(text, encoding='utf-8')
print('hybrid_register.py patched OK')

# ========== pending_sso_recovery.py ==========
ps = Path('pending_sso_recovery.py')
pt = ps.read_text(encoding='utf-8')

if '18r28e:' not in pt[:700]:
    pt = pt.replace(
        '18r28d: force_fresh Turnstile',
        '18r28e: login fail after 1 Turnstile retry -> IMMEDIATE re-register (no more login clicks/refill);\n'
        '  no-sso/sign-in stuck also fail_reason=need_reregister; outer always routes need_reregister/auth_error to hybrid.\n'
        '18r28d: force_fresh Turnstile',
        1,
    )

old_auth_block = '''                        if generic_auth and not locals().get("_auth_ts_retried"):
                            _auth_ts_retried = True
                            try:
                                log("[pending-sso] generic auth_error -> one fresh Turnstile retry before fail")
                                ts_r = _ensure_signin_turnstile(
                                    page, browser, log, stop, reason="auth-error-retry", timeout=70.0, force_fresh=True
                                )
                                try:
                                    fill_state2 = page.run_js(fill_js, email, password) or {}
                                    log(f"[pending-sso] auth-error-retry refill={fill_state2}")
                                except Exception as fe:
                                    log(f"[pending-sso] auth-error-retry refill fail: {fe}")
                                try:
                                    tok2 = _read_page_turnstile_token(page)
                                    if len(tok2) >= 80:
                                        _inject_turnstile_token(page, tok2)
                                except Exception:
                                    pass
                                click_r = _click_signin_submit(page)
                                log(
                                    f"[pending-sso] auth-error-retry submit turnstile_ok={ts_r.get('ok')} "
                                    f"token_len={ts_r.get('token_len')} click={click_r}"
                                )
                                submit_ts = time.time()
                                last_err = ""
                                page_err = ""
                                sleep_with_cancel(2.5, stop)
                                continue
                            except Exception as re_exc:
                                log(f"[pending-sso] auth-error-retry fail: {re_exc}")
                        if page_err in {"bad_password", "account_missing"}:
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )
                        if page_err == "auth_error" and locals().get("_auth_ts_retried"):
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )'''

new_auth_block = '''                        # 18r28e: at most ONE fresh-Turnstile login retry; then leave sign-in
                        # immediately for hybrid re-register. Never keep clicking 登录.
                        if page_err in {"bad_password", "account_missing"}:
                            log(
                                f"[pending-sso] hard fail page_err={page_err} -> re-register path "
                                f"(stop further login clicks) email={email}"
                            )
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )
                        if generic_auth and not locals().get("_auth_ts_retried"):
                            _auth_ts_retried = True
                            try:
                                log("[pending-sso] generic auth_error -> one fresh Turnstile retry ONLY, then reregister if still fail")
                                ts_r = _ensure_signin_turnstile(
                                    page, browser, log, stop, reason="auth-error-retry", timeout=70.0, force_fresh=True
                                )
                                if not ts_r.get("ok"):
                                    log(
                                        f"[pending-sso] auth-error-retry turnstile FAIL -> immediate re-register "
                                        f"email={email} detail={ts_r}"
                                    )
                                    return result(
                                        STATUS_FAIL,
                                        email=email,
                                        detail="sign-in page_err=auth_error turnstile_retry_failed",
                                        remove_pending=True,
                                        fail_reason="auth_error",
                                    )
                                try:
                                    fill_state2 = page.run_js(fill_js, email, password) or {}
                                    log(f"[pending-sso] auth-error-retry refill={fill_state2}")
                                except Exception as fe:
                                    log(f"[pending-sso] auth-error-retry refill fail: {fe}")
                                try:
                                    tok2 = _read_page_turnstile_token(page)
                                    if len(tok2) >= 80:
                                        _inject_turnstile_token(page, tok2)
                                except Exception:
                                    pass
                                click_r = _click_signin_submit(page)
                                log(
                                    f"[pending-sso] auth-error-retry submit turnstile_ok={ts_r.get('ok')} "
                                    f"token_len={ts_r.get('token_len')} click={click_r}"
                                )
                                submit_ts = time.time()
                                _auth_retry_submitted = True
                                last_err = ""
                                page_err = ""
                                sleep_with_cancel(3.0, stop)
                                try:
                                    pst2 = page.run_js(page_state_js) or {}
                                except Exception:
                                    pst2 = {}
                                body2 = str((pst2 or {}).get("body") or "")
                                err2 = str((pst2 or {}).get("err") or "").strip()
                                body2l = body2.lower()
                                if (not err2) and (
                                    "an error occurred" in body2l
                                    or "something went wrong" in body2l
                                    or "无法登录" in body2
                                    or "登录失败" in body2
                                    or "出错了" in body2
                                    or "错误的邮箱" in body2
                                    or "incorrect" in body2l
                                    or "invalid password" in body2l
                                    or "wrong password" in body2l
                                ):
                                    err2 = "auth_error"
                                if (
                                    "密码" in body2 and ("错误" in body2 or "不正确" in body2)
                                ) or "错误的邮箱地址或密码" in body2:
                                    err2 = "bad_password"
                                if err2 in {"auth_error", "bad_password", "account_missing"}:
                                    log(
                                        f"[pending-sso] after single Turnstile retry still page_err={err2} "
                                        f"-> IMMEDIATE re-register, no more login email={email} body={body2[:200]}"
                                    )
                                    return result(
                                        STATUS_FAIL,
                                        email=email,
                                        detail=f"sign-in page_err={err2} after_turnstile_retry",
                                        remove_pending=True,
                                        fail_reason=err2 if err2 != "auth_error" else "auth_error",
                                    )
                                _block_login_refill = True
                                continue
                            except Exception as re_exc:
                                log(f"[pending-sso] auth-error-retry fail: {re_exc} -> re-register")
                                return result(
                                    STATUS_FAIL,
                                    email=email,
                                    detail=f"sign-in page_err=auth_error retry_exc={re_exc}",
                                    remove_pending=True,
                                    fail_reason="auth_error",
                                )
                        if page_err == "auth_error" and (
                            locals().get("_auth_ts_retried") or locals().get("_auth_retry_submitted")
                        ):
                            log(
                                f"[pending-sso] auth_error after retry exhausted -> re-register "
                                f"email={email} (no further login)"
                            )
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )
                        if page_err == "auth_error":
                            log(f"[pending-sso] auth_error -> re-register email={email}")
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )'''

if old_auth_block not in pt:
    raise SystemExit('old auth block not found in pending')
pt = pt.replace(old_auth_block, new_auth_block, 1)

old_can = '''                    can_refill = (
                        refill_tries < 3
                        and (now - last_refill_ts) >= 10.0
                        and (now - submit_ts) >= 12.0
                        and (not is_loading)
                    )
                    if can_refill:'''
new_can = '''                    # 18r28e: after auth_error single retry, never click 登录 again — exit to reregister
                    if locals().get("_block_login_refill") or locals().get("_auth_ts_retried"):
                        if (now - submit_ts) >= 8.0 and not sso:
                            log(
                                f"[pending-sso] login retry budget exhausted / block_refill "
                                f"elapsed={now-submit_ts:.1f}s -> re-register email={email}"
                            )
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail="sign-in page_err=auth_error no_sso_after_retry",
                                remove_pending=True,
                                fail_reason="auth_error",
                            )
                    can_refill = (
                        refill_tries < 3
                        and (now - last_refill_ts) >= 10.0
                        and (now - submit_ts) >= 12.0
                        and (not is_loading)
                        and (not locals().get("_block_login_refill"))
                        and (not locals().get("_auth_ts_retried"))
                    )
                    if can_refill:'''
if old_can not in pt:
    raise SystemExit('can_refill block not found')
pt = pt.replace(old_can, new_can, 1)

old_nosso = '''                log(f"[pending-sso] no sso after sign-in email={email} last_fill={fill_state} last_page={pst}")
                return result(STATUS_FAIL, email=email, detail=f"no sso after sign-in page={pst}")'''
new_nosso = '''                log(f"[pending-sso] no sso after sign-in email={email} last_fill={fill_state} last_page={pst}")
                # 18r28e: login could not mint SSO -> outer must re-register, not only rotate pending
                fr = "auth_error"
                try:
                    body_n = str((pst or {}).get("body") or "")
                    err_n = str((pst or {}).get("err") or "")
                    if err_n in {"bad_password", "account_missing"}:
                        fr = err_n
                    elif "错误的邮箱地址或密码" in body_n or (
                        "密码" in body_n and ("错误" in body_n or "不正确" in body_n)
                    ):
                        fr = "bad_password"
                except Exception:
                    pass
                return result(
                    STATUS_FAIL,
                    email=email,
                    detail=f"no sso after sign-in page={pst}",
                    remove_pending=True,
                    fail_reason=fr,
                )'''
if old_nosso not in pt:
    raise SystemExit('no sso return not found')
pt = pt.replace(old_nosso, new_nosso, 1)

old_outer = '''            if not fail_reason:
                low = detail.lower()
                if "bad_password" in low or "page_err=bad_password" in low:
                    fail_reason = "bad_password"
                elif "account_missing" in low or "page_err=account_missing" in low:
                    fail_reason = "account_missing"
                elif "auth_error" in low or "page_err=auth_error" in low or "an error occurred" in low:
                    fail_reason = "auth_error"
            if controller.should_stop() or status == STATUS_STOPPED:
                log("[*] 当前 pending 恢复因停止请求中断，统计保持不变")
                break
            if status == STATUS_SUCCESS:
                success_count += 1
            else:
                fail_count += 1
                # 18r24b: always rotate failed head to end so next round / count=1 is not stuck.
                try:
                    rotate_pending_sso_account_to_end(email, log=log)
                except Exception as rot_exc:
                    log(f"[pending] rotate after fail error: {rot_exc}")
                # 密码错误/账号不存在/auth_error：走 hybrid 重注册。
                # 关键：accounts_registered_pending_sso 仅在最终成功后才移出；
                # 若重注册失败仍保留原 pending，避免数据丢失。
                if fail_reason in {"bad_password", "account_missing", "auth_error"} or res.get("remove_pending"):'''

new_outer = '''            if not fail_reason:
                low = detail.lower()
                if "bad_password" in low or "page_err=bad_password" in low:
                    fail_reason = "bad_password"
                elif "account_missing" in low or "page_err=account_missing" in low:
                    fail_reason = "account_missing"
                elif (
                    "auth_error" in low
                    or "page_err=auth_error" in low
                    or "an error occurred" in low
                    or "no sso after sign-in" in low
                    or "turnstile_retry_failed" in low
                    or "after_turnstile_retry" in low
                ):
                    fail_reason = "auth_error"
            if controller.should_stop() or status == STATUS_STOPPED:
                log("[*] 当前 pending 恢复因停止请求中断，统计保持不变")
                break
            if status == STATUS_SUCCESS:
                success_count += 1
            else:
                fail_count += 1
                # 18r24b: always rotate failed head to end so next round / count=1 is not stuck.
                try:
                    rotate_pending_sso_account_to_end(email, log=log)
                except Exception as rot_exc:
                    log(f"[pending] rotate after fail error: {rot_exc}")
                # 18r28e: 登录失败（含 no-sso）一律改走 hybrid 重注册，禁止再回到登录死循环。
                # 关键：accounts_registered_pending_sso 仅在最终成功后才移出；
                # 若重注册失败仍保留原 pending，避免数据丢失。
                need_rereg = (
                    fail_reason in {"bad_password", "account_missing", "auth_error", "need_reregister"}
                    or res.get("remove_pending")
                    or ("no sso after sign-in" in detail.lower())
                    or ("sign-in page_err" in detail.lower())
                )
                if need_rereg:
                    if not fail_reason:
                        fail_reason = "auth_error"'''

if old_outer not in pt:
    raise SystemExit('outer fail block not found')
pt = pt.replace(old_outer, new_outer, 1)

old_rr_start = '''                            log(f"[pending-sso] re-register via hybrid start (reason={fail_reason or detail})")
                            re_accounts = Path(accounts_output_file)'''
new_rr_start = '''                            log(
                                f"[pending-sso] login failed -> STOP further sign-in; "
                                f"re-register via hybrid start (reason={fail_reason or detail}) email={email}"
                            )
                            # Close pending sign-in browser before hybrid opens a fresh signup session
                            try:
                                engine.stop_browser(log_callback=log)
                                log("[pending-sso] closed sign-in browser before hybrid re-register")
                            except Exception as sb_exc:
                                log(f"[pending-sso] stop sign-in browser before rereg: {sb_exc}")
                            re_accounts = Path(accounts_output_file)'''
if old_rr_start not in pt:
    raise SystemExit('rr start not found')
pt = pt.replace(old_rr_start, new_rr_start, 1)

ps.write_text(pt, encoding='utf-8')
print('pending_sso_recovery.py patched OK')

ast.parse(hr.read_text(encoding='utf-8'))
ast.parse(ps.read_text(encoding='utf-8'))
print('syntax OK')

ns = {}
exec(helper, ns)
fn = ns['_mailbox_provider_is_aol']
assert fn('a@outlook.com', 'aol') is False
assert fn('a@hotmail.com', 'aol') is False
assert fn('a@aol.com', 'outlook') is True
assert fn('a@aol.com', 'aol') is True
assert fn('weird@example.com', 'aol') is True
assert fn('weird@example.com', 'outlook') is False
print('domain router unit OK')
