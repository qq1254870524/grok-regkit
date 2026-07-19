## 2026-07-19r29 / restore: stable-2026-07-19-matrix-singlethread-18r29

- **单线程稳定版**全矩阵实跑：`tools/matrix_cross_run.py 10 720`（hybrid/browser × direct/socks5_list × outlook/aol + pending_sso×2），每格 10 轮，`count=1`。
- **Outlook 1078**：`identity/confirm` + `error.aspx?errcode=1078` → `identity_confirm_blocked` permanent，立即删池，禁止 12 步空转。
- 主路径不变：注册成功 → 即时 SSO → g2a/Sub2API/CPA/NSFW；pending 仅兜底；日志应用内明文。
- **18r29b**：browser `early_no_new_mail`/验证码超时 → `burn_mailbox_to_pending` + 删池，与 hybrid 对齐。
- **18r29c**：`sub2api_client.import_grok_sso` 对上游 429/rate-limit 退避重试 5 次（5/12/25/40/60s）；Sub2API `sso_device.go` device/code 429 退避。
- **18r29d**：矩阵 classify 优先识别 pending burn 标记，避免 early_no 覆盖 pending。
- **18r29k**：后处理顺序 NSFW→G2A→CPA→Sub2API；`import_after_success_prefer_cpa` 优先 CPA OAuth 入 Sub2API，失败落盘 + `backfill_missing_sub2api_from_cpa_and_sso`；`reconcile_pools` 对账 TXT/token/G2A/Sub2API/CPA；Web 热加载后 Sub2API 导入不再因旧模块缺符号失败。
- **18r29j**：pending 仅一次登录；失败 hybrid 重注册；矩阵 guardian 同 OUT 续跑。
- **18r29e**：browser 路径 `pending_sso:*` 异常计入 pending 而非 fail，结束日志带 pending_sso 计数。
- **18r29f**：burn 成功即累计 pending_sso；burn 后空失败/页未就绪不硬 fail；矩阵 run_one 以日志 burn 标记优先归 pending。
- 矩阵产物：`matrix_runs/matrix_18r29_*` + `REPORT.md`；Packages **新增**本 tag（不覆盖历史）。



## 18r29 live matrix summary

- `browser__direct__aol`: ok=10/10 classes={'success': 10}
- `browser__direct__outlook`: ok=7/10 classes={'success': 7, 'early_no_new_mail': 3}
- `browser__socks5_list__aol`: ok=8/10 classes={'profile_fill_fail': 1, 'success': 8, 'unknown': 1}
- `browser__socks5_list__outlook`: ok=6/10 classes={'success': 6, 'pending_sso': 1, 'early_no_new_mail': 1, 'sso_timeout': 2}
- `hybrid__direct__aol`: ok=10/10 classes={'success': 10}
- `hybrid__direct__outlook`: ok=10/10 classes={'success': 10}
- `hybrid__socks5_list__aol`: ok=10/10 classes={'success': 10}
- `hybrid__socks5_list__outlook`: ok=9/10 classes={'success': 9, 'pending_sso': 1}
- `pending_sso_recovery__direct`: ok=8/10 classes={'success': 8, 'email_login_fail': 2}
- `pending_sso_recovery__socks5_list`: ok=9/10 classes={'success': 9, 'sso_timeout': 1}

- summary_rows=104 global_classes={'success': 87, 'empty_log': 3, 'pending_sso': 2, 'early_no_new_mail': 4, 'runner_exception': 1, 'sso_timeout': 3, 'profile_fill_fail': 1, 'unknown': 1, 'email_login_fail': 2}
- marked=2026-07-19T11:49:15
