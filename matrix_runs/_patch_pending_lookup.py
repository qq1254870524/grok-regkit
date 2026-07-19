from pathlib import Path
import re, ast, json

# 1) pending: lookup mail_token before forced re-register
p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
if "18r28d:" not in t[:800]:
    t = t.replace('"""\n18r28c:', '"""\n18r28d: force_fresh Turnstile + pre-rereg mail_token lookup from outlook cache\n18r28c:', 1)

old = '''                            forced_mail_token = str(item.get("mail_token") or "").strip()
                            forced_xai_password = str(password or "").strip()
                            log(
                                f"[pending-sso] re-register forced_email={email} "
                                f"mail_token_len={len(forced_mail_token)} "
                                f"xai_password_len={len(forced_xai_password)} "
                                f"note={str(item.get('note') or '')}"
                            )
                            rr = register_one_hybrid(
'''
new = '''                            forced_mail_token = str(item.get("mail_token") or "").strip()
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
                            if not forced_mail_token:
                                log(
                                    f"[pending-sso] skip forced re-register missing mail_token "
                                    f"email={email} (kept in pending; no IMAP/Graph creds)"
                                )
                                # rotate already done on auth_error path; count as fail without hybrid
                                rr = {
                                    "status": "fail",
                                    "ok": False,
                                    "email": email,
                                    "detail": "skip_reregister_no_mail_token",
                                }
                                rr = normalize_result(rr)
                                # jump past register_one_hybrid by using a sentinel handled below
                            if forced_mail_token:
                                log(
                                f"[pending-sso] re-register forced_email={email} "
                                f"mail_token_len={len(forced_mail_token)} "
                                f"xai_password_len={len(forced_xai_password)} "
                                f"note={str(item.get('note') or '')}"
                            )
                            if forced_mail_token:
                              rr = register_one_hybrid(
'''
if old not in t:
    raise SystemExit('pending block not found')
t = t.replace(old, new, 1)
# The above may leave broken indent for register_one_hybrid call - need careful fix
# Read the result around that area after write and fix properly with a cleaner approach.

p.write_text(t, encoding='utf-8')
print('wrote draft')
# show area
lines = t.splitlines()
for i,l in enumerate(lines,1):
    if 'pre-rereg mail_token' in l or 'forced_mail_token = str(item' in l or 'register_one_hybrid' in l and 'forced' in ''.join(lines[max(0,i-15):i+5]):
        pass
idx = t.find('pre-rereg mail_token lookup')
print(t[idx-400:idx+900])
