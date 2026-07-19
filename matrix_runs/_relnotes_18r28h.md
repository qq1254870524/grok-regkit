## 18r28h pending ONE login only

### Fix
- Login fail no longer re-clicks login
- ONE login submit after Turnstile (removed boost double-click)
- CF stuck cannot skip 10s IMMEDIATE hybrid re-register
- Removed long-wait probe that navigated back to sign-in

### Live verified
- ONE login submit after turnstile
- login_submit_done=1 block_refill=1
- page_err=auth_error -> IMMEDIATE re-register (NO second login click)
- closed sign-in browser before hybrid re-register

### Package
packages/stable-2026-07-19-pending-one-login-18r28h.zip

Does not overwrite previous restore packages/releases.
