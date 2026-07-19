
## 2026-07-19r30c / browser MT finish path fix (P0)

- 根因：`_register_one_browser` 取码后乱试不存在的 helper，抛 `browser multi-thread finish helper missing`；部分路径仅填资料即 `record_success` 且**不取 SSO**。
- 修复：对齐串行路径 — `fill_profile_and_submit` → `wait_for_sso_cookie` → 写 `accounts_*.txt` → `schedule_post_registration` → `mark_outlook_registered`。
- 验证码耗尽 / SSO 超时：`burn_mailbox_to_pending` + `pending_sso:` 前缀，MT worker 计 `pending` 不计 hard fail。
- 不杀 8010/8080/8317/8318；下一 register job `importlib.reload(grok_register_ttk)` 自动生效。
- marked: 2026-07-19T13:55:00

## 2026-07-19r30-lossfix (Sub2 丢号彻底修复)

- 根因：后处理 Sub2 导入失败/超时不重试；CPA 已 mint 但未入 Sub2；G2A 先成功导致三池数量不一致。
- `sub2api_client.import_after_success_prefer_cpa`：CPA→SSO 各路径最多 3 次重试。
- 新增 `reconcile_sub2api_pools` / `process_sub2api_pending_file`：任务结束后自动 G2A+hybrid+CPA 对账补齐 Sub2。
- 失效 SSO（`GROK_SSO_UNAUTHORIZED`）写入 `sub2api_import_dead.jsonl`，不再死循环 pending。
- `hybrid_register` 任务结束 `wait_post_success_queue` 15/45s → 20/120s。
- Web：`POST /api/sub2api/reconcile`；job 启动 reload `sub2api_client`/`cpa_export`。
- 现场补齐：`mattieivettefxp@outlook.com`、`richkjgergele@outlook.com`；池对齐 G2A=Sub2=231（CPA=225）。
- 仅剩 `neb40el@aol.com`：SSO 已失效且无 CPA，需二次补 SSO 后才能入 Sub2。

## 2026-07-19r29k / pool-sync + matrix-18r29

- 后处理：NSFW → G2A → CPA mint → Sub2API（`import_after_success_prefer_cpa`，优先 CPA OAuth JSON，失败落盘可回填）
- `sub2api_client`：`record_sub2api_import_failure` / `log_pool_counts` / `backfill_missing_sub2api_from_cpa_and_sso`
- `tools/reconcile_pools.py`：TXT / token.json / G2A / Sub2API / CPA 对账
- Web 进程需加载最新 `sub2api_client`（重启后符号齐全）；矩阵 pending_sso 收尾后打 tag `stable-2026-07-19-matrix-singlethread-18r29`（不覆盖历史 packages）
- marked: 2026-07-19T11:11:56

## 2026-07-19r30b / open_signup PageDisconnected + matrix email_provider

- open_signup: 页面断开自动 refresh/restart 代理重试。
- matrix: PUT 含 email_provider / preflight_limit。
- smoke 前: hybrid×socks5×aol workers=2 成功1失败1(代理断连)；补丁后继续全矩阵。

## 2026-07-19r30 / restore: stable-2026-07-19-matrix-multithread-18r30

- **多线程稳定版**（相对 18r29 单线程；不覆盖历史 Packages/Releases）。
- Web UI：`#regWorkers` 线程数（1–32）；`/api/start` 与 `/api/pending-sso/recover` 传 `workers`。
- `worker_coord.py`：`JobCoordinator` 槽位/计数锁；`bind_worker_proxy` SOCKS5 `pool[(w-1)%n]` 顺序复用；`preflight_email_pools` 启动预登录删坏号。
- hybrid / pending / 全浏览器：`workers>1` 走 MT；TLS 浏览器 + 线程本地代理；邮箱池 `acquire/in_use` 防双抢。
- 收信：全文件夹扫描，每夹最新 **5** 封（Outlook `GRAPH_TOP=5` / AOL `TOP=5`）。
- 停止注册只清 Chromium，**不杀** 8010/8080/8317/8318 外围服务。
- 矩阵：`tools/matrix_18r30_multithread.py`（hybrid|browser × direct|socks5_list × aol|outlook，workers=2，每格 count=10）。
- marked: 2026-07-19T12:12:35


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

## 18r30c (in-progress full matrix)
- hybrid per-account mailbox preflight top=15/25 -> **top=5** (align AOL TOP=5 / Outlook GRAPH_TOP=5)
- keep register->immediate SSO->NSFW->G2A->CPA->Sub2API primary path
- finisher auto-publish tag: stable-2026-07-19-matrix-multithread-18r30-full (no overwrite 18r29/early 18r30)
- matrix 8 cells x 10 accounts x workers=2 running; smoke3 hybrid/socks5/aol 2/2; cell1 hybrid/direct/aol 10/10


## stable-2026-07-19-matrix-multithread-18r30-full
- time: 2026-07-19T14:14:27
- multi-thread full matrix completion package
- Sub2 drop-account fix: import retries + job-end reconcile; dead SSO queue
- Sub2 drop-account fix: import retries + job-end reconcile G2A/hybrid/CPA; dead SSO queue
- does not overwrite 18r29 or early 18r30 tag
- cell `hybrid__direct__aol` success=10 fail=0 pending=0 err=
- cell `hybrid__direct__outlook` success=7 fail=0 pending=3 err=
- cell `hybrid__socks5_list__aol` success=7 fail=0 pending=3 err=
- cell `hybrid__socks5_list__outlook` success=2 fail=0 pending=8 err=
- cell `browser__direct__aol` success=5 fail=5 pending=0 err=
- cell `browser__direct__outlook` success=3 fail=5 pending=0 err=
- cell `browser__socks5_list__aol` success=3 fail=6 pending=1 err=
- cell `browser__socks5_list__outlook` success=0 fail=10 pending=0 err=
- cell `pending_sso_recovery` success=0 fail=10 pending=None err=
