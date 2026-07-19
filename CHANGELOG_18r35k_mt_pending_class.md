# 18r35k — MT pending re-register result classification

## 问题
MT 在 sign-in `auth_error` 时先 `record_fail()`，再 hybrid 重注册。
若 hybrid 返回 `pending_sso`（如 `early_no_new_mail` 已 burn 回 pending），**没有 undo_fail/record_pending**，
统计把「仍在 pending 队列」误记为硬 fail（本轮 4 成功 + 2 假 fail）。

## 修复
- MT `rr_status == STATUS_PENDING_SSO`：`undo_fail()` + `record_pending()`，日志 `fail->pending`
- 成功路径不变：即时 SSO → 移出 pending → G2A/CPA/Sub2

## 验证计划
- pending 小测后再跑 hybrid 矩阵；观察 pending_sso 计数不再吃硬 fail
