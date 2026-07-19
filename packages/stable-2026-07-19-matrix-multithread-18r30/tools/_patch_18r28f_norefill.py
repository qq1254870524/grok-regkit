from pathlib import Path
import ast

p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")

old = '''                    # Allow re-fill only after quiet window + 10s since last refill, max 3.
                    # 18r28: if page looks idle on sign-in, solve Turnstile then submit (has_cf may be false-negative).
                    # 18r28e: after auth_error single retry, never click 登录 again — exit to reregister
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
                    if can_refill:
                        try:
                            st = page.run_js(wait_inputs_js) or {}
                        except Exception:
                            st = {}
                        if isinstance(st, dict) and st.get("ready"):
                            refill_tries += 1
                            last_refill_ts = now
                            post_submit_quiet_until = now + 14.0
                            try:
                                log(f"[pending-sso] re-fill path try={refill_tries}: solve turnstile first")
                                ts_rf = _ensure_signin_turnstile(
                                    page,
                                    browser,
                                    log,
                                    stop,
                                    reason=f"refill-{refill_tries}",
                                    timeout=70.0,
                                    force_fresh=True,
                                )
                                fill_state = page.run_js(fill_js, email, password) or {}
                                log(f"[pending-sso] re-fill/sign-in try={refill_tries} after_wait {fill_state} turnstile_ok={ts_rf.get('ok')} token_len={ts_rf.get('token_len')}")
                                # fill_js clicks once; reinject token (click may race widget) and submit again.
                                try:
                                    tok2 = ""
                                    try:
                                        tok2 = _read_page_turnstile_token(page)
                                    except Exception:
                                        tok2 = ""
                                    if len(tok2) >= 80:
                                        _inject_turnstile_token(page, tok2)
                                except Exception:
                                    pass
                                try:
                                    boost_rf = _click_signin_submit(page)
                                    log(f"[pending-sso] re-fill submit boost={boost_rf}")
                                except Exception as b_exc:
                                    log(f"[pending-sso] re-fill submit boost fail: {b_exc}")
                                submit_ts = now
                            except Exception as refill_exc:
                                log(f"[pending-sso] re-fill fail: {refill_exc}")
                            sleep_with_cancel(2.0, stop)
                            continue
'''

# The file may have mojibake for 登录 - read exact bytes of that section
idx = t.find("Allow re-fill only after quiet window")
print("idx", idx)
if idx < 0:
    raise SystemExit("anchor missing")
# print exact snippet around can_refill
print(repr(t[idx:idx+200]))

# Find from "Allow re-fill" through "continue\n" before long-wait soft probe
end = t.find("DO NOT jump to grok while still stuck on sign-in", idx)
if end < 0:
    raise SystemExit("end anchor missing")
# back up to start of line with Allow
start = t.rfind("\n", 0, idx) + 1
chunk = t[start:end]
print("CHUNK LEN", len(chunk))

new = '''                    # 18r28f: NEVER re-click 登录 after the first Turnstile-backed submit.
                    # Idle sign-in without SSO = credential/session fail -> hybrid re-register.
                    # (Old re-fill path caused: login fail then login again then login again.)
                    if (now - submit_ts) >= 10.0 and not sso and not is_loading:
                        # If CF challenge UI is actively up without token, solve once then ONE submit only when never submitted? 
                        # First submit already happened; do not login again.
                        log(
                            f"[pending-sso] still on sign-in after first submit "
                            f"elapsed={now-submit_ts:.1f}s cf={cf_seen} -> IMMEDIATE re-register "
                            f"(NO re-fill login) email={email}"
                        )
                        return result(
                            STATUS_FAIL,
                            email=email,
                            detail="sign-in stuck after first submit -> re-register",
                            remove_pending=True,
                            fail_reason="auth_error",
                        )
'''

t2 = t[:start] + new + t[end:]
# update docstring line about 18r28f
if "NO re-fill login" not in t2[:1200]:
    t2 = t2.replace(
        "18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click);",
        "18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click / NO re-fill login);",
        1,
    )
p.write_text(t2, encoding="utf-8")
ast.parse(p.read_text(encoding="utf-8"))
assert "re-fill path try=" not in p.read_text(encoding="utf-8")
assert "NO re-fill login" in p.read_text(encoding="utf-8")
print("patched OK")
