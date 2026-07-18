# Matrix 18r21 Report

- generated: 2026-07-19T04:45:28
- rounds_per_register_cell: 10
- pending_rounds: 10
- job_timeout_s: 720
- out: `C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411`

## Per-cell

| cell | rounds | success | fail | pending | top_classes |
|------|--------|---------|------|---------|-------------|
| hybrid__direct__outlook | 2 | 1 | 1 | 1 | success:1, pending_sso:1 |
| hybrid__direct__aol | 2 | 2 | 0 | 0 | success:2 |
| hybrid__socks5_list__outlook | 2 | 0 | 2 | 2 | pending_sso:2 |
| hybrid__socks5_list__aol | 2 | 2 | 0 | 0 | success:2 |
| browser__direct__outlook | 2 | 0 | 2 | 0 | early_no_new_mail:2 |
| browser__direct__aol | 2 | 1 | 1 | 0 | sso_timeout:1, success:1 |
| browser__socks5_list__outlook | 2 | 0 | 2 | 0 | early_no_new_mail:2 |
| browser__socks5_list__aol | 2 | 2 | 0 | 0 | success:2 |
| pending_sso_recovery__socks5_list | 2 | 1 | 1 | 0 | email_login_fail:1, success:1 |
| pending_sso_recovery__direct | 2 | 0 | 2 | 0 | sso_timeout:2 |

## Failure class totals

- `success`: 9
- `early_no_new_mail`: 4
- `pending_sso`: 3
- `sso_timeout`: 3
- `email_login_fail`: 1

## Notes

- Logs under this directory are FULL plaintext (no SSO/password redaction) per 18r17.

