import json
from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\config.json")
c = json.loads(p.read_text(encoding="utf-8"))
print("before_provider=", c.get("email_provider"), "mode=", c.get("register_mode"), "proxy=", c.get("proxy_mode"), "workers=", c.get("workers"))
c["email_provider"] = "outlook"
c["register_mode"] = "hybrid"
c["proxy_mode"] = "socks5_list"
c["workers"] = 20
c["thread_count"] = 20
c["register_count"] = 1000
c["email_preflight_on_start"] = True
c["email_preflight_continuous"] = True
c["email_preflight_limit"] = 40
c["email_preflight_warm_ahead"] = 40
c["browser_silent"] = True
c["browser_start_minimized"] = True
c["post_success_async"] = True
c["post_success_workers"] = 6
p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
print("after_provider=", c.get("email_provider"), "mode=", c.get("register_mode"), "proxy=", c.get("proxy_mode"), "workers=", c.get("workers"))
