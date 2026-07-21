# Matrix 18r44 Silent Stable Report (full 12 cells)

- rewritten: 2026-07-22T03:11:30
- workers=2 preheat=4 count=4 rounds=2
- proxy: socks5; silent browser; pythonw parent
- fixes loaded during run: CPA prefer_direct, 18r44a SSO cookie isolation, 18r44b CreateEmail body_ok
- post-run fix: 18r44c process-wide session_id claim + post-success browser restart

## Results

| cell | r | ok | class | s | f | p | dg2a | dsub2 | t |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| hybrid__socks5__outlook | 1 | True | success | 2 | 0 | 2 | 2 | 2 | 335.0 |
| hybrid__socks5__outlook | 2 | True | success | 2 | 0 | 2 | 2 | 2 | 353.3 |
| hybrid__socks5__aol | 1 | True | success | 1 | 0 | 3 | 1 | 1 | 306.5 |
| hybrid__socks5__aol | 2 | True | success | 3 | 0 | 1 | 3 | 3 | 333.1 |
| browser__socks5__outlook | 1 | True | success | 4 | 0 | 0 | 4 | 4 | 558.2 |
| browser__socks5__outlook | 2 | True | success | 4 | 0 | 0 | 4 | 4 | 678.6 |
| browser__socks5__aol | 1 | True | success | 4 | 0 | 0 | 3 | 4 | 417.4 |
| browser__socks5__aol | 2 | True | pending_sso | 3 | 1 | 0 | 2 | 3 | 596.0 |
| pending_sso_recovery__socks5 | 1 | True | success | 1 | 0 | 0 | 1 | 1 | 405.6 |
| pending_sso_recovery__socks5 | 2 | False | pending_sso | 0 | 0 | 0 | 0 | 0 | 578.0 |
| stop_test__hybrid__socks5 | 1 | True | stop_ok | 0 | 0 | 0 | 0 | 0 | 17.2 |
| stop_test__hybrid__socks5 | 2 | True | stop_ok | 0 | 0 | 0 | 0 | 0 | 17.2 |

## Summary
- total=12 ok=11 fail=1

## Issues
- browser__socks5__aol r1: s=4 but dg2a=+3 (SSO session collision sean/littlejohn same session_id) -> 18r44c hard reject
- browser__socks5__aol r2: s=3 f=1 dg2a=+2 dsub2=+3 (collision/import lag) -> 18r44c
- pending_sso_recovery r2: s=0 class=pending_sso (CreateEmail false-sent / early_no_new) -> 18r44b body_ok (next job reload)
- stop_test r1/r2: stop_ok, panel alive

## Pool final (from DONE)
- g2a 3765->3775 (+10) sub2 3874->3886 (+12) during tracked tail; full summary deltas sum g2a success-aligned except AOL collisions

