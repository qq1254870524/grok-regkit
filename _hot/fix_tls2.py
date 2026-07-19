from pathlib import Path
import ast
p = Path("grok_register_ttk.py")
t = p.read_text(encoding="utf-8")
old = (
"            clean_code,\n"
"        )\n"
"\n"
"        if filled == \"not-ready\":\n"
)
new = (
"            clean_code,\n"
"        )\n"
"        except Exception as _fc_exc:\n"
"            em = str(_fc_exc)\n"
"            if (\n"
"                (\"NoneType\" in em and \"run_js\" in em)\n"
"                or \"页面被刷新\" in em\n"
"                or \"PageDisconnected\" in em\n"
"                or \"与页面的连接已断开\" in em\n"
"            ):\n"
"                if log_callback:\n"
"                    log_callback(f\"[!] fill_code page disconnected: {_fc_exc}\")\n"
"                try:\n"
"                    refresh_active_page()\n"
"                except Exception:\n"
"                    pass\n"
"                sleep_with_cancel(0.8, cancel_callback)\n"
"                continue\n"
"            raise\n"
"\n"
"        if filled == \"not-ready\":\n"
)
if old not in t:
    raise SystemExit("fill_code close not found")
t = t.replace(old, new, 1)
p.write_text(t, encoding="utf-8")
ast.parse(t)
print("AST_OK")
print("markers", {
  "fe": "except Exception as _fe_exc" in t,
  "fc": "except Exception as _fc_exc" in t,
  "fp": "except Exception as _fp_exc" in t,
  "soft": "soft open_signup failed" in t,
  "hard": "only hard-restart when browser/page is dead" in t,
  "click": "click_email page disconnected" in t,
})