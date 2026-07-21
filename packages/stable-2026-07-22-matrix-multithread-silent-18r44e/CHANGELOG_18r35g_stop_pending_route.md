# 18r35g — stop 立刻清 running + pending 正确路由

日期: 2026-07-20

## 问题
1. `POST /api/stop` 只触发 controller/force_stop，**不把** `_job_state["running"]` 置 False；状态长期 `running=True` / phase 卡在 `waiting_code`，新任务 409，预热仍跑。
2. validate/矩阵脚本把 `job_kind=pending_sso_recovery` 发给 `POST /api/start`，但 start **硬编码** `job_kind=register`，误开注册。
3. pending 正确入口是 `POST /api/pending-sso/recover`。

## 修复
- `web/server.py`
  - `/api/stop`：立刻 `running=False`、phase=stopping→idle；始终 `force_stop_registration`；**不杀** G2A/Sub2/CPA/CLIProxy。
  - `StartBody.job_kind`：`/api/start` 识别 pending 别名并路由到 `pending_sso_recovery`。
- `matrix_runs/_validate_18r35_hotfix.py`：优先 `/api/pending-sso/recover`；若 kind 不是 pending 立即 stop 并报错。

## 验证
- 编译 + 热加载 8092 后测 stop/start job_kind。
- 网关 8010/8080/8317 保持运行。
