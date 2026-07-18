# grok-regkit multi-agent coordination
updated: 2026-07-19T02:48:00+08:00
sessions_both_same_project: 019f67c8-d349-7bd0-a823-de10e7a42f89 | 019f763b-0d88-7aa0-8b89-9b234e2d9cab
NOTE: BOTH agents work on grok-regkit main project (NOT Sub2API-only split). Avoid duplicate bug ownership via file locks below.
formal: C:\Users\zhang\grok-regkit

## LOCKS (same project, split files)
### Agent-A (019f67c8)
- web metrics / matrix / register_count pref / package-git when packaging
### Agent-B (019f763b)
- claim other open bugs via this file before editing; do not redo A's live matrix monitor

## CPA auths dual appearance (EXPLAINED, not a bug)
- Dir: C:\Users\zhang\grok-regkit\cpa_auths
- Filename always: xai-<email>.json (dots in email local-part are normal, e.g. choseabout.92)
- Two JSON *serialization* styles, same schema:
  1) pretty indent type-first — written by regkit sso_to_auth_json.write_cpa_auth
  2) compact sorted keys access_token-first — rewritten by CLIProxyAPI (cli-proxy-api.exe)
     auth-dir points to SAME folder (config1.yaml auth-dir -> grok-regkit\cpa_auths)
- Fields identical: type=xai auth_kind=oauth tokens/sso/headers/...
- Optional unify later: write_cpa_auth sort_keys+indent; CPA refresh will still compact

## LIVE
- matrix still running; register_count pref fix r22 on disk
