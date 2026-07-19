from pathlib import Path
import ast

p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
start = t.find('forced_mail_token = str(item.get("mail_token") or "").strip()')
if start < 0:
    raise SystemExit("start not found")
# find end at next "rr = normalize_result(rr)" after register block - first occurrence after start that is followed by rr_status
end_marker = "rr = normalize_result(rr)\n                            rr_status = rr.get(\"status\")"
end = t.find(end_marker, start)
if end < 0:
    raise SystemExit("end not found")
end = end + len("rr = normalize_result(rr)\n")

new_block = '''forced_mail_token = str(item.get("mail_token") or "").strip()
                            forced_xai_password = str(password or "").strip()
                            if not forced_mail_token:
                                try:
                                    from hybrid_register import _lookup_mail_token_from_pool as _lt
                                    forced_mail_token = str(_lt(email, log=log) or "").strip()
                                    log(
                                        f"[pending-sso] pre-rereg mail_token lookup "
                                        f"email={email} len={len(forced_mail_token)}"
                                    )
                                except Exception as lkp_exc:
                                    log(f"[pending-sso] pre-rereg mail_token lookup fail: {lkp_exc}")
                                    forced_mail_token = ""
                            if not forced_mail_token:
                                log(
                                    f"[pending-sso] skip forced re-register missing mail_token "
                                    f"email={email} (kept in pending; no IMAP/Graph creds)"
                                )
                                rr = {
                                    "status": "fail",
                                    "ok": False,
                                    "email": email,
                                    "detail": "skip_reregister_no_mail_token",
                                }
                            else:
                                log(
                                    f"[pending-sso] re-register forced_email={email} "
                                    f"mail_token_len={len(forced_mail_token)} "
                                    f"xai_password_len={len(forced_xai_password)} "
                                    f"note={str(item.get('note') or '')}"
                                )
                                rr = register_one_hybrid(
                                    log=log,
                                    proxy=proxy,
                                    should_stop=controller.should_stop,
                                    accounts_file=re_accounts,
                                    post_success=True,
                                    forced_email=email,
                                    forced_mail_token=forced_mail_token,
                                    forced_xai_password=forced_xai_password,
                                )
                            rr = normalize_result(rr)
'''

t2 = t[:start] + new_block + t[end:]
# header note
if "pre-rereg mail_token lookup" not in t[:900]:
    t2 = t2.replace(
        '"""\n18r28d: force_fresh Turnstile',
        '"""\n18r28d: force_fresh Turnstile + pre-rereg mail_token from outlook_token_cache',
        1,
    )
p.write_text(t2, encoding="utf-8")
ast.parse(t2)
print("pending block rewritten AST OK")
print(t2[start:start+1200])
