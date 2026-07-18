# stable-2026-07-18-protocol-restore-18r12

Date: 2026-07-18

## Why
User reported protocol path broken from 18r10 onward; 18r9 still worked.

## Root cause
18r10 CreateEmail true-send lock short-circuited fetch/XHR with fake 200 Response after first request, and disabled whole form controls after click. That desynced browser SPA state from protocol VerifyEmail and collapsed SignUp / SSO reliability.

## Fix (18r12)
1. CreateEmail network hook restored to observe-only (r9 behavior): counters remain, no fake Response short-circuit.
2. UI form-wide disable after CreateEmail click removed; only logging flag kept.
3. UI click send-lock only skips after real 2xx CreateEmail (not inflight/status=0).
4. UI fallback email-page desync after protocol VerifyEmail aborts after 3 hits; sets last_ui_fallback_result.
5. pending_sso only when signup confirmed (UI profile submitted); otherwise accounts_signup_unconfirmed.txt + fail + keep mailbox.

## Verification
- py_compile hybrid_register.py + browser/token_harvester.py OK
- unittest 13 tests OK
- Real hybrid run count=1 SOCKS5 AOL:
  - CreateEmail browser OK status=200 net_hits=2
  - VerifyEmail 200
  - protocol SignUp status=200 sso_len=2477
  - session sso materialized len=152
  - success=1 fail=0 pending_sso=0
  - immediate SSO+pool path
- Only 8092 restarted; 8010/8080/8317/8318 kept running

## Do not overwrite
Previous packages kept intact:
- stable-2026-07-18-noreissue-18r9
- stable-2026-07-18-matrix-18r10
- stable-2026-07-18-cpa-consent-18r11
- stable-2026-07-18-pending-18r3
