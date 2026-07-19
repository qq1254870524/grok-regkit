# grok-regkit 18r35k / 18r35j

## Highlights
- **18r35j pending queue**: load prefers longest `mail_token` per email; token-first order; archive no-token rows that cannot re-register.
- **18r35k MT stats**: hybrid re-register returning `pending_sso` no longer stays as hard fail (`undo_fail` + `record_pending`).
- **CreateEmail anti rate-limit**: min gap 2.8s -> **4.0s** across workers; keep skip re-click after actual_send.
- **18r35g/h/i retained**: stop clears running immediately; live phase; MT pending auth_error -> hybrid re-register.

## Live validation (this host)
- pending_sso recover count=6 workers=3: **success 4 / fail 2** (was 0/6 when queue blocked by no-token AOL).
- Main path confirmed: register/re-register -> **immediate SSO** -> G2A -> CPA OAuth -> Sub2API.
- hybrid register count=6 workers=3 Outlook direct: in progress during packaging.

## Notes
- Stop registration via `/api/stop` only; gateways 8010/8080/8317/8318 stay up.
- Do not overwrite previous Packages/Releases.
