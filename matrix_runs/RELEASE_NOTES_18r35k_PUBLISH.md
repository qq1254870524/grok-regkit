# Release 18r35k (matrix hotfix chain 18r35b–k)

## Summary
Hotfix after multithread matrix baseline 18r35. Focus: CreateEmail rate-limit, pending token queue, MT pending classification, stop/phase correctness. Main path unchanged: **register → instant SSO → NSFW → G2A → CPA → Sub2**. pending_sso is recovery only.

## Changelog chain
- **18r35b** browser CreateEmail 验证码过多 detect + burn/switch pool
- **18r35c** global CreateEmail gate across workers
- **18r35d** ToS gate + Outlook direct Graph path hardening
- **18r35e** Chromium error-page recovery
- **18r35f** Sub2API already_exists treated as success path
- **18r35g** /api/stop clears running immediately; pending recover route via job_kind
- **18r35h** live phase while workers running (no false finished)
- **18r35i** MT pending auth_error → hybrid re-register
- **18r35j** pending load keeps longest mail_token; prefer token rows; archive no-token
- **18r35k** MT re-register pending_sso undo_fail+record_pending; CreateEmail min gap 2.8→**4.0s**

## Live validation (this session)
| cell | result |
|------|--------|
| pending_sso recover (after 18r35j) | success 4 / fail 2 (no-token head unblocked) |
| browser × direct × outlook count=6 workers=3 | **success 6 / fail 0 / pending 0** |
| hybrid × socks5_list × outlook count=4 workers=2 | running at release prep |

### browser/direct/outlook notes
- Instant SSO + G2A/Sub2/CPA path confirmed (Sub2 account_id ~1082–1084)
- One Outlook `early_no_new_mail` → burn/switch → next mailbox code ok
- **0** hard `验证码过多` / RATE_LIMIT in this cell (gate + no double-send working)
- Sub2 reconcile: missing=0; dead SSO skip only for old dead tokens

## 验证码过多 root cause
xAI CreateEmail rate limit on **email and/or egress IP**, not IMAP failure. Mitigation: detect → burn email → switch; global 4.0s CreateEmail gate; never resend when page already rate-limited.

## Non-goals / safety
- Do not kill gateways 8010/8080/8317/8318 on register stop
- Do not overwrite previous Packages/Releases
- Logs plaintext in app; do not dump secrets in release notes

## Upgrade
Pull/tag this release on running host; restart **only** grok-regkit web (8092). Keep Sub2API/Grok2API/CPA/CLIProxy running.

## Live validation update
| cell | result |
|------|--------|
| browser × direct × outlook count=6 w=3 | **6/0/0** instant SSO path OK |
| hybrid × socks5_list × outlook count=4 w=2 | **2 success / 0 fail / 2 pending_sso** |
| pending notes | 2× Outlook early_no_new_mail (Graph no post-send xAI mail) → burn pool + pending_sso with mail_token; **0** CreateEmail 验证码过多 |
| protocol | hybrid sign-up curl next-action 7f7f6cee... status=200 sso_len=2477 on both successes |

Commit: edfaca0
