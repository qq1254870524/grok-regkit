# 18r39 dual_send full-poll early_no_new

## Problem
When `dual_send_lock` is true, hybrid sets `poll_timeout=180` but Outlook `get_oai_code` still early-breaks at 110s (`early_no_new_mail`) if Graph never sees post-send mail. That cuts ~70s of the intended full wait and burns mailboxes that might still deliver code later.

Live job (pre-reload) also still runs pre-18r37 modules: false `actual_send` promote -> dual-send lock -> skip protocol-rescue -> early_no_new burn.

## Fix (disk; next process load)
1. `outlook_mail.get_oai_code(..., early_no_new_s=None)`
   - None -> 110 default
   - <=0 disables early break
2. `grok_register_ttk.get_oai_code` forwards `early_no_new_s` via kwargs to Outlook path
3. `hybrid_register` when `dual_send_lock` or not `can_protocol_rescue`:
   - `early_no_new = max(110, poll_timeout - 10)` (e.g. 170 for 180s)
   - short rescue window still uses 110 (usually irrelevant under 45s timeout)
4. no-mail burn log uses `password_len` instead of password plaintext

## Not applied live
Do not restart web/hybrid job for this while target job running. Effective on next job start / process import.

## Verify
- py_compile outlook_mail / grok_register_ttk / hybrid_register
