# 18r36 pending dead-loop break

## 18r36a
- pending_sso per-email attempt cap (default 3) + exhausted archive `accounts_pending_sso_exhausted.txt`
- attempt counters: `matrix_runs/pending_sso_attempts.json`
- compact pending file to one best row per email
- hybrid pending save becomes upsert by email

## 18r36b
- never re-queue emails already in exhausted dead-letter
- skip/purge exhausted emails on recover paths

## Verification
- py_compile hybrid_register.py pending_sso_recovery.py OK
- live hybrid run uses upsert path without stopping service
