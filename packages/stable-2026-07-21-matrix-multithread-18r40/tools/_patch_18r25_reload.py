from pathlib import Path
p = Path("web/server.py")
t = p.read_text(encoding="utf-8")
old = '''            # Prefer freshly loaded hybrid path helpers when modules were patched mid-process.
            try:
                import importlib
                import hybrid_register as _hy
                importlib.reload(_hy)
            except Exception:
                pass
'''
new = '''            # Prefer freshly loaded path helpers when modules were patched mid-process.
            try:
                import importlib
                for _mod_name in (
                    "outlook_mail",
                    "aol_mail",
                    "sub2api_client",
                    "grok_register_ttk",
                    "hybrid_register",
                ):
                    try:
                        _m = importlib.import_module(_mod_name)
                        importlib.reload(_m)
                    except Exception:
                        pass
            except Exception:
                pass
'''
if old not in t:
    raise SystemExit('block not found')
p.write_text(t.replace(old, new, 1), encoding='utf-8')
print('server reload expanded')
