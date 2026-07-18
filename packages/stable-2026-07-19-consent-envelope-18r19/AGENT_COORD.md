# grok-regkit multi-agent coordination
updated: 2026-07-19T01:40:00+08:00
session: 019f67c8-d349-7bd0-a823-de10e7a42f89
formal: C:\Users\zhang\grok-regkit
tmp: C:\Users\zhang\Desktop\codex_aidate_tmp

## LOCKS (do not touch if owned by other agent)

### Agent-A (consent/envelope — THIS agent / already DONE)
owner: agent-a-resume-consent
status: DONE
files_owned:
  - sso_to_auth_json.py (18r19 deployed formal)
  - browser/token_harvester.py (18r19 AbortError, deployed formal)
verified:
  - unit tests ALL PASSED
  - live CPA: soft-nav blacklist 0071fd1191ff -> code from 404454cfbd85
  - mint_method=authcode_pkce referrer=grok-build
  - incomplete envelope: fake JSON removed; last 200 log lines 0 hits
do_not:
  - re-patch consent/harvester for same issue
  - re-restart 8092 just for 18r19 (already PID 31044 with 18r19)
  - re-run consent probes unless regression

### Agent-B (Sub2API / gateway)
owner: agent-b-sub2api
status: IN_PROGRESS (seen patch_sub2api.py / patch_import.py / sub2api_diag.sql at ~01:34)
files_owned:
  - Sub2API / openai_gateway_scheduling.go and related gateway tests
  - sub2api pool/429 auto-pause work
do_not (for Agent-A):
  - edit patch_sub2api*.py or backend Sub2API sources while B active
do_not (for Agent-B):
  - overwrite sso_to_auth_json.py / token_harvester.py
  - kill web\server.py without noting here
  - kill matrix_cross_run.py 164008 without noting here

### Shared runtime (read-only unless needed)
- web: python -B web\server.py PID 31044 port 8092 (18r19 loaded)
- matrix: tools\matrix_cross_run.py 10 720 PID 164008
  out: matrix_runs\matrix_18r14_20260719_004422
- services: grok-regkit-services1 (g2a/cpa_gateway/cliproxy)

## REMAINING BACKLOG (claim before starting)

| id | task | claim | notes |
|----|------|-------|-------|
| M1 | matrix hybrid socks5 outlook r3-10 | MATRIX_RUNNER | already running |
| M2 | matrix hybrid socks5 aol x10 | MATRIX_RUNNER | pending after outlook |
| M3 | matrix browser cells x10 | UNCLAIMED | after hybrid done |
| M4 | pending_sso root-cause sample + fix | agent-a claimed | analysis only first |
| P1 | package stable-2026-07-19-*-18r19 (no overwrite old) | agent-a claimed | after code stable |
| G1 | git commit 18r19 + push mygithub | UNCLAIMED | wait package or explicit |
| S1 | Sub2API 429 pause | agent-b | their lane |

## HANDOFF RULES
1. Before editing a file: check this doc locks.
2. After finishing a claimed task: set status DONE + one-line evidence.
3. Never RestoreDefault keypool or wipe pools.
4. Packages: new dir only, never overwrite old packages.
5. Logs: no key/password/token redaction required by user for regkit ops logs, but do not print API keys in coord file.
