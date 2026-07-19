from pathlib import Path
p = Path("pending_sso_recovery.py")
text = p.read_text(encoding="utf-8")
old = """                        if ts_cf.get(\"ok\"):
                            # Re-fill credentials (CF widget may reset fields) then submit once.
                            try:
                                fill_state = page.run_js(fill_js, email, password) or {}
                                log(f\"[pending-sso] re-fill after cf turnstile: {fill_state}\")
                            except Exception as fr_exc:
                                log(f\"[pending-sso] re-fill after cf turnstile fail: {fr_exc}\")
                            try:
                                # fill_js already clicks; inject token again then extra submit.
                                _inject_turnstile_token(
                                    page,
                                    _read_page_turnstile_token(page),
                                )
                            except Exception:
                                pass
                            try:
                                boost2 = _click_signin_submit(page)
                                log(f\"[pending-sso] submit after cf turnstile: {boost2}\")
                            except Exception as sb_exc:
                                log(f\"[pending-sso] submit after cf turnstile fail: {sb_exc}\")
                            post_submit_quiet_until = time.time() + 12.0
                            submit_ts = time.time()"""
new = """                        if ts_cf.get(\"ok\"):
                            # 18r28g: after FIRST login submit, NEVER click login again.
                            # Only re-inject Turnstile token and wait for page auto-advance.
                            # If still stuck, outer 10s rule returns auth_error -> hybrid re-register.
                            try:
                                tok = _read_page_turnstile_token(page)
                                inj = _inject_turnstile_token(page, tok)
                                log(
                                    f\"[pending-sso] cf turnstile inject-only (no re-login click) \"
                                    f\"try={cf_solve_tries} tok_len={len(tok or '')} inj={inj}\"
                                )
                            except Exception as inj_exc:
                                log(f\"[pending-sso] cf turnstile inject-only fail: {inj_exc}\")
                            # Do not reset submit_ts; keep first-submit clock for IMMEDIATE re-register.
                            post_submit_quiet_until = time.time() + 8.0"""
if old not in text:
    print("OLD_BLOCK_NOT_FOUND")
    idx = text.find("re-fill after cf turnstile")
    print("idx", idx)
else:
    text2 = text.replace(old, new, 1)
    if "18r28g:" not in text2[:900]:
        text2 = text2.replace(
            "18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click / NO re-fill login);",
            "18r28g: CF-stuck after first submit = inject Turnstile ONLY (no re-login click);\n"
            "18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click / NO re-fill login);",
            1,
        )
    p.write_text(text2, encoding="utf-8")
    print("PATCHED_OK")
