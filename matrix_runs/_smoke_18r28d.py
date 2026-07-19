import sys, ast, json, importlib, re
from pathlib import Path
sys.path.insert(0, r"C:\Users\zhang\grok-regkit")
sys.dont_write_bytecode = True
p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
for m in re.finditer(r"_ensure_signin_turnstile\([\s\S]{0,260}?\)", t):
    b = " ".join(m.group(0).split())
    if b.startswith("_ensure_signin_turnstile( page, browser, log:"):
        continue
    print(("FRESH" if "force_fresh=True" in b else "keep"), b[:200])

old = (
    'reason=f"refill-{refill_tries}",\n'
    "                                    timeout=70.0,\n"
    "                                )"
)
new = (
    'reason=f"refill-{refill_tries}",\n'
    "                                    timeout=70.0,\n"
    "                                    force_fresh=True,\n"
    "                                )"
)
if old in t:
    t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("fixed refill")
else:
    idx = t.find("refill-")
    print("refill ctx", repr(t[idx:idx+220]) if idx >= 0 else "no")

ast.parse(p.read_text(encoding="utf-8"))
print("pending ast ok")
import hybrid_register as hr
importlib.reload(hr)
logs = []
tok = hr._lookup_mail_token_from_pool("eatonrempel@outlook.com", log=lambda m: logs.append(m))
print("tok_len", len(tok or ""))
for L in logs:
    print("L", L)
if tok and str(tok).startswith("{"):
    d = json.loads(tok)
    print("rt", len(d.get("refresh_token") or ""))
logs2 = []
tok2 = hr._lookup_mail_token_from_pool("warstalkergulich@aol.com", log=lambda m: logs2.append(m))
print("aol", len(tok2 or ""), logs2[-2:])
