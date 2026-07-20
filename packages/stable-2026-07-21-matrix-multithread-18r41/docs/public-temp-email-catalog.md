# 公开临时邮箱目录（2026-07-17 实探测）

本机经 `http://127.0.0.1:7897` 代理探测。状态仅代表探测当时。

## 已接入 grok-regkit（`email_provider`）

| provider | 站点/API | 是否要 key | 实测建箱 | 实测列表 | 说明 |
|----------|----------|------------|----------|----------|------|
| `tempmail_io` | https://temp-mail.io · `api.internal.temp-mail.io` | 否 | OK | OK | 已有实现 |
| `linshiyouxiang` | https://www.linshiyouxiang.net | 否 | 视风控 | 视风控 | 已有实现 |
| `boomlify` | https://boomlify.com · `v1.boomlify.com` | 否 | 视风控 | 视风控 | 已有实现 |
| `tempmail_org` | https://temp-mail.org | 否 | 常被 CF 拦 | - | best-effort |
| **`mailtm`** | https://mail.tm · `api.mail.tm` | 否 | **OK** | **OK** | **v3 新接入**，推荐备用 |
| **`tempmail_lol`** | https://tempmail.lol · `api.tempmail.lol` | 否 | **OK** | **OK** | **v3 新接入** |
| **`tempmail_plus`** | https://tempmail.plus | 否 | **OK** | **OK** | **v3 新接入**，随机 `*@mailto.plus` 等 |
| `cloudflare` | 自建 Worker | 可选 | 自建 | 自建 | 需自己部署 |
| `duckmail` | DuckMail API | 要 | - | - | 需 api key |
| `yyds` | vip.215.im | 要 | - | - | 需 api key |

### 配置示例

```json
"email_provider": "mailtm"
```

可选：`tempmail_lol` / `tempmail_plus` / `tempmail_io` …

Web/桌面「邮箱服务商」下拉已同步。

## 公开候选（未接入或不可用）

| 名称 | 入口 | 实测 | 备注 |
|------|------|------|------|
| Mail.gw | `api.mail.gw` | 502 | 当时挂了 |
| 1secmail | `1secmail.com/api/v1` | 403 | 当前封 API |
| Guerrilla / Sharklasers | guerrillamail / sharklasers | 超时/SSL | 不稳定 |
| Dropmail.me GraphQL | dropmail.me/api/graphql | 403 legacy_token_disabled | 需新 token 方案 |
| TempMail.plus | tempmail.plus/api | OK | **已接入** |
| Inboxes.com | inboxes.com/api/v2 | 200 空箱 | 可后续接 |
| EmailOnDeck / FakeMailGenerator | 网页 | 200 HTML | 无干净公共 API |
| Getnada 旧 API | getnada.com/api/v1/domains | 404 | 路由已变 |
| MailForSpam / Throwaway / TmpMail | - | SSL 失败 | 暂不接 |

## 其它常见公开站（网页型，未做 API 适配）

- https://yopmail.com/
- https://www.minuteinbox.com/
- https://tempail.com/
- https://www.moakt.com/
- https://smailpro.com/
- https://tempmailo.com/
- https://etempmail.com/
- https://www.emailnator.com/
- https://www.mailinator.com/（公共 inbox 可猜地址）
- https://guerrillamail.com/
- https://www.fakemailgenerator.com/
- https://emailondeck.com/

## 选用建议

1. **优先有 key 的稳源**：`yyds` / `duckmail` / 自建 `cloudflare`
2. **无 key 公共源轮换**：`mailtm` → `tempmail_lol` → `tempmail_plus` → `tempmail_io`
3. 公共域容易被 xAI/Grok 拒投或进垃圾箱；失败就换 provider
4. 收信建议走与注册相同或可通的代理（SOCKS5 池可在 Web 里保存）

## 冒烟命令

```powershell
cd C:\Users\zhang\grok-regkit
$env:HTTPS_PROXY='http://127.0.0.1:7897'
python -B -c "import temp_email_public_providers as p; print(p.smoke_test_provider('mailtm', proxies={'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}))"
python -B -c "import temp_email_public_providers as p; print(p.smoke_test_provider('tempmail_lol', proxies={'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}))"
python -B -c "import temp_email_public_providers as p; print(p.smoke_test_provider('tempmail_plus', proxies={'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}))"
```