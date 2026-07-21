from pathlib import Path
p = Path("hybrid_register.py")
t = p.read_text(encoding="utf-8")
old = """            _sso_ok = True
            try:
                from protocol.sso_util import is_mail_token_blob, is_session_sso, normalize_sso_token
                sso = normalize_sso_token(sso)
                if is_mail_token_blob(sso) or not is_session_sso(sso):
                    _sso_ok = False
                    log(f\"[!] refuse save non-session SSO email={email} sso_len={len(sso or '')}\")
            except Exception:
                pass
            if _sso_ok and sso:
                line = f\"{email}----{password}----{sso}\\n\"
                try:
                    with accounts_file.open(\"a\", encoding=\"utf-8\") as f:
                        f.write(line)
                except Exception as e:
                    log(f\"[hybrid] save file fail: {e}\")
            else:
                log(f\"[hybrid] skip accounts file write (no importable session SSO) email={email}\")



            log(f\"[hybrid][+] OK {email}\")
"""
new = """            _sso_ok = True
            try:
                from protocol.sso_util import is_mail_token_blob, is_session_sso, normalize_sso_token
                sso = normalize_sso_token(sso)
                if is_mail_token_blob(sso) or not is_session_sso(sso):
                    _sso_ok = False
                    log(f\"[!] refuse save non-session SSO email={email} sso_len={len(sso or '')}\")
            except Exception:
                pass
            # 18r43a: mail_token / non-session must NOT count as success or enter G2A/Sub2/CPA.
            # Burn back to pending_sso with mailbox token so secondary SSO recovery can re-run.
            if not (_sso_ok and sso):
                log(
                    f\"[hybrid] non-importable token -> pending_sso email={email} \"
                    f\"sso_len={len(sso or '')} (mail_token kept for recovery)\"
                )
                try:
                    burn_mailbox_to_pending(
                        email,
                        password or \"PENDING_NO_PW\",
                        reason=\"pending_sso:token_not_session_sso\",
                        log=log,
                        mail_token=mail_token,
                    )
                except Exception as be:
                    log(f\"[hybrid] token_not_session_sso burn fail: {be}\")
                return _result(STATUS_PENDING_SSO, email=email, detail=\"token_not_session_sso\")
            line = f\"{email}----{password}----{sso}\\n\"
            try:
                with accounts_file.open(\"a\", encoding=\"utf-8\") as f:
                    f.write(line)
            except Exception as e:
                log(f\"[hybrid] save file fail: {e}\")

            log(f\"[hybrid][+] OK {email}\")
"""
if old not in t:
    print("OLD NOT FOUND")
    i = t.find("_sso_ok = True")
    print(repr(t[i:i+750]))
else:
    t2 = t.replace(old, new, 1)
    if not t2.startswith("# 18r43a:"):
        t2 = "# 18r43a: non-session/mail_token never counts success or pool-import; burn pending_sso\n" + t2
    p.write_text(t2, encoding="utf-8")
    print("OK hybrid", len(t2) - len(t))
