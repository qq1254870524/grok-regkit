# 18r44c Silent Multi-thread Stable

Date: 2026-07-22

## Highlights
- Multi-thread silent matrix (workers=2, preheat=4, count=4) full cross-run socks5 hybrid/browser outlook/aol + pending_sso_recovery + stop_test
- CPA auth.x.ai: prefer_direct_first (avoid SOCKS curl 97 / User rejected by SOCKS5)
- 18r44a: wait_for_sso ignores baseline cookies; open_signup clears xAI session; Windows per-launch user-data
- 18r44b: CreateEmail requires body_ok + real 2xx/send; bare OTP UI no longer promotes browser_sent
- 18r44c: process-wide session_id claim; collision never writes disk or imports G2A/Sub2; browser restarts after each success

## Stop semantics
- /api/stop: stop Event + kill script workers/browsers only; keep 8092 / G2A / Sub2 / user Edge

## Matrix notes
- stop_test: both rounds stop_ok, panel alive
- AOL browser pool mismatch root cause: same session_id on two emails (fixed by 18r44c)
- recovery r2 zero success: CreateEmail false-send path (18r44b)

## Non-goals
- Does not overwrite prior packages
- Does not ship config.json or live accounts
