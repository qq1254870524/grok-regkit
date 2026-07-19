# MATRIX_REPORT

## 18r29 single-thread 10x10

# Matrix 18r29 Single-Thread Stable Report

- generated: 2026-07-19T11:48:29
- rounds_per_register_cell: 10
- pending_rounds: 10
- job_timeout_s: 720
- out: `C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041`

## Per-cell

| cell | rounds | success | fail | pending | top_classes |
|------|--------|---------|------|---------|-------------|
| hybrid__direct__outlook | 10 | 10 | 0 | 0 | success:10 |
| hybrid__direct__aol | 10 | 10 | 0 | 0 | success:10 |
| hybrid__socks5_list__outlook | 10 | 9 | 1 | 1 | success:9, pending_sso:1 |
| hybrid__socks5_list__aol | 10 | 10 | 0 | 0 | success:10 |
| browser__direct__outlook | 10 | 7 | 3 | 0 | success:7, early_no_new_mail:3 |
| browser__direct__aol | 10 | 10 | 0 | 0 | success:10 |
| browser__socks5_list__outlook | 10 | 6 | 4 | 2 | success:6, sso_timeout:2, pending_sso:1, early_no_new_mail:1 |
| browser__socks5_list__aol | 10 | 8 | 2 | 0 | success:8, profile_fill_fail:1, unknown:1 |
| pending_sso_recovery__socks5_list | 10 | 9 | 1 | 0 | success:9, sso_timeout:1 |
| pending_sso_recovery__direct | 10 | 8 | 2 | 0 | success:8, email_login_fail:2 |

## Failure class totals

- `success`: 87
- `early_no_new_mail`: 4
- `sso_timeout`: 3
- `pending_sso`: 2
- `email_login_fail`: 2
- `profile_fill_fail`: 1
- `unknown`: 1

## Notes

- Logs under this directory are FULL plaintext (no SSO/password redaction) per 18r17.



## 18r29 live matrix summary

- `browser__direct__aol`: ok=10/10 classes={'success': 10}
- `browser__direct__outlook`: ok=7/10 classes={'success': 7, 'early_no_new_mail': 3}
- `browser__socks5_list__aol`: ok=8/10 classes={'profile_fill_fail': 1, 'success': 8, 'unknown': 1}
- `browser__socks5_list__outlook`: ok=6/10 classes={'success': 6, 'pending_sso': 1, 'early_no_new_mail': 1, 'sso_timeout': 2}
- `hybrid__direct__aol`: ok=10/10 classes={'success': 10}
- `hybrid__direct__outlook`: ok=10/10 classes={'success': 10}
- `hybrid__socks5_list__aol`: ok=10/10 classes={'success': 10}
- `hybrid__socks5_list__outlook`: ok=9/10 classes={'success': 9, 'pending_sso': 1}
- `pending_sso_recovery__direct`: ok=8/10 classes={'success': 8, 'email_login_fail': 2}
- `pending_sso_recovery__socks5_list`: ok=9/10 classes={'success': 9, 'sso_timeout': 1}

- summary_rows=104 global_classes={'success': 87, 'empty_log': 3, 'pending_sso': 2, 'early_no_new_mail': 4, 'runner_exception': 1, 'sso_timeout': 3, 'profile_fill_fail': 1, 'unknown': 1, 'email_login_fail': 2}
- marked=2026-07-19T11:49:15
