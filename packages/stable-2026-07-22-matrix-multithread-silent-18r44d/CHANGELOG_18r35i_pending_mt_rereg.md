# 18r35i — pending MT 补齐 hybrid 重注册

## 根因
`pending_sso_recovery` 串行路径在 auth_error 后会 `register_one_hybrid`，但 **MT `_worker` 只 `coord.record_fail()`**，从不重注册 → 日志只有 IMMEDIATE re-register 字样，实际直接换下一个 pending。

## 修复
- `pending_sso_recovery.py` MT worker：auth_error/bad_password/no-sso 等走与串行一致的 hybrid re-register（同邮箱 forced_email + mail_token）
- `worker_coord.JobCoordinator.undo_fail`：重注册成功后回退 fail 计数
- 保留 18r35g/h：stop 清 running、phase 不误 finished

## 注意
- 重注册成功才 `remove_pending_sso_account`
- 缺 mail_token 跳过重注册但保留 pending
