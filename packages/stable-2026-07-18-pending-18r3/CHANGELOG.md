# CHANGELOG — stable-2026-07-18-pending-18r3 (还原点 #4)

日期: 2026-07-18

## 相对还原点 #3 (`stable-2026-07-18-matrix-uifallback`)

本还原点 **不覆盖** 任何历史 tag/package：
- stable-2026-07-18
- stable-2026-07-18-sso-mainflow
- stable-2026-07-18-matrix-uifallback
- 本地包 stable-2026-07-18-matrix-speed（速度补丁中间包，保留）

### pending_sso_recovery.py（18r / 18r2 / 18r3）
- 登录提交后强制 quiet 等待 ≥12s（或 URL 变化），禁止 1s 内连点打断登录
- Cloudflare / captcha / challenge 未过完不跳 grok.com
- 仅确认离开 sign-in 后才打开 accounts/grok 固化 cookie
- 真正点击登录按钮 + form.requestSubmit + Enter
- 18r2：页面标题「您正在登录」不再误判为 loading
- 18r3：识别 `An error occurred` / 登录失败 → `auth_error`
- **`bad_password` / `account_missing` / `auth_error`：移出 pending 后走 hybrid 重新注册**（不是只删号）
- `rate_limit` 不直接重注册

### hybrid_register.py
- 主路径不变：注册成功 → **当时即时 SSO** → 入池（CPA/Sub2API/G2A）
- pending 仅兜底；UI fallback 最后
- changelog 记录 18r 系列与 re-register 入口

### mailbox speed（承接 matrix-speed 中间包）
- AOL/Outlook poll dump 降噪 + TOP 收敛
- 保留 ALL folders 扫描与 CreateEmail 后 3s 再查信

### Grok2API
- 模型列表含 `grok-4.5` / `grok-4.5-console` 等
- 本机实测 `/v1/chat/completions` model=`grok-4.5` 返回 OK

## 实跑验证摘要（2026-07-18 上午）

### A. pending ×1 `dolbaeb42@aol.com`（SOCKS5）
1. page_err=`bad_password`
2. 移出 pending
3. re-register via hybrid
4. 新邮箱 AOL IMAP 登录成功 → 收码 → Turnstile → SignUp status=200 **sso_len=2477**
5. materialize session SSO → 写 G2A 号池 + Sub2API 入池 + NSFW + CPA OIDC 导出
6. 任务结束：成功 1 | 失败 0 | pending_sso 0

### B. pending ×1 `psixol618ag@aol.com`（SOCKS5）
1. page_err=`auth_error`（页面 An error occurred）
2. 移出 pending
3. re-register via hybrid start（已触发，主路径同 A）

### C. G2A
- `GET /v1/models` 含 grok-4.5 系列（需 Bearer）
- `POST /v1/chat/completions` model=grok-4.5 → content=OK

## 服务约束
- 停止注册只停 8092 任务
- 8010 Grok2API / 8080 Sub2API / 8317 CLIProxy / 8318 CPA Gateway **始终保持运行**

## 关联仓库 tag（同名，不 force）
- grok-regkit → `stable-2026-07-18-pending-18r3`
- grok-regkit-services → 同上
- sub2api → 同上
- grok2api → 同上

## 本地包
`C:\Users\zhang\Desktop\codex_aidate_tmp\packages\stable-2026-07-18-pending-18r3\`
