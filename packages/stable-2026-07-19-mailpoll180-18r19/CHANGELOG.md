# grok-regkit 18r19 Package Notes

Tag: stable-2026-07-19-poll180-apiretry-18r19

## Fixes
1. **hybrid_register.py**: When CreateEmail `actual_send>=1` (dual-send lock active), mail poll uses **full 180s** instead of 45s short window. Short window only when protocol-rescue is still allowed. Fixes mass false `code_timeout_or_empty` pending after 18r16 dual-send lock.
2. **tools/matrix_cross_run.py**: API calls retry on WinError 10061 / URLError with backoff; empty logs classified as `empty_log`; OUT dir `matrix_18r19_*`.
3. **sso_to_auth_json.py** (carried): consent non-allow blacklist + deeper code parse (from working tree).
4. **browser/token_harvester.py** (carried): CreateEmail first-send-only dual-send lock refinements.

## Unchanged business rules
- Success -> delete from AOL/Outlook pool -> accounts_hybrid + immediate SSO pool
- Fail / code timeout / rate-limit -> delete pool -> accounts_registered_pending_sso.txt
- Rate-limit 验证码过多: burn + switch mailbox immediately
- Main path: register -> immediate SSO -> pool; pending only fallback
- Logs: full plaintext, no redaction
- Do not overwrite previous Packages/Releases

## Verify
- Log must show: `mail poll window ... poll_timeout=180s use_short=0 can_protocol_rescue=0 actual_send=1`
- Dual-send: `actual_send=1 blocked_dup=1`
