# grok-regkit multi-agent coordination
updated: 2026-07-19T02:06:30+08:00
session: 019f67c8-d349-7bd0-a823-de10e7a42f89
formal: C:\Users\zhang\grok-regkit
tmp: C:\Users\zhang\Desktop\codex_aidate_tmp

## LOCKS

### Agent-A (THIS) — consent/envelope/signup + monitor/git
owner: agent-a-collab-resume
status: ACTIVE-monitor-git
files_owned:
  - sso_to_auth_json.py (18r20 DONE — do not re-patch unless regression)
  - browser/token_harvester.py (18r20 share-first DONE)
  - hybrid_register.py (18r20 no-sso retry DONE)
  - consent_working_next_action.txt (404454cfbd852ce5c8a509c4f06c692fd60f911545)
claimed_now:
  - G1 git commit/push 18r20 sources + packages + CHANGELOG
  - M-monitor matrix 18r19 + live 8092 (observe only unless NEW bug)
do_not:
  - re-patch 18r20 consent unless live regression soft-nav-only-1-candidate fail
  - touch Sub2API / patch_sub2api* / WSL sub2api (Agent-B)
  - kill matrix PID 143044 unless replacing
  - overwrite old packages/*

### Agent-B (Sub2API)
owner: agent-b-sub2api
status: THEIR_LANE
do_not (for Agent-A): edit patch_sub2api* / Sub2API backend / rebuild scripts

### Shared runtime
- web: python -B web\server.py port 8092 PID 163140 (18r20)
- matrix: PID 143044 tools\matrix_cross_run.py 10 720 OUT=matrix_18r19_20260719_014826
- note: r2/r3 empty_log was 8092 restart 10061 during 18r20 deploy; do not treat as reg bug

## BACKLOG
| id | task | claim | notes |
|----|------|-------|-------|
| M1-M3 | matrix cells ≥2/combo | MATRIX_RUNNER 143044 | hybrid×direct×outlook: r4 success, r5 code_timeout pending_sso; in progress |
| M4 | pending_sso / code_timeout | observe | often xAI no-mail on burned boxes; dual-send lock correct |
| P2 | package 18r20 | DONE | packages/stable-2026-07-19-consent-working-18r20 |
| G1 | git commit+push mygithub | agent-a ACTIVE | 18r20 3 files + packages + coord |
| S1 | Sub2API 429 | agent-b | |

## LIVE OBSERVE (02:05)
- consent working: r4 mint_method=authcode_pkce Next-Action 404454... SUCCESS
- incomplete envelope: share-first deployed; no live toast in current rounds
- r5/r1 fail class=code_timeout_or_empty (browser actual_send=1, Graph no new xAI mail) — not consent
- live job 02:04 joannelouisek1ds@outlook.com code=5TO-LES VerifyEmail 200 → turnstile

## 18r20 root cause (user [01:19:36] consent 失败)
- discovery often only soft-nav 0071fd... (1 candidate) → re-enter still 1 → fail
- fix: persist/prepend working 404454... + extended scan when under-discovered
- incomplete envelope: AbortError → share first CreateEmail Promise

## Agent-A evidence
- Desktop work: Desktop\codex_aidate_tmp\regkit_fix_consent_18r20
- Probe: Desktop\codex_aidate_tmp\probe_18r20_out.txt SUCCESS
- Formal: 18r20 deployed on 8092
