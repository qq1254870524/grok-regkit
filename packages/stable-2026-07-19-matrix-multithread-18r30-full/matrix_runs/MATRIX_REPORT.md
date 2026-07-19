# MATRIX_REPORT

## 18r30 multi-thread (2026-07-19)

### Smoke 18r30b (post PageDisconnected fix)
- cell: hybrid x socks5_list x aol
- workers=2 count=2
- result: **success=2 fail=0 pending=0**
- notes: parallel [w1]/[w2]; immediate SSO path; post_process Sub2API account_id seen
- previous smoke2 before fix: success=1 fail=1 (w1 PageDisconnected on open_signup)

### Full matrix
- status: RUNNING in background (tools/matrix_18r30_multithread.py --rounds 10 --workers 2)
- cells: hybrid|browser x direct|socks5_list x aol|outlook + pending_sso_recovery
- tag target: stable-2026-07-19-matrix-multithread-18r30
- do-not-overwrite: stable-2026-07-19-matrix-singlethread-18r29

### Features verified
- Web workers UI + API
- SOCKS5 per-worker bind index (w-1)%n
- email preflight sample limit + AOL auth-only
- mail ALL folders top=5
- stop registration does not kill 8010/8080/8317/8318


---

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

## 18r30 full matrix results
finished=2026-07-19T12:38:33
summary_file=matrix_18r30_20260719_121329_summary.json
- `hybrid__socks5_list__aol` success=0 fail=0 pending=0 err=
- `pending_sso_recovery` success=None fail=None pending=None err=<urlopen error [WinError 10061] 由于目标计算机积极拒绝，无法连接。>

## 18r30 full matrix results
finished=2026-07-19T14:14:27
summary_file=matrix_18r30_20260719_123545_summary.json
- `hybrid__direct__aol` success=10 fail=0 pending=0 err=
- `hybrid__direct__outlook` success=7 fail=0 pending=3 err=
- `hybrid__socks5_list__aol` success=7 fail=0 pending=3 err=
- `hybrid__socks5_list__outlook` success=2 fail=0 pending=8 err=
- `browser__direct__aol` success=5 fail=5 pending=0 err=
- `browser__direct__outlook` success=3 fail=5 pending=0 err=
- `browser__socks5_list__aol` success=3 fail=6 pending=1 err=
- `browser__socks5_list__outlook` success=0 fail=10 pending=0 err=
- `pending_sso_recovery` success=0 fail=10 pending=None err=
