# -*- coding: utf-8 -*-
"""18r30 patch part1: TLS browser + config workers + thread proxy."""
from pathlib import Path
import re
import py_compile

path = Path("grok_register_ttk.py")
text = path.read_text(encoding="utf-8")
orig_len = len(text)

# --- DEFAULT_CONFIG ---
if '"workers"' not in text.split("DEFAULT_CONFIG", 1)[1][:5000]:
    needle = (
        '    "register_count": 1,\n'
        '    # register_mode: browser (full UI) | hybrid (protocol + short browser tokens)\n'
        '    "register_mode": "browser",'
    )
    repl = (
        '    "register_count": 1,\n'
        '    # 18r30 multithread: web-configurable worker count (1 = serial / same as 18r29)\n'
        '    "workers": 1,\n'
        '    "thread_count": 1,\n'
        '    # mail poll: ALL folders, only newest N messages per folder\n'
        '    "mail_top_per_folder": 5,\n'
        '    # job-start preflight login for outlook/aol pools (drop bad mailboxes)\n'
        '    "email_preflight_on_start": True,\n'
        '    # register_mode: browser (full UI) | hybrid (protocol + short browser tokens)\n'
        '    "register_mode": "browser",'
    )
    if needle not in text:
        raise SystemExit("DEFAULT_CONFIG needle missing")
    text = text.replace(needle, repl, 1)
    print("DEFAULT_CONFIG: workers added")
else:
    print("DEFAULT_CONFIG: workers already present")

TLS_HELPERS = r'''
# ===== 18r30 thread-local browser + per-worker proxy =====
_tls = threading.local()
_ACTIVE_BROWSERS_LOCK = threading.Lock()
_ACTIVE_BROWSERS = {}  # thread_id -> Chromium


def _tls_browser_state():
    """Per-thread browser state (each worker has its own Chromium)."""
    t = _tls
    if not getattr(t, "_browser_inited", False):
        t.browser = None
        t.page = None
        t.browser_proxy_bridge = None
        t.browser_started_with_proxy = False
        t.proxy_override = None
        t._browser_inited = True
    return t


def set_thread_proxy(proxy_url: str = "") -> None:
    """Bind proxy URL for this worker thread (SOCKS5 per-thread sequential reuse)."""
    _tls_browser_state().proxy_override = str(proxy_url or "")


def clear_thread_proxy() -> None:
    st = _tls_browser_state()
    st.proxy_override = None


def get_thread_proxy_override():
    st = _tls_browser_state()
    return getattr(st, "proxy_override", None)


def _register_active_browser(b) -> None:
    tid = threading.get_ident()
    with _ACTIVE_BROWSERS_LOCK:
        if b is None:
            _ACTIVE_BROWSERS.pop(tid, None)
        else:
            _ACTIVE_BROWSERS[tid] = b


def _stop_all_thread_browsers(log_callback=None) -> int:
    """Quit every worker Chromium. Does NOT stop Grok2API/Sub2API/CLIProxy/CPA."""
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    with _ACTIVE_BROWSERS_LOCK:
        items = list(_ACTIVE_BROWSERS.items())
        _ACTIVE_BROWSERS.clear()
    n = 0
    for tid, b in items:
        if b is None:
            continue
        try:
            b.quit(del_data=True)
            n += 1
        except Exception as exc:
            _lg(f"[!] stop thread browser tid={tid}: {exc}")
    try:
        st = _tls_browser_state()
        st.browser = None
        st.page = None
        st.browser_proxy_bridge = None
        st.browser_started_with_proxy = False
    except Exception:
        pass
    if n:
        _lg(f"[*] 已关闭 {n} 个 worker 浏览器实例")
    return n


def _sync_module_browser_aliases():
    """Mirror current-thread TLS onto module attrs (compat for single-thread code)."""
    global browser, page, browser_proxy_bridge, browser_started_with_proxy
    st = _tls_browser_state()
    browser = st.browser
    page = st.page
    browser_proxy_bridge = st.browser_proxy_bridge
    browser_started_with_proxy = bool(st.browser_started_with_proxy)

'''

if "def _tls_browser_state" not in text:
    needle = (
        'SIGNUP_URL = "https://accounts.x.ai/sign-up?redirect=grok-com"\n\n'
        "browser = None\n"
        "page = None\n"
        "browser_proxy_bridge = None\n"
        "browser_started_with_proxy = False\n"
    )
    repl = (
        'SIGNUP_URL = "https://accounts.x.ai/sign-up?redirect=grok-com"\n'
        + TLS_HELPERS
        + "\nbrowser = None\n"
        "page = None\n"
        "browser_proxy_bridge = None\n"
        "browser_started_with_proxy = False\n"
    )
    if needle not in text:
        raise SystemExit("browser globals needle missing")
    text = text.replace(needle, repl, 1)
    print("TLS helpers inserted")
else:
    print("TLS helpers already present")

# get_configured_proxy
if "get_thread_proxy_override()" not in text:
    needle = "def get_configured_proxy():\n    mode = str(config.get(\"proxy_mode\", \"\") or \"\").strip().lower()\n"
    repl = (
        "def get_configured_proxy():\n"
        "    # 18r30: per-worker proxy override (SOCKS5 sequential bind)\n"
        "    try:\n"
        "        ov = get_thread_proxy_override()\n"
        "        if ov is not None:\n"
        "            return str(ov or \"\").strip()\n"
        "    except Exception:\n"
        "        pass\n"
        "    mode = str(config.get(\"proxy_mode\", \"\") or \"\").strip().lower()\n"
    )
    if needle not in text:
        raise SystemExit("get_configured_proxy needle missing")
    text = text.replace(needle, repl, 1)
    print("get_configured_proxy patched")
else:
    print("get_configured_proxy already patched")

path.write_text(text, encoding="utf-8")
print("part1 saved", orig_len, "->", len(text))
