from pathlib import Path
p = Path("tools/package_18r43_silent.py")
lines = p.read_text(encoding="utf-8").splitlines()
start = end = None
for i, l in enumerate(lines):
    if l.strip() == "notes = [":
        start = i
    if start is not None and end is None and l.strip() == "]" and i > start:
        end = i
        break
if start is None or end is None:
    raise SystemExit(f"notes block missing {start} {end}")
new_notes = [
    "    notes = [",
    '        f"# {PKG_NAME}",',
    '        f"built={ts}",',
    '        "",',
    '        "## Highlights",',
    '        "- multi-thread silent stable matrix 18r43 (workers=20 preheat=40 count=1000)",',
    '        "- hybrid only + SOCKS5 outlook/aol x2 each",',
    '        "- pending_sso recovery SOCKS5 x2",',
    '        "- stop registration tests x2",',
    '        "- UI top metric: awaiting_pool with success/fail live",',
    '        "- 18r43a: mail_token never counts success; multi post-success workers default 6",',
    '        "- 18r43b: dual_send_lock strict; freeze-reclick throttle; soft net_hits yield",',
    '        "- SSO vs mail_token import fix: reject mail_token as SSO; export importable session SSO only",',
    '        "- silence edge_safe (never minimize/kill user Edge)",',
    '        "- /api/stop = stop Event + kill workers + clear pending (keep G2A/Sub2/CPA)",',
    '        "- no overwrite of 18r40/18r41/18r42 packages",',
    '        "",',
    '        f"## Files count={len(copied)}",',
    '        "",',
    "    ]",
]
lines = lines[:start] + new_notes + lines[end + 1 :]
text = "\n".join(lines) + "\n"
text = text.replace(
    "- silent multi-thread stable matrix 18r43 completed packaging",
    "- silent multi-thread stable matrix 18r43 (workers=20 preheat=40 count=1000)",
)
p.write_text(text, encoding="utf-8")
print("notes_ok", "awaiting_pool" in text)
