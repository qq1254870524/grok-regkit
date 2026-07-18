# CHANGELOG 18r18 — dualsend-lock

## 用户问题：验证码过多

xAI CreateEmail 对同一邮箱短时间多次发码会返回：
「发送到此邮箱的验证码过多。请在 {count} minute(s) 后重试…」

根因：
1. 表单 `requestSubmit` / React 并发双发 CreateEmail（日志 `actual_send=2`）
2. 历史 re-click / protocol-rescue 二次发信（18r16 已禁）

## 18r18 修复
- **CreateEmail first-send-only 锁**（token_harvester 网络 hook）
  - 第一次 CreateEmail 永远放行
  - 并发/后续第 2+ 次直接 block（返回 blocked_duplicate，计数 blocked_dup）
  - 降低 dual-code 与 rate-limit
- 保留 18r16/r17：
  - rate-limit 检测 → burn 邮箱 → pending_sso → 立即换下一邮箱
  - switch_mailbox 有上限 max(8, count*3)，code_timeout 不再无限 switch
  - 日志禁止脱敏（password/mail_token 明文）
  - 成功 → 删池 + accounts_hybrid_*
  - 失败/超时/过多 → 删池 + accounts_registered_pending_sso.txt
  - 主路径：注册 → 即时 SSO → 入池；pending 仅兜底
  - UI fallback timeout 40s；后处理等待 90s

## 矩阵进度（18r14 目录继续跑，代码已热更至 18r18）
hybrid__direct__outlook 10轮：success 3 / pending 6 / unknown 1
hybrid__direct__aol 进行中

## 服务约束
勿杀：8010 Grok2API / 8080 Sub2API / 8317 CLIProxy / 8318 CPA Gateway
仅可重启：8092 regkit web
