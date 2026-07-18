# CHANGELOG — stable-2026-07-18-matrix-18r10

日期: 2026-07-18
Tag: stable-2026-07-18-matrix-18r10

## 相对 18r9 的改动
1. dual-code 真发送锁（token_harvester）
   - fetch/XHR 首次 CreateEmail 后 short-circuit 重复网络发送
   - actual_send_count / blocked_duplicate_count 可观测
   - UI click send-lock + 控件 lock
2. CPA consent 加速（sso_to_auth_json）
   - JS 扫描预算 10s / max 12 / timeout 8s
   - cache-first；action 试前 5 个
3. SSO materialize 分段日志（hybrid_register + protocol/sso_util）
   - stage=start/browser_nav/browser_done 等

## 主路径约束（未改变）
- 注册成功 → 当时即时 SSO → 入池
- pending 仅兜底；成功后才移出 pending 文件
- 停止注册只停 8092 任务，不动 8010/8080/8317/8318
- 不覆盖历史 restore tag/package

## 实跑（18r10）
- hybrid + SOCKS5 + AOL count=1
- success=1 fail=0 pending_sso=0
- CreateEmail: net_hits=2 raw=2 actual_send=0 blocked_dup=0 sent=True（真发送锁生效；仅一次业务发送）
- VerifyEmail 200 → Turnstile → weak castle early-abort → reuse CreateEmail castle
- SignUp protocol 200 sso_len=2477 → materialize session 152 (~27s)
- immediate SSO+pool path elapsed≈148s
- NSFW OK；G2A remote add OK；Sub2API account created（新号 chat 403 属上游瞬态，创建成功）
- CPA consent 仍可能 fallback（hardcoded next-action 404），后台继续 device/protocol；**不影响主注册/SSO/入池成功**
- archive: Desktop/codex_aidate_tmp/matrix_runs/20260718_18r10_hybrid_socks5_aol
