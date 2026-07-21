# 本机运行

```bash
cd grok-regkit
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
```

编辑 `config.json`：

1. 邮箱：`email_provider` + Cloudflare/DuckMail 等密钥  
2. 代理：`proxy_mode` / `proxy`  
3. 模式：`register_mode` = `browser` 或 `hybrid`  
4. CPA：默认 `cpa_export_enabled=true`，产物在 `cpa_auths/`

运行：

```bash
# Web
uvicorn web.server:app --host 127.0.0.1 --port 8092

# CLI（仍会启动 Chromium）
python grok_register_ttk.py --cli
```

可选环境变量（号池联动）：

```text
GROK2API_INTERNAL_URL=http://127.0.0.1:8010
GROK2API_PUBLIC_URL=http://127.0.0.1:8010
GROK_REGISTER_ACCESS_PASSWORD=   # Web 访问密码，空则不鉴权
```

存量账号补 OIDC：

```bash
python scripts/backfill_cpa_xai_from_accounts.py
```

凭证说明：[docs/sso-cpa/](./docs/sso-cpa/)。

## 存量 CPA 导入 Sub2API

CPA 目录文件是 OAuth 凭证包（`access_token`/`refresh_token`），不是 SSO。
官方 Sub2API 网页「导入数据」**不直接接受** `xai-*.json`；请用下面客户端导入，或先转换。

```bash
# 解析检查（不调用 API）
python -B scripts/import_cpa_to_sub2api.py --dir "C:\Users\zhang\Desktop\Grok\cpa" --dry-parse --limit 3

# 批量导入（推荐，走 /api/v1/admin/accounts；默认不逐个 verify，加快）
python -B scripts/import_cpa_to_sub2api.py --dir "C:\Users\zhang\Desktop\Grok\cpa"

# 单文件并验证
python -B scripts/import_cpa_to_sub2api.py --file "C:\Users\zhang\Desktop\Grok\cpa\xai-xxx.json" --verify

# 转成网页「导入数据」可用的备份格式
python -B scripts/convert_cpa_to_sub2api_data.py --file "C:\Users\zhang\Desktop\Grok\cpa\xai-xxx.json" --out sub2api_data.json
python -B scripts/convert_cpa_to_sub2api_data.py --dir "C:\Users\zhang\Desktop\Grok\cpa" --out sub2api_data_bundle.json
```

Web：保存 Sub2API 管理员配置后，在 CPA 目录框填路径，点「导入 CPA 到 Sub2API」。

