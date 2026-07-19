## 2026-07-19r29 / restore: stable-2026-07-19-matrix-singlethread-18r29

- **单线程稳定版矩阵实跑**：`tools/matrix_cross_run.py 10 720`（hybrid/browser × direct/socks5 × outlook/aol + pending_sso ×2），每组合 10 轮，`count=1` 单任务串行。
- **Outlook 1078 永久剔号**：`outlook_mail.py` 将 `identity/confirm` + `error.aspx?errcode=1078` 归类为 `identity_confirm_blocked`（permanent=True）；`_follow_to_code` 遇 error.aspx/二次 identity 墙立即抛错；acquire 循环凭据类关键词含 1078/identity **立刻删池**（不 120s 冷却）。
- 主路径不变：注册成功 → **立即 SSO → g2a/Sub2API/CPA/NSFW 入池**；pending 仅兜底。
- 日志应用内明文；矩阵产出 `matrix_runs/matrix_18r29_*` + `REPORT.md`。
- Packages/Releases：**新增** `stable-2026-07-19-matrix-singlethread-18r29`（不覆盖历史包）。

