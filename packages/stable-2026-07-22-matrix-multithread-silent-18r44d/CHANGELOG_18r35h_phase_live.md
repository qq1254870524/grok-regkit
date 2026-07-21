# 18r35h — phase 不再被「当前统计」误标 finished

- `web/server.py`：只有 `混合任务结束` / `web job thread finished` 才 phase=finished
- 中途 `当前统计` → running 或 pending_sso_recovery
- pending 日志细分 signin / turnstile / reregister
