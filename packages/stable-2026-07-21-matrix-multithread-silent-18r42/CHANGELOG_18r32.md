# 18r32 / preflight UI

## 2026-07-19 邮箱预热网页可配 + 矩阵 409 修复

- 网页「任务参数」新增：
  - `email_preflight_warm_ahead`：预热邮箱数量，**0=自动**（max(6,min(40,workers×4))），可自定义 1–200
  - `email_preflight_limit`：启动预检抽样上限
  - `email_preflight_on_start` / `email_preflight_continuous` 开关
- `worker_coord.start_continuous_preflight`：正数 warm_ahead 按用户值 clamp 1–200，不再被写死
- `tools/matrix_18r30_multithread.py`：`wait_idle` 加长 + 超时后仅停注册；`/api/start` 遇 409 自动重试，避免假 7 格全 Conflict

