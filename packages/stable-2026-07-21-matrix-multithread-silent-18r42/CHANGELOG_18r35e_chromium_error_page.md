# CHANGELOG 18r35e — Chromium interstitial / stale page proxy-error detect

Date: 2026-07-20

## Problem
Matrix cell `browser__socks5_list__outlook` workers stuck ~minutes on open_signup:
- URL shows `https://accounts.x.ai/sign-up?...` but HTML is Chromium default error page
  (`title=accounts.x.ai`, `Copyright ... The Chromium Authors`, empty real app)
- Existing `page_has_proxy_error()` only matched classic proxy strings and used a
  **stale** `page` handle (checked before TLS page refresh) → always False
- `click_email_signup_button` then burned full 15s timeout hunting the button

## Fix
1. Expand `page_has_proxy_error` markers (ERR_*, Chromium interstitial, 无法访问此网站, etc.)
2. Detect title=host + Chromium Authors / main-frame-error / tiny body
3. open_signup: refresh TLS page **before** proxy-error check (always, not only when proxy mode)
4. click_email: early abort on error page instead of full timeout

## Notes
- Disk write only until current job ends; `_reload_8092_after_cell` restarts **only** 8092
- Does not change register→instant SSO main path
- Companion: 18r35c CreateEmail gate, 18r35d tos-gate + Outlook login direct fallback
