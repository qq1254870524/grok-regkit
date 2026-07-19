from pathlib import Path
import re

t = Path("pending_sso_recovery.py").read_text(encoding="utf-8")
assert "inject-only" in t
assert "re-fill after cf turnstile" not in t
print("verify_ok")

hpath = Path("hybrid_register.py")
h = hpath.read_text(encoding="utf-8")
if "18r28g" not in h[:4000]:
    if "18r28f" in h[:4000]:
        h = h.replace("18r28f", "18r28g / 18r28f", 1)
        hpath.write_text(h, encoding="utf-8")
        print("hybrid_note_updated")
    else:
        print("hybrid_no_18r28f_marker")
else:
    print("hybrid_has_18r28g")

s = Path("web/server.py").read_text(encoding="utf-8")
for key in ["pending_sso_recovery", "grok_register_ttk", "hybrid_register"]:
    print(key, s.count(key))

# show reload list snippet
m = re.search(r"reload[^\n]{0,40}|RELOAD|hot.?reload|importlib\.reload", s, re.I)
print("reload_hit", bool(m), m.group(0) if m else None)
# find modules list near pending
idx = s.find("pending_sso_recovery")
print("snippet:")
print(s[max(0, idx - 200) : idx + 300] if idx >= 0 else "NOT FOUND")
