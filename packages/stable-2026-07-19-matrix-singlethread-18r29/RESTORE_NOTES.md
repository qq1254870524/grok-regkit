# RESTORE_NOTES — stable-2026-07-19-docs-sync-18r28i

## 这是什么

第 **docs-sync / 18r28i** 还原包：在 **18r28h 业务已验证** 的基础上，完成文档去重、实况 README、MATRIX 终态、Packages 备份，并把关联项目说明对齐到 GitHub。

**不覆盖**任何旧 tag / release / `packages/*`。

## 业务基线（继承 18r28h，未回退）

1. pending 登录：**ONE login submit only**（去掉 submit boost 双重点）
2. CF stuck：inject-only ≤1；≥10s 仍停 sign-in → `auth_error` → **IMMEDIATE hybrid 重注册**
3. 删除 long-wait 回 sign-in 探针
4. 登录失败：关登录浏览器 → hybrid 同邮箱重注册（**禁止再点登录**）
5. 主路径：注册 → **即时 SSO** → 入池；pending 仅兜底

## 本包文件

- `pending_sso_recovery.py` — 18r28h 核心
- `hybrid_register.py` / `grok_register_ttk.py` / `cpa_export.py`
- `web/server.py`
- `CHANGELOG.md` / `README.md` / `MATRIX_REPORT.md` / `STABLE_VERSION.md` / `RESTORE_NOTES.md`

## 实跑摘要（18r28h）

- pending recovery ×2 Outlook SOCKS5 → success=1 fail=1
- 成功样例：`iveansowparejasir@outlook.com` 即时 SSO + Sub2API
- 失败样例：`juliostangoc@outlook.com` `early_no_new_mail` 回 pending（邮箱侧无信，非登录双重点问题）

## 还原步骤

1. 备份当前目录自定义 `config.json` / 账号池 / `cpa_auths`
2. `git fetch mygithub --tags && git checkout stable-2026-07-19-docs-sync-18r28i` 或解压本 zip 覆盖同名文件
3. 重启仅 Web（8092）；其它服务保持
4. 健康检查：8010 / 8080 / 8092 / 8317 / 8318 LISTEN

## 关联发布

| 仓 | 同步内容 |
|----|----------|
| grok-regkit | 本 tag + package zip |
| sub2api | Grok OAuth 429 多账号切换 + docs restore |
| grok-regkit-services | 端口/还原点文档对齐 18r28i |
| grok2api / turnstile-harvester1 | 配套 release notes（不覆盖旧资产） |
