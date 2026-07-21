from pathlib import Path
import re
import py_compile

p = Path("hybrid_register.py")
text = p.read_text(encoding="utf-8")
if "claim_sso_session_or_reject" in text and "sso_session_collision burn fail" in text:
    print("already patched")
    raise SystemExit(0)

pat = re.compile(
    r'(return _result\(STATUS_PENDING_SSO, email=email, detail="token_not_session_sso"\))\s*\n\s*line = f"\{email\}----\{password\}----\{sso\}\\n"',
    re.M,
)
m = pat.search(text)
if not m:
    idx = text.find('detail="token_not_session_sso"')
    print("idx", idx)
    print(repr(text[idx:idx + 250]))
    raise SystemExit("pattern not found")

insert = """return _result(STATUS_PENDING_SSO, email=email, detail=\"token_not_session_sso\")
            # 18r44c: process-wide session_id claim before disk/pool
            try:
                from grok_register_ttk import claim_sso_session_or_reject
                ok_claim, sid, owner = claim_sso_session_or_reject(sso, email=email, log_callback=log)
                if not ok_claim:
                    try:
                        burn_mailbox_to_pending(
                            email,
                            password or \"PENDING_NO_PW\",
                            reason=\"sso_session_collision\",
                            log=log,
                            mail_token=mail_token,
                        )
                    except Exception as be:
                        log(f\"[hybrid] sso_session_collision burn fail: {be}\")
                    return _result(
                        STATUS_PENDING_SSO,
                        email=email,
                        detail=f\"sso_session_collision owner={owner} sid={(sid or '')[:13]}\",
                    )
            except Exception as claim_exc:
                log(f\"[hybrid] sso claim check fail (continue): {claim_exc}\")
            line = f\"{email}----{password}----{sso}\\n\""""

text2 = text[: m.start()] + insert + text[m.end() :]
if "18r44c" not in text2[:800]:
    text2 = "# 18r44c: claim SSO session_id before hybrid disk/pool; collision -> pending_sso\n" + text2
p.write_text(text2, encoding="utf-8")
py_compile.compile(str(p), doraise=True)
print("hybrid patched ok")
