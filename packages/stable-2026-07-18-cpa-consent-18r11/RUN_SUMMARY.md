# RUN SUMMARY — 18r11

- 8092 仅单独重启；8010/8080/8317/8318 PID 全程保持不变。
- `unittest`: 13 passed。
- `pytest`: 24 passed。
- 官方 device-code 端点单次直连：HTTP 200，首试成功，约 1.66 秒。
- 已有已授权 SSO 单次 authcode 验证：成功。
  - 快速阶段扫描 12 个 chunk 未发现 Action。
  - 自动扩展至 40 个 chunk，动态解析 2 个候选。
  - 跳过非 allow 候选，后续动态候选返回 authorization code。
  - access token 与 refresh token 均成功生成，未写入本报告。
- `/api/stop` 在无任务状态返回正常，五个服务 PID 均保持不变。
- 未执行批量账号注册、批量验证码或代理矩阵账号创建。
