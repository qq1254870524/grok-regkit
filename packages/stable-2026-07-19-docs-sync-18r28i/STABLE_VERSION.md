# STABLE_VERSION — known-good restore points

> **当前推荐还原点**：`stable-2026-07-19-docs-sync-18r28i`（文档全量同步 + 业务基线 18r28h）  
> **业务代码完美点**：`stable-2026-07-19-pending-one-login-18r28h`  
> **历史 packages/releases 一律保留，禁止覆盖。**

## Latest — stable-2026-07-19-docs-sync-18r28i（18r28i）

| 项 | 值 |
|----|----|
| Tag / Release | `stable-2026-07-19-docs-sync-18r28i` |
| Marked at | 2026-07-19 |
| Purpose | 文档去重、README 按实况、MATRIX 终态、关联仓同步与 Packages 备份 |
| Repo | https://github.com/qq1254870524/grok-regkit |
| Local | `C:\\Users\\zhang\\grok-regkit` |
| Package | `packages/stable-2026-07-19-docs-sync-18r28i.zip` |

### 本快照能力（含 18r28h 业务）

- hybrid / browser 双注册；协议优先 SignUp，注册成功即时 SSO 入池
- Outlook（Graph）/ AOL（IMAP+TOTP）邮箱池；域名路由 `resolve_mailbox_provider`
- pending SSO 二次补：Turnstile + **仅一次**登录提交；失败立即 hybrid 重注册，禁止再点登录
- SOCKS5 代理池（Web 内保存）；Web 控制台 `http://127.0.0.1:8092`
- Sub2API SSO/CPA 入池；CPA OIDC mint（authcode_pkce + consent working action）
- 日志应用内明文（禁止脱敏）；账号/SSO/密钥 **不进公开 git**

### 还原

```bash
git fetch mygithub --tags
git checkout stable-2026-07-19-docs-sync-18r28i
```

## 业务完美点 — stable-2026-07-19-pending-one-login-18r28h

| 项 | 值 |
|----|----|
| Commits | `3dfe749` + `585f20f` |
| Release | https://github.com/qq1254870524/grok-regkit/releases/tag/stable-2026-07-19-pending-one-login-18r28h |
| Package | `packages/stable-2026-07-19-pending-one-login-18r28h.zip` |

## 配套仓库（18r28i 同步）

| 项目 | Repo | 说明 |
|------|------|------|
| grok-regkit | https://github.com/qq1254870524/grok-regkit | 主注册 / Web / pending / hybrid |
| grok-regkit-services | https://github.com/qq1254870524/grok-regkit-services | 本机服务编排（脱敏） |
| sub2api | https://github.com/qq1254870524/sub2api | CPA/CLIProxy JSON 导入 + Grok 429 failover |
| grok2api | https://github.com/qq1254870524/grok2api | 模型注册 / 本地 API |
| turnstile-harvester1 | https://github.com/qq1254870524/turnstile-harvester1 | Turnstile 采集独立抽取 |
| mumu-clipboard-isolation | https://github.com/qq1254870524/mumu-clipboard-isolation | MuMu 剪贴板隔离（弱关联） |

## 本机运行面（不含密钥）

| 服务 | 端口 | 说明 |
|------|------|------|
| grok-regkit Web | 8092 | 注册 / pending / 配置 |
| Sub2API | 8080 | 号池 |
| grok2api | 8010 | 模型 API |
| CLIProxyAPI | 8317 | OAuth/CLI 代理 |
| CPA Gateway | 8318 | 网关 |

停止注册：`POST http://127.0.0.1:8092/api/stop`  
二次补：`POST http://127.0.0.1:8092/api/pending-sso/recover` body `{"count":N}`  
**不要**为了停注册去杀 8010/8080/8317/8318。

## 历史还原点（保留）

1. `stable-2026-07-18`
2. `stable-2026-07-18-sso-mainflow`
3. `stable-2026-07-18-matrix-uifallback`
4. `stable-2026-07-18-pending-18r3` / 多枚 `stable-2026-07-19-*`（18r16…18r28h）
5. **`stable-2026-07-19-docs-sync-18r28i`（当前文档同步点）**
