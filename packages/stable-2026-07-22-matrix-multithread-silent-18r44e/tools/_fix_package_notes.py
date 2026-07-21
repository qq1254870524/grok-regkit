from pathlib import Path
p = Path("tools/package_18r43_silent.py")
t = p.read_text(encoding="utf-8-sig")
# fix broken notes block by rewriting the notes = [...] section via markers
start = t.find("    notes = [")
end = t.find("    (PKG / \"PACKAGE_NOTES.md\")")
if start < 0 or end < 0:
    raise SystemExit(f"markers missing {start} {end}")
new_notes = '''    notes = [
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
        "- 18r43b: dual_send_lock strict; freeze-reclick throttle; soft net_hits yield",
        "- 18r43c: register /api/start also reloads browser.token_harvester",
        "- 18r43d: post_success_workers=6 at cell config; early ensure; drain timeout scales with awaiting_pool depth",
        "- 18r43e: matrix resume/attach running job; supervisor auto-restart dead matrix; start skips if alive",
        "- 18r43f: Sub2API verify fail-fast permanent permission-denied; matrix verify_timeout=35 attempts=1",
        "- SSO vs mail_token import fix: reject mail_token as SSO; export importable session SSO only",
        "- silence edge_safe (never minimize/kill user Edge)",
        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",
        "- no overwrite of 18r40/18r41/18r42 packages",
        "",
        f"## Files count={len(copied)}",
        "",
    ]

'''
t2 = t[:start] + new_notes + t[end:]
p.write_text(t2, encoding="utf-8")
import ast
ast.parse(t2)
print("package script fixed")
