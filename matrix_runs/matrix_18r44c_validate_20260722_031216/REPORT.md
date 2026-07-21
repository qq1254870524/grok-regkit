# Matrix 18r44c/d Silent Stable Report

- generated: 2026-07-22T03:50:00
- workers=2 preheat=4 count=4 rounds=2
- proxy: socks5_list only; silent browser; no console window (pythonw parent)
- follow-up: 18r44d SOCKS5 precheck-before-browser + dual G2A targets (8010 primary + 8011/8020 mirror)

## Results

| cell | r | ok | class | s | f | p | dg2a | dsub2 | t |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| browser__socks5__aol | 1 | True | success_partial | 3 | 1 | 0 | 3 | 3 | 455.8 |
| browser__socks5__aol | 2 | True | success | 4 | 0 | 0 | 4 | 4 | 405.3 |
| pending_sso_recovery__socks5 | 1 | True | success | 2 | 0 | 0 | 2 | 2 | 629.9 |
| pending_sso_recovery__socks5 | 2 | True | success | 2 | 0 | 0 | 2 | 2 | 549.9 |
| stop_test__hybrid__socks5 | 1 | True | stop_ok | 0 | 0 | 0 | 0 | 0 | 17.2 |
| stop_test__hybrid__socks5 | 2 | True | stop_ok | 0 | 0 | 0 | 0 | 0 | 17.3 |

## Summary
- total=6 ok=6 fail=0
- pool_delta matrix window: g2a 3775->3786 (+11), sub2 3886->3897 (+11)
- all successful registrations entered both G2A(8010) and Sub2 during matrix (dg2a==success count)

## Issues / pool notes
- r1 class was mislabeled pending_sso by old classifier (disk has success_partial fix); s=3 f=1 with full pool entry
- 8020/8011 mirror lag: 8010 had ~3786 while 8011/8020 ~3742 before backfill; root cause=running 8092 without dual-target code; fixed in 18r44d + backfill 8010->8011
- SOCKS5 Chromium interstitial on first open: fixed by ensure_live_proxy_before_browser / pick_live_proxy

