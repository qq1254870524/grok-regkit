# 临时邮箱适配说明

注册机取号 = **建地址** + **轮询验证码**。  
`email_provider` 决定走哪套 API；**browser / hybrid 共用**同一入口（`get_email_and_token` / 收信）。

---

## 本项目已支持

| `email_provider` | 配置项 | 说明 |
|------------------|--------|------|
| `cloudflare` | `cloudflare_api_base`，可选 `cloudflare_api_key` / `cloudflare_auth_mode` | [Cloudflare Temp Email](https://github.com/dreamhunter2333/cloudflare_temp_email) 兼容 Worker（路径可配） |
| `duckmail` | `duckmail_api_key` | DuckMail（`https://api.duckmail.sbs`） |
| `yyds` | `yyds_api_key`，可选 `yyds_jwt` | [YYDS Mail](https://vip.215.im/docs)：拉域名 → 建地址 → 轮询邮件取码 |
| `outlook` | `outlook_accounts` / `outlook_accounts_file` | 微软邮箱 password+TOTP 或 refresh_token；Graph 收信 |

Web 控制台页签：Cloudflare / DuckMail / YYDS / Outlook / 公共临时邮箱。

### YYDS 示例

```json
"email_provider": "yyds",
"yyds_api_key": "your-key",
"yyds_jwt": ""
```

### Cloudflare 示例

```json
"email_provider": "cloudflare",
"cloudflare_api_base": "https://your-worker.example.com",
"cloudflare_auth_mode": "none",
"cloudflare_api_key": ""
```

路径默认：`/api/domains`、`/api/new_address`、`/api/token`、`/api/mails`（可在配置里改）。

---

---

## Outlook / Microsoft（本项目已实现）

| `email_provider` | 配置项 | 说明 |
|------------------|--------|------|
| `outlook`（别名 `microsoft` / `hotmail` / `ms_outlook`） | `outlook_accounts` 或 `outlook_accounts_file`，可选 `outlook_client_id` / `outlook_token_cache` | 自有微软邮箱池；密码+TOTP 或 refresh_token；Microsoft Graph `Mail.Read` 收信 |

### 账号行格式

```text
# 推荐：密码 + Authenticator TOTP
user@outlook.com----password----BASE32TOTPSECRET

# 可选带 client_id
user@outlook.com----password----BASE32TOTPSECRET----9e5f94bc-e8a4-4e73-b8be-63364c29d753

# 已有 refresh_token
user@outlook.com----9e5f94bc-e8a4-4e73-b8be-63364c29d753----0.AXoA...refresh...
user@outlook.com----0.AXoA...refresh...
```

分隔符支持 `----` / `|` / 制表符 / 逗号。

### 登录与收信流程

1. OAuth authorize（native client redirect）
2. 两步密码：先提交邮箱，再提交密码
3. MFA：`type=19` + TOTP `otc` + Authenticator proof
4. Consent 跟随后换 `access_token` / `refresh_token`
5. `GET https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages` 轮询验证码
6. `refresh_token` 写入本地 `outlook_token_cache.json`（**勿提交 Git**）

### 配置示例

```json
"email_provider": "outlook",
"outlook_accounts_file": "outlook_accounts.txt",
"outlook_accounts": "",
"outlook_client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
"outlook_token_cache": "outlook_token_cache.json"
```

Web：邮箱来源 Tab 选 **Outlook**，在文本框粘贴账号池后点保存。

### 限制

- 个人微软账号需开启 Authenticator / 可用 TOTP；纯短信可能无法自动过 MFA
- 不使用 IMAP basic（个人号常失败）；不使用 ROPC password grant
- 账号池并发时同一邮箱会标记 `in_use`，避免抢号
- 密钥文件 `outlook_accounts.txt` / `outlook_token_cache.json` 默认 gitignore

## 适配参考（chatgpt2api 注册邮箱栈）

本仓库**当前未全部实现**下列类型；下列来自本地维护的 ChatGPT 注册机  
`chatgpt2api`（`services/register/mail_provider.py`）的 **type 清单与运维经验**，便于后续扩展或对照配置。

### 对方已实现的 type

| type（chatgpt2api） | 能力摘要 | 与本项目关系 |
|---------------------|----------|----------------|
| `cloudflare_temp_email` | CF Worker 临时邮 | ≈ 本项目 `cloudflare` |
| `duckmail` | DuckMail API | ≈ 本项目 `duckmail` |
| `yyds_mail` | YYDS 建号 + 收信 | ≈ 本项目 `yyds` |
| `gptmail` | GPTMail（额度/public key 等） | 未接入，可参考扩展 |
| `moemail` | MoeMail | 未接入 |
| `cloudmail_gen` | CloudMail 类生成 | 未接入 |
| `tempmail_lol` | Tempmail.lol | 未接入 |
| `ddg_mail` | DuckDuckGo 别名邮 | 未接入 |
| `inbucket` | 自建 Inbucket | 未接入 |
| `outlook_token` | Outlook/Hotmail **OAuth refresh_token** 读信 | 已由本项目 `outlook` provider 覆盖（见下节） |

### 可借鉴的运维点（实现新 provider 时）

| 经验 | 说明 |
|------|------|
| **YYDS 域名黑名单** | 某域名收码超时后拉黑，避免反复踩死域名；可持久化 `yyds_domain_blacklist.json` |
| **YYDS 白名单** | 成功域名记入白名单，优先选用 |
| **Outlook token 池** | 账号 `used` / `in_use` / `token_invalid` 状态机，防并发抢同一邮箱 |
| **Outlook 别名** | `user+tag@outlook.com` 与主号占用联动 |
| **收信代理分离** | 注册代理与「拉邮件 API」代理可拆开（`mail_fetch_proxy`），避免邮箱 API 走错出口 |
| **OTP 解析** | 主题 + HTML + 纯文本多路正则；Grok/xAI 邮件文案可能与 OpenAI 不同，扩展时需加关键词 |
| **独立 Outlook 模块** | `outlook_mail_fetcher.py`：Graph / IMAP + XOAUTH2 + 代理，可拷贝改造后挂 `email_provider=outlook` |

Outlook 独立说明见 chatgpt2api 仓内：`outlook_mail_fetcher_README.md`（Graph + `Mail.Read` + `offline_access`）。

---

## 扩展新邮箱时建议接口

对齐现有分支即可（概念上）：

1. **create**：返回 `(email_address, mail_token_or_session)`  
2. **poll_code(email, token, timeout)**：等到 xAI 验证码或超时  
3. 在 `get_email_provider()` / Web 页签 / `config.example.json` 增加一项  

验证码提取需覆盖 xAI 邮件模板（不要只抄 OpenAI 关键词）。

---

## 配置入口

| 位置 | 作用 |
|------|------|
| `config.json` → `email_provider` | 当前后端 |
| Web「邮箱来源」 | 切换 Cloudflare / DuckMail / YYDS |
| `config.example.json` | 字段模板 |

browser 与 hybrid **不需要**为邮箱再选一遍模式。

---

## 公共无 Key 临时邮箱（2026-07-17 增补）

| `email_provider` | 说明 |
|------------------|------|
| `mailtm` / `mail.tm` | [Mail.tm](https://mail.tm) 公开 API |
| `tempmail_lol` / `tempmail.lol` | [TempMail.lol](https://tempmail.lol) v2 |
| `tempmail_plus` / `tempmail.plus` | [TempMail.plus](https://tempmail.plus) 随机 free 域 |
| `tempmail_io` | Temp-Mail.io |
| `linshiyouxiang` | 临时邮箱.net |
| `boomlify` | Boomlify |
| `tempmail_org` | Temp-Mail.org（常被 CF） |

完整探测清单见 [public-temp-email-catalog.md](./public-temp-email-catalog.md)。