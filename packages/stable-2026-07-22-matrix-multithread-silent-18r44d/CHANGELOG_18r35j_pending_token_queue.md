# 18r35j — pending queue mail_token prefer + no-token archive

## 问题
1. `load_pending_sso_accounts` 按「首次出现 email」去重：同邮箱若先有无 `b64` 旧行、后有完整 `b64` 行，**有 token 行被丢掉**（实测 lost_tok_dups≈74）。
2. 队首大量历史 AOL 无 `mail_token`（池已 burn 删掉），pending 登录 `auth_error` 后 hybrid 重注册被 `skip forced re-register missing mail_token` 卡住，队列不前移有效 Outlook。
3. 小测 6/6 全撞无 token AOL → 0 成功。

## 修复
- `load_pending_sso_accounts`：同 email **保留 mail_token 最长/最完整** 的一行；队列 **有 token 优先**，无 token 沉底。
- 新增 `archive_pending_no_mail_token`：重注册缺凭据时从 `accounts_registered_pending_sso.txt` 移到 `accounts_pending_no_mail_token_archive.txt`（保留账密供人工），**不堵队首**。
- serial/MT 两条 skip 分支统一 archive + `detail=skip_reregister_no_mail_token_archived`。
- job 启动日志：`with_mail_token` / `no_mail_token` + queue head。

## 验证
- 加载 152 去重账号：with_tok 123→**127**；head 变为 Outlook+b64（toklen≈2k）；order_bad=0。
- 编译通过。

## 主路径不变
注册成功 → 即时 SSO → NSFW → G2A → CPA → Sub2；pending 仅兜底。
