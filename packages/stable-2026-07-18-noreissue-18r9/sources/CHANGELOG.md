# CHANGELOG

## 2026-07-18r9 / restore: stable-2026-07-18-noreissue-18r9

- hybrid 主路径保持：CreateEmail → VerifyEmail → protocol SignUp → 即时 materialize SSO → 入池；pending 仅兜底。
- 18r8: CreateEmail freeze-reclick（sent/2xx/code-step 后禁二次 click）；prepare_profile 仅 given/pw 算 ready；VerifyEmail 后禁止 open_signup 重发码。
- 18r9: mint_fresh_castle 对注入弱 token(~744) early-abort（weak_hits>=3），窗口 6s/4s，复用 CreateEmail IBYIll；避免约 32s 空刷日志。
- 实跑验证 hybrid + SOCKS5 + AOL：
  - 18r8: success=1 pending=0 immediate SSO（marra...）
  - 18r9: success=1 pending=0，weak early-abort 约 5s 后复用 castle，SignUp sso_len=2477 → session 152；NSFW/g2a/Sub2API 后处理正常。
- dual-code 同秒双信仍可能出现（fetch+XHR 双记 net_hits），但 freeze-reclick 阻止额外点击。
- 未覆盖旧 restore tag/package。




## 2026-07-18 — restore point #4 `stable-2026-07-18-pending-18r3`

### Added / Fixed
- pending_sso_recovery **18r/18r2/18r3**:
  - post-submit quiet wait ≥12s; no rapid re-click during login
  - Cloudflare/captcha unfinished → do not jump grok
  - only leave-sign-in then materialize cookies
  - page title "您正在登录" not treated as loading (18r2)
  - `An error occurred` → auth_error (18r3)
  - **bad_password / account_missing / auth_error → remove pending then hybrid re-register** (not delete-only)
- hybrid main path unchanged: register → immediate SSO → pool ingest; pending fallback only; UI fallback last
- mailbox speed tweaks retained from matrix-speed intermediate package
- G2A verified: `grok-4.5` models listed and chat completion OK

### Live validation
- pending bad_password path: re-register hybrid → SSO → G2A/Sub2API/CPA success
- pending auth_error path: re-register hybrid started
- stop-registration still does not stop 8010/8080/8317/8318

### Package
- `C:\Users\zhang\Desktop\codex_aidate_tmp\packages\stable-2026-07-18-pending-18r3`
- Does **not** overwrite tags: `stable-2026-07-18`, `stable-2026-07-18-sso-mainflow`, `stable-2026-07-18-matrix-uifallback`
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

