# CHANGELOG 18r19 — consent soft-nav fix + incomplete envelope

## 用户问题 A：consent 失败一直重试
日志：`consent 失败，重新进入 authorize/consent 并解析 Next-Action...`
根因：Next-Action `0071fd1191ff...` 是 RSC soft-nav（`0:{"a":"$@1","q":"?response_type=code..."}`），无 authorization code。
旧逻辑：非 allow 不拉黑、strong_id 早停、只试前 5 个 → 每轮卡死同一 action。
CPA 只能 fallback protocol，`referrer=None`，free grok-4.5 可能失败。

## 用户问题 B：点注册弹 `[invalid_argument] protocol error: incomplete envelope`
根因：18r18 CreateEmail 双发锁对第 2+ 次返回假 JSON `{"blocked_duplicate":true}`（fetch 200 / XHR responseText）。
React/Connect 按协议解析 → incomplete envelope toast。
首发仍可能成功，但页面必弹错。

## 18r19 修复
### sso_to_auth_json.py
- 识别 soft-nav / incomplete envelope 为非 allow
- 非 allow **拉黑** Next-Action 并继续试
- `action_ids[:12]`，round 3；不强因 1 个 strong_id 早停
- `_parse_consent_code` 支持 query / RSC `q=` 内嵌 `code=`
- 实机：拉黑 0071fd1191ff → `404454cfbd85` 返回 code → `mint_method=authcode_pkce` `referrer=grok-build`

### browser/token_harvester.py
- blocked_duplicate 改为 `AbortError` / XHR abort
- **禁止** 假 JSON body（避免 incomplete envelope）
- 首发 CreateEmail 仍放行；`actual_send=1 blocked_dup=1` 仍可收码注册

## 验证
- 单元测试 ALL PASSED
- 正式路径 sso_to_token SUCCESS referrer=grok-build
- 实机 hybrid 后处理：soft-nav 拉黑 + authcode_pkce + referrer=grok-build
- 最近日志 incomplete envelope hits=0

## 与 18r18 关系
- 继承 dual-send 首发放行锁
- 仅修正锁的「假响应」实现 + CPA consent 拉黑/深扫

## 矩阵（并行，不杀）
目录：matrix_runs/matrix_18r14_20260719_004422
见 runner.log；Agent 分工见 AGENT_COORD.md

## 服务约束
勿杀：8010 Grok2API / 8080 Sub2API / 8317 CLIProxy / 8318 CPA Gateway
仅可重启：8092 regkit web
