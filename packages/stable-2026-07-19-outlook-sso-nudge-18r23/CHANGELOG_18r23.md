# stable-2026-07-19-outlook-sso-nudge-18r23

Date: 2026-07-19 03:12:29

## Summary
Restore-point package 18r23 (does NOT overwrite 18r20/18r21/18r22).

## Changes
### 18r21
- Outlook early_no_new_mail: Graph 75s no post-send mail -> early burn/switch
- seen_new_after_send init fix

### 18r22
- hybrid VerifyEmail SOCKS5/proxy timeout retry (up to 3, 45/60/75s)

### 18r23
- Outlook strict post-send code window (since_ts-20s); baseline skip pre-send xAI codes
- Outlook form action `#`/empty -> urlPost/page URL (fix MissingSchema identity/confirm)
- browser success path calls mark_outlook_registered (prevent mailbox reuse + old code)

### 18r23b
- wait_for_sso_cookie: signing-in page nudge navigate grok.com/accounts.x.ai to mint SSO
- browser SSO timeout after profile submit -> pending_sso burn (not silent lose)

## Main path unchanged
register -> immediate SSO -> pool; pending only fallback.

## Matrix note
See matrix_runs/matrix_18r21_* summary for cross-run results.
