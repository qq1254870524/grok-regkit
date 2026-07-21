from pathlib import Path
p = Path("web/server.py")
t = p.read_text(encoding="utf-8")
old = '''            for _mod_name in (
                "aol_mail",
                "outlook_mail",
                "browser.token_harvester",
                "hybrid_register",
                "pending_sso_recovery",
            ):'''
new = '''            for _mod_name in (
                "aol_mail",
                "outlook_mail",
                "grok_register_ttk",
                "browser.token_harvester",
                "hybrid_register",
                "pending_sso_recovery",
            ):'''
if old not in t:
    raise SystemExit("reload list not found")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("server reload list updated")

# hybrid changelog line
hp = Path("hybrid_register.py")
ht = hp.read_text(encoding="utf-8")
if "18r28f" not in ht[:2500]:
    # add near top changelog if exists
    if "Changelog" in ht[:1500] or "2026-07-19" in ht[:1500]:
        ht = ht.replace(
            '"""',
            '"""\n18r28f: code fetch uses grok_register_ttk.resolve_mailbox_provider (domain-first);\n'
            "  pending login fail skips second login click (pending_sso_recovery).\n",
            1,
        )
        hp.write_text(ht, encoding="utf-8")
        print("hybrid note added")
    else:
        print("hybrid no changelog slot")
else:
    print("hybrid already noted")
