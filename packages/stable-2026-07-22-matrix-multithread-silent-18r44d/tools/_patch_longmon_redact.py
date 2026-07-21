import py_compile
p = r"C:\Users\zhang\grok-regkit\tools\_agent_longmon_18r43.py"
t = open(p, encoding="utf-8").read()
old = 'ev = (s.get("last_event") or "")[:160]'
new = '''ev = (s.get("last_event") or "")
    import re as _re
    ev = _re.sub(r"(?i)(?:socks5h?|https?)://\\S+", "***proxy***", ev)
    ev = _re.sub(r"(?i)(?:access_token|refresh_token|mail_token)=\\S+", "***token***", ev)
    ev = ev[:160]'''
if old not in t:
    raise SystemExit("old not found")
open(p, "w", encoding="utf-8").write(t.replace(old, new))
py_compile.compile(p, doraise=True)
print("ok")
