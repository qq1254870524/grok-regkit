from pathlib import Path
import ast
p = Path("grok_register_ttk.py")
t = p.read_text(encoding="utf-8")
bad = '''    try:
        page.run_js(
            "try { if (window.turnstile && typeof turnstile.reset === 'function') turnstile.reset(); } catch(e) {}"
        )
        except Exception as _fc_exc:
            em = str(_fc_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] fill_code page disconnected: {_fc_exc}")
                try:
                    refresh_active_page()
                except Exception:
                    pass
                sleep_with_cancel(0.8, cancel_callback)
                continue
            raise
    except Exception:
        pass
'''
good = '''    try:
        page.run_js(
            "try { if (window.turnstile && typeof turnstile.reset === 'function') turnstile.reset(); } catch(e) {}"
        )
    except Exception:
        pass
'''
if bad not in t:
    # show nearby
    i = t.find("def getTurnstileToken")
    print(t[i:i+900])
    raise SystemExit("bad block not found")
t = t.replace(bad, good, 1)
p.write_text(t, encoding="utf-8")
ast.parse(t)
print("AST_OK")
print({
  "fe": t.count("except Exception as _fe_exc"),
  "fc": t.count("except Exception as _fc_exc"),
  "fp": t.count("except Exception as _fp_exc"),
  "soft": "soft open_signup failed" in t,
  "hard": "only hard-restart when browser/page is dead" in t,
  "click": "click_email page disconnected" in t,
  "fill_email_resolve": "fill_email page disconnected" in t,
})