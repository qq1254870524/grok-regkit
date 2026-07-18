# MATRIX_REPORT

## 18r28i docs-sync package

- Tag/package/release: `stable-2026-07-19-docs-sync-18r28i`（文档+全关联同步，不覆盖 18r28h）
- 业务基线代码：18r28h（ONE login / 禁二次登录 / CF≥10s 立即重注册）

## 18r28h live matrix FINAL 2026-07-19 ~05:59

### pending_sso recovery count=2 · SOCKS5 · Outlook

| # | email | 路径 | 结果 |
|---|-------|------|------|
| 1 | juliostangoc@outlook.com | ONE login → auth_error → IMMEDIATE hybrid re-register（无二次登录） | **fail** `early_no_new_mail`（邮箱无新信）→ **保留 pending** |
| 2 | iveansowparejasir@outlook.com | ONE login → auth_error → IMMEDIATE hybrid re-register | **success** SignUp sso + immediate pool；移出 pending；Sub2API sso-to-oauth |

### Job API 终态

```json
{
  "ok": true,
  "running": false,
  "success": 1,
  "fail": 1,
  "pending_sso": 0,
  "target": 2,
  "job_kind": "pending_sso_recovery",
  "phase": "finished",
  "session_success": 5,
  "session_fail": 2
}
```

### 验证关键词（18r28h 后日志）

- `ONE login submit after turnstile`
- `login_submit_done=1 block_refill=1`
- `page_err=auth_error -> IMMEDIATE re-register (NO second login click)`
- `closed sign-in browser before hybrid re-register`
- **无** `submit boost` 二次点登录（仅修复前旧日志出现）

### Git（18r28h）

- commits: `3dfe749` fix + `585f20f` matrix docs
- package/release: `stable-2026-07-19-pending-one-login-18r28h`（保留）

## 18r28g pending no-second-login（历史）

- Tag: `stable-2026-07-19-pending-turnstile-18r28g`
- pending count=2: success=2 fail=0

## 主路径约定（全程不变）

1. 注册成功 → **立即**拿 SSO → 入池（g2a / Sub2API / CPA）
2. `pending_sso` 仅兜底；二次补失败可 hybrid 重注册，**禁止**反复点登录
3. 停注册只停 8092 任务；8010/8080/8317/8318 保持运行
