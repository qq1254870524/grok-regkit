# 验证码过多 根因说明 (18r35k live)

## 现象
xAI 页面文案: 发送到此邮箱的验证码过多。请在 N minutes 后重试。

## 根因
- **不是**邮箱 IMAP/Graph 坏了，而是 **xAI CreateEmail 对该邮箱/该出口 IP 的发码频控**。
- 常见触发：
  1. 同一邮箱短时间多次点「发送验证码 / CreateEmail」
  2. 多线程并行多个浏览器同时 CreateEmail（同 IP）
  3. 收不到信后又自动 resend / 重点注册按钮导致双发
  4. 历史 pending 对同一邮箱反复 re-register

## 已有防护 (18r35b/c/k)
1. 页面检测 `验证码过多` / too many verification → **burn 该邮箱 + 换下一号**，不盲重试同邮箱
2. 全局 CreateEmail gate，worker 间最小间隔 **4.0s**
3. 已进入验证码步骤且页面已限流 → **禁止 resend**
4. 防双发：skip re-click 日志

## 本轮实跑 (browser/direct/outlook workers=3 count=6)
- 结果：**成功 6 / 失败 0 / pending 0**
- 本轮 **0 次** RATE_LIMIT / 验证码过多 硬失败
- 有 1 次 Outlook `early_no_new_mail`（真无新信）→ burn/switch 后下一邮箱 `doriadenise7mu` 成功收码并完成 SSO 入池
- 主路径确认：注册成功 → 即时 SSO → G2A/Sub2/CPA（account_id 1082–1084 一带）

## 策略（不动主路径）
限流/无信 → **换邮箱**；成功号即时 SSO 入池；失败/超时 burn 出池并可进 pending 二次补（仅兜底）
