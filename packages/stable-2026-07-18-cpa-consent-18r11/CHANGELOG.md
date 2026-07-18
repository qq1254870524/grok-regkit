# CHANGELOG — 18r11

日期：2026-07-18
基线：stable-2026-07-18-matrix-18r10 / commit 762b85e

1. 修复 18r10 将 consent JS 扫描限制到 12 个脚本后，真实 Action 位于后续 chunk 时错误回退失效哈希并 404 的回归。
2. 动态扫描改为 fast/extended 两阶段；只有实际解析出 Server Action ID 才允许早停。
3. 增强带空格及 webpack 包装形式的 `createServerReference` 解析。
4. 移除 consent 流程中的 hardcoded fallback 自动提交；404 Action 继续进程内拉黑。
5. device-code 请求新增端点、代理路由、attempt、elapsed、异常类型和 transient 分类日志。
6. 网络瞬断采用指数退避；400/401 等业务错误立即返回，不消耗网络重试。
7. 代理日志只保留 scheme/host/port，不输出认证信息。
8. pending SSO 不再调用 `open_signup_page` 作为浏览器 bootstrap，防止恢复任务误走注册页。
9. 新增 6 项定向回归测试并与项目现有测试合并验证。
