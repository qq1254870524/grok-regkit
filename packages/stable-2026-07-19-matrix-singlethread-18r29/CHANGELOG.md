## 2026-07-19r29k / pool-sync + matrix-18r29

- 后处理：NSFW → G2A → CPA mint → Sub2API（`import_after_success_prefer_cpa`，优先 CPA OAuth JSON，失败落盘可回填）
- `sub2api_client`：`record_sub2api_import_failure` / `log_pool_counts` / `backfill_missing_sub2api_from_cpa_and_sso`
- `tools/reconcile_pools.py`：TXT / token.json / G2A / Sub2API / CPA 对账
- Web 进程需加载最新 `sub2api_client`（重启后符号齐全）；矩阵 pending_sso 收尾后打 tag `stable-2026-07-19-matrix-singlethread-18r29`（不覆盖历史 packages）
- marked: 2026-07-19T11:11:56

# CHANGELOG

## 2026-07-19r28i / restore: stable-2026-07-19-docs-sync-18r28i

- **文档与全关联同步还原点**（不改 18r28h 业务逻辑，不覆盖旧 Packages/Releases）。
- 整理 `CHANGELOG.md`：去除重复头部与重复 18r28h 块，按时间倒序单文件维护。
- 更新 `README.md`：按本机实际能力补充 Outlook/AOL 池、pending SSO 二次补、Turnstile 登录、hybrid 即时 SSO、SOCKS5 代理池、Sub2API/g2a/CPA 入池、Web 8092、关联仓库表与还原点索引。
- 补全 `MATRIX_REPORT.md` 18r28h 终态：pending recovery count=2 → success=1 fail=1（iveansow 成功即时 SSO+入池；juliostangoc 邮箱无新信回 pending）。
- 新增/更新 `STABLE_VERSION.md`、`RESTORE_NOTES.md` 指向本还原点与历史 tags。
- 打包 `packages/stable-2026-07-19-docs-sync-18r28i/` + `.zip`（核心源码 + 文档）。
- 关联仓同步：`sub2api`（Grok OAuth 429 多账号 failover）、`grok-regkit-services` 文档对齐 18r28h/18r28i；`grok2api` / `turnstile-harvester1` 打配套还原说明（不覆盖旧 release）。

## 2026-07-19r28h / restore: stable-2026-07-19-pending-one-login-18r28h

- **根因**：登录失败后「又重新登录」——(1) Turnstile 后 `_click_signin_submit` + submit boost **双重点登录**；(2) CF stuck 的 `continue` **绕过** ≥10s 改注册；(3) 55s long-wait probe 导航回 sign-in。
- **修复**：首次仅 **ONE login submit**；CF 最多 inject-only 1 次且 ≥10s 仍停 sign-in → `auth_error` **IMMEDIATE hybrid 重注册**；删除 long-wait 回登录；禁止二次 click/refill。
- 实跑 pending count=2 SOCKS5 Outlook：`ONE login submit` / `login_submit_done=1` / `IMMEDIATE re-register (NO second login click)`；终态 success=1 fail=1；session_success 累计正常。
- 主路径不变：注册→即时 SSO→入池；pending 仅兜底。

## 2026-07-19r28g / restore: stable-2026-07-19-pending-turnstile-18r28g

- **二次补 SSO 登录失败不再二次点登录**：首次 submit 后立刻 hybrid 重注册；日志 `NO second login click`。
- **sign-in 停顿 ≥10s 无 SSO**：立即重注册（删除旧 re-fill 再点登录路径）。
- **CF stuck 后**：仅 inject Turnstile token，禁止 re-fill + 再点登录。
- **邮箱路由按域名/token**：`resolve_mailbox_provider`；全局 `email_provider=aol` 时 Outlook 仍走 Graph。
- **热重载**：pending job 重载相关模块。
- 实跑 pending count=2：success=2 fail=0。

## 2026-07-19r28c / restore: stable-2026-07-19-pending-turnstile-18r28c

- pending 二次补 SSO 登录路径接入 Turnstile token 采集/注入。

## 2026-07-19r27 / restore: stable-2026-07-19-forced-rereg-18r27

- 登录失败强制 hybrid 重注册；密码错误/账号不存在分类处理。

## 2026-07-19r26 / restore: stable-2026-07-19-sso-hold-signup-18r26

- SSO hold / signup 路径加固；pending 与主路径边界更清晰。

## 2026-07-19r25 / restore: stable-2026-07-19-nsfw-direct-18r25

- NSFW 直连与 Outlook 投递相关修复。

## 2026-07-19r23 / restore: stable-2026-07-19-outlook-sso-nudge-18r23

- Outlook SSO nudge / 收信策略。

## 2026-07-19r20 / restore: stable-2026-07-19-consent-working-18r20

- consent 工作 Next-Action 持久化；CreateEmail share-first 防 incomplete envelope；SignUp 无 SSO 时 remint 再试。
- 实跑 hybrid×direct×outlook success；CPA `mint_method=authcode_pkce`。

## 2026-07-19r19 / restore: stable-2026-07-19-mailpoll180-18r19

- 邮件轮询 180s；matrix API retry；consent/envelope 初版。

## 2026-07-19r18 / restore: stable-2026-07-19-dualsend-lock-18r18

- dual-code 真发送锁：CreateEmail 首次后 short-circuit。

## 2026-07-19r16 / restore: stable-2026-07-19-ratelimit-switch-18r16

- 验证码过多（rate limit）直接换下一个邮箱。

## 2026-07-18r11 — CPA consent/device-code 与 pending SSO

- consent Next-Action 两阶段 JS chunk 扫描（12→40）；device-code 错误分类/退避；pending 直接进 sign-in。

## 2026-07-18r10 / restore: stable-2026-07-18-matrix-18r10

- dual-code 发送锁与矩阵基线。

## 历史还原点（勿覆盖）

见 `STABLE_VERSION.md` 完整 tag 列表。
