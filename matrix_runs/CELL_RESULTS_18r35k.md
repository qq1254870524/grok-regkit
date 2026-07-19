# Matrix cell results 2026-07-20 (18r35k live validation)

Version under test: **stable-2026-07-20-matrix-hotfix-18r35k** (`edfaca0` / docs `eb807ca`)

## Prior session (carried)
| cell | result |
|------|--------|
| browser × direct × outlook count=6 w=3 | **6/0/0** instant SSO |
| hybrid × socks5 × outlook count=4 w=2 | **2/0/2** pending (Outlook early_no_new_mail → burn + pending mail_token) |
| pending_sso recover (18r35j) | 4/2 then fixed queue |

## This session
| cell | result |
|------|--------|
| hybrid × direct × aol count=4 w=2 | **4/0/0** |
| hybrid × socks5_list × aol count=4 w=2 | **4/0/0** Sub2 ~1094 |
| browser × direct × aol count=4 w=2 | **4/0/0** Sub2 ~1097–1098 |
| browser × socks5_list × aol count=4 w=2 | **4/0/0** Sub2 ~1102 |
| pending_sso recover count=6 w=3 | **6/0/0** (Turnstile before login; fail→re-register not re-login loop) |

## Totals this session (register+recover counted by job)
- AOL register jobs: **16 success / 0 fail / 0 pending_sso**
- pending recover: **6 success / 0 fail**
- **RATE_LIMIT / 验证码过多 hard fail: 0**
- Main path intact: register → instant SSO (sso_len≈2477) → NSFW → G2A → CPA authcode → Sub2 OAuth
- reconcile missing=0 observed after hybrid jobs
- Sub2 verify may 403 once on brand-new account then pass on retry (account kept)

## Notes
- CreateEmail global gate 4.0s + skip re-click anti double-send active
- Outlook no-mail still burn/switch; do not change register main path for delivery
- Stop registration only via /api/stop; gateways 8010/8080/8317/8318/8092 kept up
