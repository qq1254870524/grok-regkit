# Restore Package: stable-2026-07-18-cpa-consent-18r11

18r11 是在 `stable-2026-07-18-matrix-18r10` 之后建立的独立还原点，不覆盖任何旧 Package 或 tag。

## 核心修复

- CPA consent Next-Action 两阶段动态扫描：快速 12 个 chunk，未发现有效 Action 时扩展至最多 40 个。
- 不再自动提交已确认失效的 hardcoded Next-Action。
- device-code 对 `RemoteDisconnected`、超时、TLS/代理瞬断做分类重试和指数退避。
- HTTP 4xx 业务错误不进行无意义网络重试，日志不输出代理账号密码、token 或 SSO。
- `browser_confirm` 不再把内部重试额外乘以三轮。
- pending SSO 复用已启动 Chromium 的空白页，直接进入 `/sign-in`，不先打开 `/sign-up`。

## 还原

优先使用 Git tag：

```powershell
git checkout stable-2026-07-18-cpa-consent-18r11
```

也可按原目录结构将 `sources/` 内文件覆盖回项目。旧 Package 与旧 tag 均保留。
