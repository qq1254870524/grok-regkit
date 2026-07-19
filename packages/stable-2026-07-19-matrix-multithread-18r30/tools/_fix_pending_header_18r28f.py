from pathlib import Path
import ast

p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
lines = t.splitlines(True)

start_idx = None
for i, l in enumerate(lines):
    if l.strip() == '"""' and i < 5:
        start_idx = i + 1
        break
if start_idx is None:
    raise SystemExit("no docstring start")

end_idx = None
for i in range(start_idx, min(len(lines), 80)):
    if lines[i].strip() == '"""':
        end_idx = i
        break
print("doc body", start_idx, end_idx)
body_after = "".join(lines[end_idx + 1 :]) if end_idx is not None else "".join(lines[start_idx:])

new_doc = '''"""
Pending SSO recovery helpers for grok-regkit hybrid.

18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click);
  pair with grok_register_ttk.resolve_mailbox_provider so Outlook code fetch
  is not misrouted to AOL when UI email_provider=aol.
18r28e: fix sleep_with_cancel in _ensure_signin_turnstile; login fail after 1 Turnstile retry -> IMMEDIATE re-register (no more login clicks/refill);
  no-sso/sign-in stuck also fail_reason=need_reregister; outer always routes need_reregister/auth_error to hybrid.
18r28d: force_fresh Turnstile + pre-rereg mail_token from outlook_token_cache on refill/auth-error/cf-stuck (no stale already-passed short-circuit).
18r28c: reload hybrid_register before forced re-register; server hot-reload hybrid
18r28b: fill credentials WITHOUT auto-click login; one submit only after Turnstile OK; hybrid mail_token pool lookup
18r28: pending SSO sign-in MUST solve/inject Cloudflare Turnstile before login submit
and on CF stuck/re-fill; never blind re-click login while challenge pending.
18r24b: pending fail rotates account to end of accounts_registered_pending_sso.txt so count=1 matrix no longer stuck on same head row.
18r24: pending-sso sign-in prefers ?email=true deep-link; after 2 empty social-btn clicks force email form URL.
"""
'''
p.write_text(new_doc + body_after.lstrip("\n"), encoding="utf-8")
ast.parse(p.read_text(encoding="utf-8"))
print("syntax OK")
print(p.read_text(encoding="utf-8")[:700])
assert "NO second login click" in p.read_text(encoding="utf-8")
print("marker OK")
