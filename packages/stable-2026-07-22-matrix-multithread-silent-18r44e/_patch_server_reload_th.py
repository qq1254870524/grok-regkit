from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\web\server.py")
t = p.read_text(encoding="utf-8")
marker = "Prefer freshly loaded path helpers when modules were patched mid-process."
i = t.find(marker)
if i < 0:
    raise SystemExit("marker missing")
j = t.find("for _mod_name in (", i)
k = t.find("):", j)
block = t[j : k + 2]
print("OLD BLOCK:\n" + block)
if "browser.token_harvester" in block:
    print("already ok")
else:
    new_block = block.replace(
        '"worker_coord",\n                    "grok_register_ttk",',
        '"worker_coord",\n                    "browser.token_harvester",\n                    "grok_register_ttk",',
    )
    if new_block == block:
        raise SystemExit("replace failed")
    t = t[:j] + new_block + t[k + 2 :]
    old_hdr = "18r43: /api/status exposes awaiting_pool"
    new_hdr = "18r43c: register job also reloads browser.token_harvester; 18r43: /api/status exposes awaiting_pool"
    if old_hdr in t[:900]:
        t = t.replace(old_hdr, new_hdr, 1)
    p.write_text(t, encoding="utf-8")
    print("PATCHED")
# verify
t2 = p.read_text(encoding="utf-8")
i2 = t2.find(marker)
j2 = t2.find("for _mod_name in (", i2)
k2 = t2.find("):", j2)
print("NEW BLOCK:\n" + t2[j2 : k2 + 2])
