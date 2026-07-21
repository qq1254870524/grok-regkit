# 18r38 UI fallback reason=running + code page stuck

Date: 2026-07-20

## Symptom
- After code confirm, UI stays on verification page (`code=True`, often `cf=True`)
- prepare_profile aborts ~14s
- `last_ui_fallback_result.reason` left as initial `"running"`
- pending saved as `pending_sso:signup_unconfirmed:running` (misleading)

## Fix (disk; live job keeps old in-memory modules until process reload)
- prepare_profile: re-confirm every ~4s while stuck; wait 22s when CF present else 14s
- set `last_ui_fallback_result.reason=code_page_stuck` on stuck abort
- UI fallback cancel/hard-fail overwrite initial `running`
- hybrid: map leftover `running`/empty to `code_page_stuck` or `ui_incomplete`
- hybrid: no-sso classify logs no longer print password plaintext

## Files
- browser/token_harvester.py
- hybrid_register.py

## Note
- 18r37 CreateEmail false actual_send fix remains required for early_no_new_mail
- Neither 18r37 nor 18r38 applies to currently running web job until import/reload
