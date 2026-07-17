# CHANGELOG


## 2026-07-18 — restore point #3 `stable-2026-07-18-matrix-uifallback`

### Added / Changed
- hybrid: re-enable **UI fallback as last resort only** after protocol SignUp and browser-fetch both fail to produce SSO.
- Order fixed: protocol → browser-fetch → `submit_profile_and_wait_sso` → `pending_sso` disk save.
- Main path unchanged: immediate SSO + CPA/Sub2API/g2a pool ingest on success.
- Matrix live validation started: hybrid+direct+AOL, hybrid+socks5+AOL success paths confirmed before tag.

### Not changed / preserved
- Does **not** overwrite tags `stable-2026-07-18` or `stable-2026-07-18-sso-mainflow`.
- Stop registration still only stops 8092 job; services 8010/8080/8317/8318 stay up.

### Package
- Local package dir: `C:\Users\zhang\Desktop\codex_aidate_tmp\packages\stable-2026-07-18-matrix-uifallback`
