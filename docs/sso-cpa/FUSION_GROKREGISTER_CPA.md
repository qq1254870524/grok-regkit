# Fusion: grokRegister-cpa → grok-regkit

Date: 2026-07-17 fuse-v1

## What was merged

From https://github.com/Git-creat7/grokRegister-cpa (MIT):

1. Authorization Code + PKCE mint with `referrer=grok-build` (`sso_to_auth_json.py`)
2. Remote CLIProxyAPI Management API upload (`POST /v0/management/auth-files`)
3. Config aliases `cpa_auto_add`, `cpa_remote_url`, `cpa_management_key`

## What was kept local

- hybrid protocol register
- Web console 8092
- cpa_gateway 8318
- grok2api pool
- public temp-email providers + heartbeat fix
- device/protocol mint as fallback

## Default behavior after fusion

1. On SSO success → `export_cpa_xai_for_account`
2. If `cpa_prefer_authcode` (default true) and SSO present → authcode mint first
3. On failure → existing `cpa_xai.mint_and_export` (protocol/device)
4. Write `cpa_auths/xai-<email>.json` (CLIProxyAPI hot-load dir on this machine)
5. If `cpa_remote_upload` + url + plaintext management key → remote POST

## Notes

- CPA yaml `secret-key` may be bcrypt-hashed after first start; remote upload needs the **original plaintext**.
- Local stack already uses `auth-dir: ...\cpa_auths`, so remote upload is optional.
