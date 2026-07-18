# stable-2026-07-19-pending-one-login-18r28h

## Fix
- pending SSO login fail must NOT re-login
- ONE login submit only (removed double click/boost)
- CF stuck cannot skip 10s IMMEDIATE hybrid re-register
- removed long-wait navigate back to sign-in

## Verified live keywords
- ONE login submit after turnstile
- login_submit_done=1 block_refill=1
- page_err=auth_error -> IMMEDIATE re-register (NO second login click)
- closed sign-in browser before hybrid re-register

## Main path unchanged
register -> immediate SSO -> pool; pending is fallback only.
