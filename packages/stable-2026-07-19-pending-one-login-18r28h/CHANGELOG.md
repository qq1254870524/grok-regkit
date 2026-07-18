# CHANGELOG


## 2026-07-19r28h / restore: stable-2026-07-19-pending-one-login-18r28h

- **根因**：登录失败后「又重新登录」——(1) Turnstile 后 `_click_signin_submit` + submit boost **双重点登录**；(2) CF stuck 的 `continue` **绕过** 10s 改注册；(3) 55s long-wait probe 导航回 sign-in。
- **修复**：首次仅 **ONE login submit**；CF 最多 inject-only 1 次且 ≥10s 仍停 sign-in → `auth_error` **IMMEDIATE hybrid 重注册**；删除 long-wait 回登录；禁止二次 click/refill。
- 主路径不变：注册→即时 SSO→入池；pending 仅兜底。
## 2026-07-19r28g / restore: stable-2026-07-19-pending-turnstile-18r28g

- **二次补 SSO 登录失败不再二次点登录**：`page_err in {auth_error,bad_password,account_missing,need_reregister}` 首次 submit 后立刻 `fail_reason=auth_error` → hybrid 重注册；日志 `NO second login click`。
- **sign-in 停顿 ≥10s 无 SSO**：`still on sign-in after first submit ... NO re-fill login` → 立即重注册（删除旧 re-fill 再点登录路径）。
- **CF stuck 后**：仅 inject Turnstile token，**禁止** re-fill + 再点登录（18r28g）；超时走重注册。
- **邮箱路由按域名/token**：`resolve_mailbox_provider`；全局 `email_provider=aol` 时 Outlook 仍走 Graph（修复 `AOL missing password for xxx@outlook.com`）。
- **热重载**：pending job 重载 `grok_register_ttk` + `pending_sso_recovery` 等，无需整进程重启。
- 实跑 pending_sso_recovery count=2：success=2 fail=0；两条均 login auth_error → IMMEDIATE re-register → Outlook Graph 收码 → protocol SignUp sso wrapper→session152 → g2a/Sub2API/CPA/NSFW 完成；pending 成功移出。
- 主路径不变：注册 → 即时 SSO → 入池；pending 仅兜底。
- 不覆盖旧 packages/releases/tags。

﻿# CHANGELOG


## 2026-07-19r28h / restore: stable-2026-07-19-pending-one-login-18r28h

- **根因**：登录失败后「又重新登录」——(1) Turnstile 后 `_click_signin_submit` + submit boost **双重点登录**；(2) CF stuck 的 `continue` **绕过** 10s 改注册；(3) 55s long-wait probe 导航回 sign-in。
- **修复**：首次仅 **ONE login submit**；CF 最多 inject-only 1 次且 ≥10s 仍停 sign-in → `auth_error` **IMMEDIATE hybrid 重注册**；删除 long-wait 回登录；禁止二次 click/refill。
- 主路径不变：注册→即时 SSO→入池；pending 仅兜底。
## 2026-07-19r20 / restore: stable-2026-07-19-consent-working-18r20

- **consent 失败（仅 1 个 Next-Action soft-nav）**：工作 Next-Action 持久化到 `consent_working_next_action.txt`（404454…），每轮 prepend；候选不足时扩展 JS 扫描。
- **incomplete envelope / 注册按钮 AbortError**：`token_harvester` CreateEmail 重复请求 share-first 首个 Promise，不再 reject 半截 envelope。
- **SignUp 200 sso_len=0**：`hybrid_register` 在协议候选失败后 remint+再试一次（18r20-retry-first-after-nosso）。
- 实跑：matrix hybrid×direct×outlook r4/r6 success；CPA `mint_method=authcode_pkce` + working 404454…；probe SUCCESS ~3.9s。
- 不覆盖旧 packages（另存 `consent-envelope-18r19` / `consent-working-18r20`）。

## 2026-07-19r19 / restore: stable-2026-07-19-consent-envelope-18r19

- 邮件轮询 180s + matrix 10061 API retry；consent/envelope 初版（后续 18r20 加固 working action 持久化）。

## 2026-07-18 18r11 — CPA consent/device-code 与 pending SSO 修复

- consent Next-Action 改为两阶段 JS chunk 扫描：快速 12 个，无有效 action 时扩展至 40 个。
- 只有解析到真实 Server Action ID 才早停；不再自动提交已知失效的 hardcoded action。
- device-code 网络错误增加分类、指数退避、端点/路由/耗时日志；HTTP 4xx 不做无意义网络重试。
- 避免 browser_confirm 外层再次乘以三轮 device-code 重试。
- pending SSO 直接启动浏览器进入 sign-in，不再先打开 sign-up 作为 bootstrap。
- 新增 18r11 本地回归测试：late chunk、死 fallback、RemoteDisconnected 恢复、400 不重试、代理凭据不入日志、pending sign-in 入口。

# CHANGELOG


## 2026-07-19r28h / restore: stable-2026-07-19-pending-one-login-18r28h

- **根因**：登录失败后「又重新登录」——(1) Turnstile 后 `_click_signin_submit` + submit boost **双重点登录**；(2) CF stuck 的 `continue` **绕过** 10s 改注册；(3) 55s long-wait probe 导航回 sign-in。
- **修复**：首次仅 **ONE login submit**；CF 最多 inject-only 1 次且 ≥10s 仍停 sign-in → `auth_error` **IMMEDIATE hybrid 重注册**；删除 long-wait 回登录；禁止二次 click/refill。
- 主路径不变：注册→即时 SSO→入池；pending 仅兜底。
## 2026-07-18r10 / restore: stable-2026-07-18-matrix-18r10

- dual-code 真发送锁：CreateEmail fetch/XHR 首次后 short-circuit；actual_send/blocked_dup 可观测；UI click send-lock。
- CPA consent 加速：JS 扫描 10s/max12/timeout8s；cache-first。
- SSO materialize 分段日志：stage=start/browser_nav/browser_done。
- 主路径不变：注册 → 即时 SSO → 入池；pending 仅兜底。
- 实跑 hybrid + SOCKS5 + AOL count=1：success=1 pending=0；wrapper 2477 → session 152；immediate SSO+pool ≈148s。
- 补齐 packages/ 入仓：18r9 完整 sources（此前只有 RESTORE md）+ 18r10 新 package。
- 不覆盖旧 restore tags。

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


