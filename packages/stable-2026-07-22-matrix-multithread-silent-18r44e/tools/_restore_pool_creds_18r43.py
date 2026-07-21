import json, shutil, re
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
cfg_path = ROOT / "config.json"
bak = ROOT / "config.json.bak_before_restore_20260719_214745"
g2a_toml = Path(r"C:\Users\zhang\grok-regkit-services1\grok2api1\data\config.toml")
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(cfg_path, ROOT / f"config.json.bak_before_poolfix_{ts}")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
src = json.loads(bak.read_text(encoding="utf-8"))
restored = []
for k in [
    "sub2api_admin_email",
    "sub2api_admin_password",
    "grok2api_remote_app_key",
    "sub2api_base_url",
    "grok2api_remote_base",
]:
    cur = str(cfg.get(k) or "").strip()
    old = str(src.get(k) or "").strip()
    if (not cur) and old:
        cfg[k] = old
        restored.append(k)
if not str(cfg.get("grok2api_remote_base") or "").strip():
    cfg["grok2api_remote_base"] = "http://127.0.0.1:8010"
    restored.append("base_default")
cfg["grok2api_auto_add_remote"] = True
cfg["grok2api_auto_add_local"] = True
cfg["sub2api_auto_add"] = True
cfg["sub2api_verify_after_add"] = False
cfg["sub2api_require_verify_success"] = False
cfg["post_success_workers"] = 12
cfg["register_mode"] = "hybrid"
cfg["proxy_mode"] = "socks5_list"
cfg["email_provider"] = "outlook"
cfg["workers"] = 20
cfg["thread_count"] = 20
cfg["register_count"] = 1000
cfg["claim_mode"] = "attempt"
cfg["register_quota_mode"] = "attempt"
key = str(cfg.get("grok2api_remote_app_key") or "")
if len(key) < 12 and g2a_toml.is_file():
    text = g2a_toml.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'app_key\s*=\s*"([^"]+)"', text)
    if not m:
        m = re.search(r"app_key\s*=\s*'([^']+)'", text)
    if m and len(m.group(1)) >= 12:
        cfg["grok2api_remote_app_key"] = m.group(1)
        restored.append("app_key_from_toml")
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("restored", restored)
print("lens", {k: len(str(cfg.get(k) or "")) for k in ["sub2api_admin_email", "sub2api_admin_password", "grok2api_remote_app_key"]})
print("auto_remote", cfg.get("grok2api_auto_add_remote"), "base", cfg.get("grok2api_remote_base"))
print("cell", cfg.get("register_mode"), cfg.get("proxy_mode"), cfg.get("email_provider"), cfg.get("workers"), cfg.get("register_count"))
