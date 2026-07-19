from pathlib import Path
import re, ast, importlib, json, sys
sys.dont_write_bytecode = True

p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
# fix cf-stuck call
old = '''ts_cf = _ensure_signin_turnstile(
                            page, browser, log, stop, reason=f"cf-stuck-{cf_solve_tries}", timeout=70.0
                        )'''
new = '''ts_cf = _ensure_signin_turnstile(
                            page, browser, log, stop, reason=f"cf-stuck-{cf_solve_tries}", timeout=70.0, force_fresh=True
                        )'''
if old in t:
    t = t.replace(old, new, 1)
    print("cf-stuck force_fresh OK")
else:
    # broader
    t2, n = re.subn(
        r'(_ensure_signin_turnstile\(\s*page,\s*browser,\s*log,\s*stop,\s*reason=f"cf-stuck-\{cf_solve_tries\}",\s*timeout=70\.0)(\s*\))',
        r'\1, force_fresh=True\2',
        t,
        count=1,
    )
    print("cf regex n", n)
    t = t2

# verify all ensure calls
for m in re.finditer(r'_ensure_signin_turnstile\([\s\S]{0,240}?\)', t):
    b = m.group(0)
    reason = "force_fresh" if "force_fresh" in b else "NO_FORCE"
    print(reason, "=>", " ".join(b.split())[:140])

p.write_text(t, encoding="utf-8")
ast.parse(t)
print("pending AST OK")

# smoke lookup
import hybrid_register as hr
importlib.reload(hr)
logs = []
tok = hr._lookup_mail_token_from_pool("eatonrempel@outlook.com", log=lambda m: logs.append(m))
print("tok_len", len(tok or ""))
for L in logs:
    print("L", L)
if tok and tok.strip().startswith("{"):
    d = json.loads(tok)
    print("rt_len", len(d.get("refresh_token") or ""), "cid", (d.get("client_id") or "")[:12])

# AOL random miss
logs2=[]
tok2 = hr._lookup_mail_token_from_pool("warstalkergulich@aol.com", log=lambda m: logs2.append(m))
print("aol tok_len", len(tok2 or ""), logs2[-3:])
