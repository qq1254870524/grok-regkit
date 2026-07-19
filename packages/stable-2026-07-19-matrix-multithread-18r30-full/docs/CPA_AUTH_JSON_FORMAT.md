# CPA auth JSON 格式说明（未改 schema）

`cpa_auths/xai-*.json` **字段集合始终是 17 键扁平 xAI OAuth**，与最早版本一致：

type, auth_kind, email, sub, access_token, refresh_token, id_token,
token_type, expires_in, expired, last_refresh, redirect_uri,
token_endpoint, base_url, disabled, headers, sso

## 为什么看起来“格式变了”？

1. **pretty（缩进）**：`sso_to_auth_json.write_cpa_auth` 用 `json.dumps(..., indent=2)` 写出，键顺序为写入时的插入序（type 在前）。
2. **compact（单行/字母序）**：CLIProxyAPI 的 `auth-dir` 指向同一 `cpa_auths` 目录，热加载/刷新后会用 Go 侧 `sort_keys` 风格重写为紧凑 JSON，键按字母序，`access_token` 会排到最前。

示例：
- `xai-anna_madsen@aol.com.json` / `xai-misspafosindia@aol.com.json` → pretty，write_cpa_auth 原样
- `xai-jakublavigne@aol.com.json` → compact 字母序，CLIProxy 重写后

**兼容性**：Sub2API / CLIProxy / CPA Gateway 都按字段名解析，pretty/compact 不影响使用。
