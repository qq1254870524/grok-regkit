# Matrix 18r21 Report

- generated: 2026-07-19T03:33:43
- rounds_per_register_cell: 2
- pending_rounds: 2
- job_timeout_s: 720
- out: `C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216`

## Per-cell

| cell | rounds | success | fail | pending | top_classes |
|------|--------|---------|------|---------|-------------|
| hybrid__direct__outlook | 2 | 0 | 2 | 2 | pending_sso:2 |
| hybrid__direct__aol | 2 | 1 | 1 | 0 | empty_log:1, success:1 |
| hybrid__socks5_list__outlook | 2 | 0 | 2 | 2 | pending_sso:2 |
| hybrid__socks5_list__aol | 2 | 1 | 1 | 1 | pending_sso:1, success:1 |
| browser__direct__outlook | 2 | 1 | 1 | 0 | success:1, early_no_new_mail:1 |
| browser__direct__aol | 2 | 1 | 1 | 0 | success:1, email_login_fail:1 |
| browser__socks5_list__outlook | 2 | 2 | 0 | 0 | success:2 |
| browser__socks5_list__aol | 2 | 1 | 1 | 0 | success:1, email_login_fail:1 |
| pending_sso_recovery__socks5_list | 2 | 0 | 2 | 0 | email_login_fail:1, signup_no_sso:1 |
| pending_sso_recovery__direct | 2 | 0 | 2 | 0 | signup_no_sso:2 |

## Failure class totals

- `success`: 7
- `pending_sso`: 5
- `email_login_fail`: 3
- `signup_no_sso`: 3
- `empty_log`: 1
- `early_no_new_mail`: 1

## Notes

- Logs under this directory are FULL plaintext (no SSO/password redaction) per 18r17.

