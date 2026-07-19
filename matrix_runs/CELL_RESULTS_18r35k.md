# Matrix cell results 2026-07-20 (18r35k live validation)

Version: **stable-2026-07-20-matrix-hotfix-18r35k** + validation package **stable-2026-07-20-matrix-validation-18r35k-live**

## Register matrix
| cell | result |
|------|--------|
| browser×direct×outlook (prior) | **6/0/0** |
| hybrid×socks5×outlook (prior) | **2/0/2** pending (early_no_new_mail) |
| hybrid×direct×aol | **4/0/0** |
| hybrid×socks5×aol | **4/0/0** |
| browser×direct×aol | **4/0/0** |
| browser×socks5×aol | **4/0/0** |
| hybrid×direct×outlook | **3/0/1** pending (mailbox empty → burn+pending; 0 RATE_LIMIT) |

## pending_sso recover
| cell | result |
|------|--------|
| recover count=6 w=3 | **6/0/0** |

## Totals (this continuous agent session after 18r35k)
- AOL register: **16 success / 0 fail / 0 pending**
- Outlook hybrid direct: **3 success / 0 fail / 1 pending**
- pending recover: **6 success / 0 fail**
- **RATE_LIMIT / 验证码过多 hard fail: 0**
- Main path OK: register → instant SSO → G2A/CPA/Sub2
- Gateways kept up: 8092/8010/8080/8317/8318

## Releases (no overwrite)
- https://github.com/qq1254870524/grok-regkit/releases/tag/stable-2026-07-20-matrix-hotfix-18r35k
- https://github.com/qq1254870524/grok-regkit/releases/tag/stable-2026-07-20-matrix-validation-18r35k-live
