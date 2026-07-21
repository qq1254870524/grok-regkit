# CHANGELOG 18r35 browser TLS hot-fix

## 2026-07-20 browser infinite open/close root cause

- Symptom: matrix entered `mode=browser` workers=10; Chrome processes spiked (~97) and windows flashed open/close.
- Root cause 1: full-browser multi-thread path always `restart_browser()` after every account (success or fail).
- Root cause 2: `fill_email_and_submit` / `fill_code_and_submit` / `fill_profile_and_submit` / `wait_cloudflare_passthrough` / `wait_for_sso_cookie` used module-global `page` instead of TLS `_get_page()`, so workers hit `NoneType.run_js` and page-disconnect storms.
- Fix in `grok_register_ttk.py`:
  - Resolve page via `_get_page()`/`refresh_active_page()` in those functions.
  - Catch page-disconnect / 页面被刷新 and soft-recover.
  - Browser multi-thread finally: hard restart only when browser/page dead; otherwise soft `open_signup_page`.
- Hybrid cells already completed (AOL strong). Browser cells re-run after fix.