from pathlib import Path
p = Path("tools/package_18r43_silent.py")
text = p.read_text(encoding="utf-8-sig")
# ensure name correct
text = text.replace("18r42", "18r43")
notes_old = '''    notes = [
        f"# {PKG_NAME}",
        f"built={ts}",
        "",
        "## Highlights",
        "- multi-thread silent matrix 18r43 (workers=20 preheat=40 count=1000)",
        "- hybrid + browser SOCKS5 outlook/aol x2 each",
        "- pending_sso recovery SOCKS5 x2",
        "- stop registration tests x2",
        "- SSO vs mail_token import fix (18r43d): reject mail_token as SSO; export importable session SSO only",
        "- silence edge_safe (never minimize/kill user Edge)",
        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",
        "",
        f"## Files count={len(copied)}",
        "",
    ]
'''
notes_new = '''    notes = [
        f"# {PKG_NAME}",
        f"built={ts}",
        "",
        "## Highlights",
        "- multi-thread silent stable matrix 18r43 (workers=20 preheat=40 count=1000)",
        "- hybrid only + SOCKS5 outlook/aol x2 each",
        "- pending_sso recovery SOCKS5 x2",
        "- stop registration tests x2",
        "- UI top metric: awaiting_pool with success/fail live",
        "- 18r43a: mail_token never counts success; multi post-success workers default 6",
        "- 18r43b: dual_send_lock strict; freeze-reclick throttle; soft net_hits yield to protocol-rescue",
        "- SSO vs mail_token import fix: reject mail_token as SSO; export importable session SSO only",
        "- silence edge_safe (never minimize/kill user Edge)",
        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",
        "- no overwrite of 18r40/18r41/18r42 packages",
        "",
        f"## Files count={len(copied)}",
        "",
    ]
'''
if notes_old in text:
    text = text.replace(notes_old, notes_new)
else:
    # try looser
    if "awaiting_pool" not in text:
        text = text.replace(
            "- SSO vs mail_token import fix (18r43d): reject mail_token as SSO; export importable session SSO only",
            "- UI top metric: awaiting_pool with success/fail live\n"
            "        - 18r43a: mail_token never counts success; multi post-success workers default 6\n"
            "        - 18r43b: dual_send_lock strict; freeze-reclick throttle\n"
            "        - SSO vs mail_token import fix: reject mail_token as SSO; export importable session SSO only",
        )
entry_old = '''    entry = (
        f"\\n## {PKG_NAME}\\n"
        f"- date: {ts}\\n"
        f"- silent multi-thread stable matrix 18r43 completed packaging\\n"
        f"- fix: pending_sso mail_token cannot import as SSO; export importable session SSO only\\n"
        f"- package: packages/{PKG_NAME}.zip (no overwrite of prior packages)\\n"
    )
'''
entry_new = '''    entry = (
        f"\\n## {PKG_NAME}\\n"
        f"- date: {ts}\\n"
        f"- silent multi-thread stable matrix 18r43 (workers=20 preheat=40 count=1000)\\n"
        f"- fix: dual_send_lock/freeze-reclick; multi post-success; mail_token never as SSO\\n"
        f"- UI: awaiting_pool live metric\\n"
        f"- package: packages/{PKG_NAME}.zip (no overwrite of prior packages)\\n"
    )
'''
if entry_old in text:
    text = text.replace(entry_old, entry_new)
p.write_text(text, encoding="utf-8")
print("PKG", [ln for ln in text.splitlines() if "PKG_NAME" in ln][0])
print("has_await", "awaiting_pool" in text)
