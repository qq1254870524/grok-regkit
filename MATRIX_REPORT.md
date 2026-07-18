
## 2026-07-19 18r28g pending no-second-login

- Tag/release/package: `stable-2026-07-19-pending-turnstile-18r28g` (non-overwrite)
- Commits: `68a604e` (fix) + `0b9c4a5` (packages)
- Fix: login `auth_error` after first Turnstile submit -> IMMEDIATE hybrid re-register; CF-stuck inject-only; Outlook route by domain even if configured=aol
- Run A pending count=2: success=2 fail=0 (touseysiagosto9, jodyceciliafnx) auth_error->reregister->Graph code->SignUp sso152->pool/CPA/NSFW
- Run B pending count=2 in progress after release (pensamorisem success path same; spaethkindtj started)


# MATRIX_REPORT

## 18r28h 2026-07-19 05:52:37
- Fix: login-fail must not re-login (double submit boost + CF continue skip + long-wait back to sign-in).
- ONE login submit; CF inject-only x1 then IMMEDIATE hybrid re-register at >=10s.
- Live matrix pending recovery next.

## 18r28h live matrix 2026-07-19 05:57:51
### pending_sso recovery count=2 SOCKS5 Outlook
1. juliostangoc@outlook.com
   - ONE login submit after turnstile
   - page_err=auth_error -> IMMEDIATE re-register (NO second login click)
   - closed sign-in browser before hybrid re-register
   - re-register -> early_no_new_mail (mailbox dead) -> kept pending
2. iveansowparejasir@outlook.com
   - ONE login submit after turnstile
   - page_err=auth_error -> IMMEDIATE re-register (NO second login click)
   - no submit boost / no second login
   - hybrid re-register in progress at snapshot time

### Git
- commit 3dfe749
- package/release stable-2026-07-19-pending-one-login-18r28h (non-overwrite)
