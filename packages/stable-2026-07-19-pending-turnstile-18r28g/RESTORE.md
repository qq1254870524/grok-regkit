# RESTORE 18r28g

Tag: stable-2026-07-19-pending-turnstile-18r28g
Commit: 68a604e

## Fixes
1. pending SSO login fail -> IMMEDIATE hybrid re-register (NO second login click / NO re-fill login)
2. CF-stuck after first submit: inject Turnstile only
3. Outlook mail route by domain/token even when configured provider=aol
4. Hot-reload grok_register_ttk + pending_sso_recovery

## Verified
- pending_sso_recovery count=2 success=2 fail=0
- auth_error -> re-register -> Graph code -> SignUp SSO session 152 -> g2a/Sub2API/CPA/NSFW

## Do not overwrite older packages
