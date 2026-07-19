from pathlib import Path
import ast, json
# verify function compiles by import
import sys
sys.path.insert(0, ".")
import pending_sso_recovery as ps
import importlib
importlib.reload(ps)
print("import pending OK", ps.__doc__[:80].replace("\n"," "))

# reorder pending: outlook with cache first
p = Path("accounts_registered_pending_sso.txt")
lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
cache = json.loads(Path("outlook_token_cache.json").read_text(encoding="utf-8"))
ck = {k.lower() for k in cache}
with_c, without = [], []
for ln in lines:
    em = ln.split("----")[0].strip().lower()
    (with_c if em in ck else without).append(ln)
# backup
bak = Path("accounts_registered_pending_sso.txt.bak_18r28d")
bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
ordered = with_c + without
p.write_text("\n".join(ordered) + "\n", encoding="utf-8")
print("reordered pending cache_first", len(with_c), "nocache", len(without))
print("head:")
for ln in ordered[:8]:
    em = ln.split("----")[0]
    print(" ", em, "CACHE" if em.lower() in ck else "no")
