# 18r35b — 验证码过多 / 多 worker 同邮箱 热修

## 现象
- 页面/日志提示：发送到此邮箱的验证码过多，请在 N minutes 后重试
- browser×10 Outlook 格：大量 early_no_new_mail，同一邮箱被多个 worker 同时 poll

## 根因
1. `outlook_mail.get_pool` 把 `config.outlook_accounts` **全文**放进 pool signature；
   删号/同步写回 config 后 signature 变化 → **重建 pool** → 所有 `in_use` 清空。
2. 多线程于是再次 `acquire` 到同一邮箱，同时对 xAI CreateEmail 发码。
3. hybrid 侧 `force_reload=True` 取 token 也会触发重建。
4. browser 路径提交邮箱后**没有**检测「验证码过多」UI，继续空等收信 → 看起来像验证码问题。

## 修复
- Outlook/AOL：`get_pool` 重建时 **preserve in_use/cooldown/tokens**；Outlook sig 不再含 accounts 文本。
- hybrid token lookup：**不再 force_reload**。
- browser：`fill_email_and_submit` 提交后检测 rate-limit UI，立刻 `create_email_rate_limited` 换号；
  resend 前同样检测，禁止对已限流邮箱再点重发。

## 验证
- AST_OK 四文件
- 新 job importlib.reload 后生效（不必杀 8092）
