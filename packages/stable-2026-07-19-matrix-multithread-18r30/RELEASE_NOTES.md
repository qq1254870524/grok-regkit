# Release stable-2026-07-19-matrix-multithread-18r30

## 多线程稳定版 18r30

### 新增
- Web 线程数 `regWorkers`（1–32）
- `/api/start` `/api/pending-sso/recover` 传 `workers`
- `worker_coord.JobCoordinator` 槽位锁 + 计数
- SOCKS5 每线程绑定 `pool[(worker_id-1) % n]` 顺序复用
- 启动邮箱预登录（限量 sample + AOL auth-only；失败删池）
- 收信全文件夹、每夹最新 5 封
- 邮箱池 `acquire/in_use` 防双抢账号/验证码

### 不覆盖
- 单线程还原点 `stable-2026-07-19-matrix-singlethread-18r29`

### 主路径
注册成功 → 即时 SSO → NSFW → G2A → CPA → Sub2API；pending 仅兜底。

### 停止
停止注册只关 Chromium，不杀 8010/8080/8317/8318。
