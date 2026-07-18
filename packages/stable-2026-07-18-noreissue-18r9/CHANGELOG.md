# CHANGELOG — stable-2026-07-18-noreissue-18r9

日期: 2026-07-18
Tag: stable-2026-07-18-noreissue-18r9
Commit base: da04991

## 为什么补这个 Package
上一版只写了桌面 RESTORE_*.md 并 push 了 git tag，**没有**把 sources/ 快照提交进仓库 packages/。
本 package 补齐 18r9 完整还原点，**不覆盖**任何既有 tag/package。

## 相对 18r3 的关键修复
- CreateEmail freeze-reclick：sent/2xx/code-step 后禁止二次 click，避免双发码
- mint_fresh_castle weak early-abort：注入弱 token(~744) weak_hits>=3 即停，复用 CreateEmail IBYIll
- 主路径不变：注册 → 即时 SSO materialize → 入池；pending 仅兜底

## 实跑
- hybrid + SOCKS5 + AOL：success=1 pending=0（18r8/18r9）
