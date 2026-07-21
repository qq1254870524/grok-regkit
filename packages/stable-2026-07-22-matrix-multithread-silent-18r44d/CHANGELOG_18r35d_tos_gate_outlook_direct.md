# 18r35d — tos-gate escape + Outlook login direct fallback

## Why
- Multi-worker browser@socks5@outlook: after SSO success some workers reopen on `https://grok.com/tos-gate` and spin looking for 「使用邮箱注册」.
- Outlook `password+TOTP` / refresh through SOCKS hits `login.microsoftonline.com` timeouts/resets; Graph already falls back to direct, login did not.

## Fix
1. `grok_register_ttk.py`
   - `page_is_tos_gate` / `escape_tos_gate_to_signup`
   - `open_signup_page`: if URL/html is tos-gate → force `SIGNUP_URL`, clear storage; still gate → rotate proxy/restart browser
2. `outlook_mail.py` `ensure_tokens`
   - refresh/password+TOTP: proxy first; on proxy/network error → one **direct** retry
   - permanent auth failures still delete/burn as before (no silent keep)

## Load
Running web job keeps old modules in memory. After current matrix cell finishes, restart **only** `web/server.py` :8092 (do not kill 8010/8080/8317/8318).

## Note
Does not change main path: register → immediate SSO → pool. CreateEmail gate (18r35c) retained.
