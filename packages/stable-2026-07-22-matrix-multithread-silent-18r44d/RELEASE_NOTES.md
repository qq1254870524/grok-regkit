# stable-2026-07-22-matrix-multithread-silent-18r44d

## 版本定位

多线程**静默稳定**版本 **18r44d**（追加发行，**不覆盖** 18r44c/18r43*）。

构建时间: 2026-07-22T03:55:50

## 本版关键修复

1. **SOCKS5 预检后再开浏览器**
   - `quick_check_proxy` / `pick_live_proxy` / `ensure_live_proxy_before_browser`
   - `start_browser` 启动 Chromium 前强制 LIVE 预检
   - 坏代理冷却 + `mark_proxy_bad`，降低首次 Chromium interstitial
2. **G2A 双目标入池（8010 + 8011→8020）**
   - `get_grok2api_remote_targets()` primary + mirror_v3
   - `config.json`: `grok2api_mirror_remote_base` / `grok2api_mirror_remote_app_key`
   - 新注册 SSO 同时写 8010 与桥 8011（v3 8020）
3. **回填工具** `tools/_backfill_8010_to_8011_18r44d.py`
   - 从 8010 拉真实 SSO 分批 POST 到 8011（服务端去重）
4. **矩阵实测** `matrix_18r44c_validate_20260722_031216`
   - 6/6 ok：browser AOL x2、pending_sso_recovery x2、stop_test x2
   - 入池 delta 与 success 对齐（8010/Sub2）

## 配置提示

```json
{
  "grok2api_remote_base": "http://127.0.0.1:8010",
  "grok2api_mirror_remote_base": "http://127.0.0.1:8011",
  "grok2api_auto_add_remote": true
}
```

8020 Go 版不要直接打旧 `/admin/api/tokens*`，走 8011 兼容桥。

## 变更文件（核心）

- grok_register_ttk.py
- worker_coord.py
- tools/_backfill_8010_to_8011_18r44d.py
- web/server.py（stop/status 既有逻辑）

## 校验

- py_compile 通过
- 矩阵 6/6 ok
- 8092 热载：需重启 web 进程后双写生效
