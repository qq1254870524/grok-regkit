from pathlib import Path

p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")

# header
hdr = (
    "18r28f: login fail -> IMMEDIATE hybrid re-register (NO second 登录 click);\n"
    "pair with grok_register_ttk resolve_mailbox_provider so Outlook code fetch not AOL.\n"
)
if "18r28f:" not in t[:900]:
    t = hdr + t

marker = 'if generic_auth and not locals().get("_auth_ts_retried"):'
idx = t.find(marker)
if idx < 0:
    raise SystemExit("generic_auth marker not found")

# Find start of comment block before generic_auth
start = t.rfind('                        # 18r28b: generic "An error occurred"', 0, idx)
if start < 0:
    start = t.rfind("if page_err in {\"bad_password\", \"account_missing\"}:", 0, idx)
    if start < 0:
        raise SystemExit("cannot find block start")
    # include hard-fail block from page_err in bad_password
else:
    # include from 18r28b through end of auth_error handling
    pass

# Better: replace from hard fail page_err through final auth_error returns
start2 = t.find('                        if page_err in {"bad_password", "account_missing"}:')
if start2 < 0:
    raise SystemExit("hard fail start not found")

# End: after the last `fail_reason=page_err` for plain auth_error before captcha
end_marker = '                        if page_err == "auth_error":\n                            log(f"[pending-sso] auth_error -> re-register email={email}")'
end = t.find(end_marker)
if end < 0:
    raise SystemExit("end marker not found")
# include the whole if page_err == auth_error block
end2 = t.find("fail_reason=page_err,\n                            )\n", end)
if end2 < 0:
    raise SystemExit("end2 not found")
end2 = end2 + len("fail_reason=page_err,\n                            )\n")

old = t[start2:end2]
print("OLD LEN", len(old))
print("OLD HEAD", old[:200].replace("\n"," | "))
print("OLD TAIL", old[-200:].replace("\n"," | "))

new = '''                        # 18r28f: ANY login page_err after first submit -> IMMEDIATE re-register.
                        # Do NOT click 登录 again (user: 登录失败改走注册，不要又重新登录).
                        # First login already solved Turnstile; second login only burns time / CF.
                        if page_err in {"bad_password", "account_missing", "auth_error", "need_reregister"}:
                            log(
                                f"[pending-sso] page_err={page_err} -> IMMEDIATE re-register "
                                f"(NO second login click) email={email} body={body[:240]}"
                            )
                            _block_login_refill = True
                            _auth_ts_retried = True
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=(
                                    page_err
                                    if page_err in {"bad_password", "account_missing"}
                                    else "auth_error"
                                ),
                            )
'''

t = t[:start2] + new + t[end2:]
p.write_text(t, encoding="utf-8")
print("pending_sso_recovery.py patched")

# sanity
t2 = p.read_text(encoding="utf-8")
assert "NO second login click" in t2
assert 'if generic_auth and not locals().get("_auth_ts_retried"):' not in t2
print("sanity OK, generic_auth retry removed")
