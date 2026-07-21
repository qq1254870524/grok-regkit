# CHANGELOG 18r35 multi-thread matrix

## 参数
- workers / thread_count = **10**
- email_preflight_warm_ahead = **40**
- register_count / rounds per cell = **40**
- 组合：hybrid|browser × direct|socks5_list × aol|outlook + pending_sso_recovery
- 不覆盖既有 Packages：18r30 / 18r31 等历史 tag 保留

## 本次变更
- `tools/matrix_18r30_multithread.py`：默认 WORKERS=10、ROUNDS=40；矩阵格强制 `email_preflight_warm_ahead=40`、`email_preflight_limit=max(40, workers*4)`
- 恢复 `socks5_proxies.txt`（7 条）并写入 config `proxy_list`
- 临时邮箱冒烟（不注册）：`matrix_runs/temp_email_smoke_20260720_003836.json` → **14/16 OK**
  - OK：boomlify / linshi / linshiyouxiang / mail.tm / mailtm / temp-mail.io / temp-mail.org / tempmail.lol / tempmail.plus / 别名键 / duckmail
  - FAIL（缺配置）：yyds（无 API Key/JWT）、cloudflare（无 API Base）

## 运行中
- 矩阵 stamp：`20260720_003737`
- 报告：`matrix_runs/matrix_18r30_20260720_003737.jsonl`
- 监控：`_live_pulse_18r35.txt` / `_matrix_18r35_watchdog.py`

## 发版计划（矩阵全部完成后）
- 新 tag：`stable-2026-07-20-matrix-multithread-18r35-w10-r40`
- 新 Package/Release zip + 本 CHANGELOG；**不覆盖** 18r30/18r31

## Final (20260720_022806)
- tag: `stable-2026-07-20-matrix-multithread-18r35-w10-r40`
- `hybrid__direct__outlook` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `hybrid__socks5_list__aol` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `hybrid__socks5_list__outlook` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `browser__direct__aol` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `browser__direct__outlook` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `browser__socks5_list__aol` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `browser__socks5_list__outlook` success=None fail=None pending=None err=HTTP Error 409: Conflict
- `pending_sso_recovery` success=None fail=None pending=None err=HTTP Error 409: Conflict
