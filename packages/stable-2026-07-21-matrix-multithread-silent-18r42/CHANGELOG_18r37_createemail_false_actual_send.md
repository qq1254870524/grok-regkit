# 18r37 CreateEmail false actual_send / early_no_new_mail

Date: 2026-07-20

## Symptom
- CreateEmail `reason=seen_status_unknown` `status=0` `ok=False` `sent=False`
- `net_hits=1` inflated to `actual_send=1`
- promote `browser_sent` then lock protocol-rescue
- 180s empty poll -> `early_no_new_mail`

## Fix
- backfill actual_send only on 2xx
- browser_sent / dual_send_lock only on confirmed signals
- weak unknown: wait-confirm; no promote; rescue eligible
- live job not stopped; next process import picks up disk fix

## Files
- hybrid_register.py
- browser/token_harvester.py
