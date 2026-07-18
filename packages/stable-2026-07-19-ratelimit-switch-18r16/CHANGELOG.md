# stable-2026-07-19-ratelimit-switch-18r16

Date: 2026-07-19

## Why
用户报「发送到此邮箱的验证码过多」：同一邮箱 CreateEmail 双发（UI re-click / harvest + protocol-rescue），限流后仍空等或未换邮箱。要求：
1. 日志禁止脱敏、尽量详细
2. 限流后立即换下一邮箱
3. 成功删池入 accounts_hybrid
4. 失败/验证码超时删池入 accounts_registered_pending_sso.txt
5. 矩阵实跑；Packages/Releases 只新增不覆盖

## Root cause
1. browser 假 200 / actual_send 后 protocol-rescue 二次 CreateEmail
2. freeze-reclick 在 net_hits/actual_send 已有时仍可能 re-click
3. 限流只在 protocol strings 粗匹配；browser UI 正文未检测
4. 限流后仅 remove_pool + STATUS_FAIL，未 burn pending，job 也不立刻换邮箱

## Fix (18r16, 含 r14/r15 已合入)
1. `detect_create_email_rate_limit`：protocol strings + browser UI body 检测「验证码过多 / too many / minute+retry」
2. `handle_create_email_rate_limited`：burn_mailbox_to_pending(reason=create_email_rate_limited) + STATUS_PENDING_SSO(rate_limited/switch_mailbox)
3. job 循环：rate_limited 时 IMMEDIATE switch（不消耗 success target slot）
4. actual_send>=1：跳过 re-click 与 protocol-rescue（防双发）
5. token_harvester：UI body rateLimited/bodyText；hard_no_reclick 含 actual_send/net_hits/ui_rate_limited
6. 成功仍：即时 SSO→入池→删邮箱池→accounts_hybrid；失败/超时 burn→pending_sso
7. 日志明文（含 mail_token/password/rate-limit evidence 全文）

## Files
- sources/hybrid_register.py
- sources/browser/token_harvester.py
- sources/outlook_mail.py (r15 adaptive poll / folder dedupe 已在权威目录)
- sources/aol_mail.py

## Verification (live 2026-07-19)
- py_compile hybrid_register.py + browser/token_harvester.py OK
- detect smoke：验证码过多 / too many → True；normal → False
- 仅重启 8092；8010/8080/8317/8318 保持
- matrix hybrid__direct__outlook r1：
  - actual_send=2 后 skip re-click（防再发）
  - code=RYIFQH VerifyEmail=200
  - protocol SignUp sso_len=2477 → session sso len=152
  - success=1 fail=0 pending_sso=0
  - Outlook 池删除 + g2a/Sub2API/CPA 后处理入队
  - class=success elapsed≈140.7s
- 矩阵继续：10 轮 × 10 格（hybrid/browser × direct/socks5 × outlook/aol + pending）

## Do not overwrite
Previous packages kept intact:
- stable-2026-07-18-noreissue-18r9
- stable-2026-07-18-matrix-18r10
- stable-2026-07-18-cpa-consent-18r11
- stable-2026-07-18-protocol-restore-18r12
- stable-2026-07-18-consent-maxscan-18r13
- stable-2026-07-18-pending-18r3
