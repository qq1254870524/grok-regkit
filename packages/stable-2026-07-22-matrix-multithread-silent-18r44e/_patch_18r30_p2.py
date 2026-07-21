# -*- coding: utf-8 -*-
"""18r30 patch part2: rewrite start/stop/get/refresh browser to TLS."""
from pathlib import Path
import re

path = Path("grok_register_ttk.py")
text = path.read_text(encoding="utf-8")

def replace_func(text, func_name, new_src):
    """Replace function definition starting at def name until next top-level def."""
    pat = re.compile(rf'^def {re.escape(func_name)}\(.*$', re.M)
    m = pat.search(text)
    if not m:
        raise SystemExit(f"func {func_name} not found")
    start = m.start()
    # find next def at column 0
    m2 = re.search(r'^def ', text[start + 1:], re.M)
    if not m2:
        end = len(text)
    else:
        end = start + 1 + m2.start()
    old = text[start:end]
    if new_src.rstrip() + "\n\n" == old or new_src.rstrip() + "\n" == old.rstrip() + "\n":
        print(func_name, "already same-ish")
    text2 = text[:start] + new_src.rstrip() + "\n\n\n" + text[end:]
    print(func_name, "replaced", len(old), "->", len(new_src))
    return text2

start_browser = r'''
def start_browser(log_callback=None, use_proxy=True):
    """Start Chromium for *this thread* only (18r30 TLS; multi-worker safe)."""
    st = _tls_browser_state()
    last_exc = None
    proxy_enabled = bool(use_proxy and get_configured_proxy())
    if sys.platform != "win32":
        _ensure_xvfb(log_callback=log_callback)
    for attempt in range(1, 5):
        bridge = None
        force_hl = None
        if sys.platform != "win32" and attempt >= 3:
            force_hl = True
            if log_callback and attempt == 3:
                log_callback("[!] 有头模式多次失败，回退无头 headless=new 重试")
        try:
            browser_proxy, bridge = prepare_browser_proxy(use_proxy=use_proxy, log_callback=log_callback)
            b = Chromium(
                create_browser_options(browser_proxy=browser_proxy, force_headless=force_hl)
            )
            st.browser = b
            st.browser_proxy_bridge = bridge
            st.browser_started_with_proxy = bool(browser_proxy)
            tabs = b.get_tabs()
            p = tabs[-1] if tabs else b.new_tab()
            st.page = p
            _register_active_browser(b)
            _sync_module_browser_aliases()
            _apply_browser_stealth(p, log_callback=log_callback)
            if log_callback and getattr(b, "user_data_path", None):
                log_callback(f"[Debug] 当前浏览器资料目录: {b.user_data_path}")
            if log_callback:
                if sys.platform != "win32":
                    hl = force_hl if force_hl is not None else _linux_should_headless()
                    log_callback(
                        f"[*] 浏览器显示模式: {'无头 headless' if hl else '有头 headed(Xvfb/DISPLAY)'} "
                        f"DISPLAY={os.environ.get('DISPLAY') or '(空)'} "
                        f"Xsocket={'ok' if _linux_display_socket_ok() else 'missing'}"
                    )
                if get_configured_proxy():
                    mode = "代理" if st.browser_started_with_proxy else "直连"
                    log_callback(f"[*] 浏览器网络模式: {mode}")
                    meta = config.get("_last_proxy_exit") if isinstance(config, dict) else None
                    if isinstance(meta, dict) and meta.get("exit_ip"):
                        log_callback(
                            f"[*] 出口家宽提醒: {meta.get('exit_ip')} "
                            f"({meta.get('exit_org') or '?'}) "
                            f"res={meta.get('isResidential')} fraud={meta.get('fraudScore')} "
                            f"| 入口网关仅={meta.get('gateway')}"
                        )
            if log_callback and attempt > 1:
                log_callback(f"[*] 浏览器第 {attempt} 次启动成功")
            return st.browser, st.page
        except Exception as exc:
            last_exc = exc
            if bridge is not None:
                try:
                    bridge.stop()
                except Exception:
                    pass
            if log_callback:
                mode = "代理" if proxy_enabled else "直连"
                log_callback(f"[Debug] 浏览器{mode}启动失败(第{attempt}/4次): {exc}")
            try:
                if st.browser is not None:
                    st.browser.quit(del_data=True)
            except Exception:
                pass
            st.browser = None
            st.page = None
            st.browser_proxy_bridge = None
            st.browser_started_with_proxy = False
            _register_active_browser(None)
            _sync_module_browser_aliases()
            if sys.platform != "win32" and attempt == 1:
                _ensure_xvfb(log_callback=log_callback)
            time.sleep(min(1.5 * attempt, 4))
    raise Exception(f"浏览器启动失败，已重试4次: {last_exc}")
'''

stop_bridge = r'''
def stop_browser_proxy_bridge(log_callback=None):
    """Stop local Chromium auth proxy bridge if running (this thread only)."""
    st = _tls_browser_state()
    bridge = st.browser_proxy_bridge
    st.browser_proxy_bridge = None
    _sync_module_browser_aliases()
    if bridge is None:
        return
    try:
        bridge.stop()
        if log_callback:
            log_callback("[*] 本地认证代理桥已关闭")
    except Exception as exc:
        if log_callback:
            log_callback(f"[!] 关闭本地认证代理桥失败: {exc}")
'''

stop_browser = r'''
def stop_browser(log_callback=None):
    """Close DrissionPage browser + local proxy bridge for *this thread*."""
    st = _tls_browser_state()
    _lg = log_callback if callable(log_callback) else None
    b = st.browser
    st.browser = None
    st.page = None
    st.browser_started_with_proxy = False
    _register_active_browser(None)
    _sync_module_browser_aliases()
    if b is not None:
        try:
            b.quit(del_data=True)
            if _lg:
                _lg("[*] 浏览器已关闭")
        except Exception as exc:
            if _lg:
                _lg(f"[!] browser.quit 失败: {exc}")
    stop_browser_proxy_bridge(log_callback=log_callback)
'''

force_stop = r'''
def force_stop_registration(log_callback=None, reason="user_stop"):
    """Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA."""
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    _lg(f"[!] force_stop_registration: {reason}")
    try:
        stop_browser(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] stop_browser in force_stop: {exc}")
    try:
        _stop_all_thread_browsers(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] stop_all_thread_browsers: {exc}")
    try:
        force_kill_registration_browsers(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] force_kill in force_stop: {exc}")
'''

get_browser = r'''
def _get_browser():
    """Alias for hybrid/token_harvester (thread-local)."""
    return _tls_browser_state().browser


def _get_page():
    """Alias for hybrid/token_harvester; refresh tab if needed (thread-local)."""
    st = _tls_browser_state()
    if st.browser is None:
        return None
    if st.page is None:
        try:
            return refresh_active_page()
        except Exception:
            return None
    return st.page


def restart_browser(log_callback=None, use_proxy=True):
    stop_browser()
    return start_browser(log_callback=log_callback, use_proxy=use_proxy)


def cleanup_runtime_memory(log_callback=None, reason="定期清理"):
    if log_callback:
        log_callback(f"[*] {reason}: 关闭浏览器并清理内存")
    stop_browser()
    collected = gc.collect()
    if log_callback:
        log_callback(f"[*] Python GC 已回收对象数: {collected}")


def refresh_active_page():
    st = _tls_browser_state()
    if st.browser is None:
        restart_browser()
        st = _tls_browser_state()
    try:
        tabs = st.browser.get_tabs()
        if tabs:
            st.page = tabs[-1]
        else:
            st.page = st.browser.new_tab()
    except Exception:
        restart_browser()
        st = _tls_browser_state()
    _sync_module_browser_aliases()
    return st.page
'''

# replace_func for multi-def block: only first name
for name, src in [
    ("start_browser", start_browser),
    ("stop_browser_proxy_bridge", stop_bridge),
    ("stop_browser", stop_browser),
]:
    text = replace_func(text, name, src)

# force_stop_registration - may sit after force_kill
text = replace_func(text, "force_stop_registration", force_stop)

# _get_browser through refresh - replace from _get_browser until click_email
m = re.search(r'^def _get_browser\(\):', text, re.M)
if not m:
    raise SystemExit("_get_browser missing")
m2 = re.search(r'^def click_email_signup_button', text, re.M)
if not m2:
    raise SystemExit("click_email missing")
text = text[:m.start()] + get_browser.rstrip() + "\n\n\n" + text[m2.start():]
print("_get_browser..refresh replaced")

# click_email: global page -> page = _get_page()
text2 = text
idx = text.find("def click_email_signup_button")
if idx >= 0:
    # only within first 300 chars of function
    head = text[idx:idx+300]
    if "global page" in head:
        head2 = head.replace("global page\n", "page = _get_page()\n    if page is None:\n        raise Exception('浏览器 page 未就绪')\n", 1)
        text = text[:idx] + head2 + text[idx+300:]
        print("click_email global page fixed")
    else:
        print("click_email no global page")

# open_signup_page
idx = text.find("def open_signup_page")
if idx < 0:
    raise SystemExit("open_signup missing")
m2 = re.search(r'^def ', text[idx+1:], re.M)
end = idx + 1 + m2.start()
fn = text[idx:end]
fn2 = fn
if "global browser, page" in fn2:
    fn2 = fn2.replace(
        "global browser, page\n",
        "st = _tls_browser_state()\n    browser = st.browser\n    page = st.page\n",
        1,
    )
    print("open_signup primary global fixed")
if re.search(r'^\s*global page\s*$', fn2, re.M):
    fn2 = re.sub(
        r'^(\s*)global page\s*$',
        r"\1page = _get_page()\n\1browser = _get_browser()\n\1st = _tls_browser_state()",
        fn2,
        count=1,
        flags=re.M,
    )
    print("open_signup secondary global fixed")
# sync page assignments
for pat in [
    "page = browser.get_tab(0)",
    "page = current_browser.new_tab(SIGNUP_URL)",
    "page = browser.new_tab(SIGNUP_URL)",
]:
    if pat in fn2 and "st.page = page" not in fn2.split(pat, 1)[1][:120]:
        fn2 = fn2.replace(
            pat,
            pat
            + "\n            st = _tls_browser_state()\n"
            + "            st.page = page\n"
            + "            if browser is not None:\n"
            + "                st.browser = browser\n"
            + "            _sync_module_browser_aliases()",
            1,
        )
        print("synced", pat[:40])
# Also when open_signup sets browser via start - look for start_browser returns
if "browser, page = start_browser" in fn2 or "start_browser(" in fn2:
    # after start_browser calls, TLS already set
    pass
# ensure browser_started_with_proxy reads from TLS when used bare
if "browser_started_with_proxy" in fn2:
    fn2 = fn2.replace(
        "if browser_started_with_proxy and get_configured_proxy():",
        "if _tls_browser_state().browser_started_with_proxy and get_configured_proxy():",
    )
    fn2 = fn2.replace(
        "if browser_started_with_proxy and page_has_proxy_error(page):",
        "if _tls_browser_state().browser_started_with_proxy and page_has_proxy_error(page):",
    )
text = text[:idx] + fn2 + text[end:]

# getTurnstileToken
idx = text.find("def getTurnstileToken")
if idx >= 0:
    head = text[idx:idx+250]
    if "global page" in head:
        head2 = head.replace(
            "global page\n",
            "page = _get_page()\n    if page is None:\n        raise Exception('浏览器 page 未就绪 (getTurnstileToken)')\n",
            1,
        )
        text = text[:idx] + head2 + text[idx+250:]
        print("getTurnstileToken fixed")

# remaining global page
text = re.sub(r'^([ \t]+)global page\s*$', r'\1page = _get_page()', text, flags=re.M)
print("remaining global page count", len(re.findall(r'global page', text)))

# bare browser is None in run_registration_job finally
text = text.replace(
    "                if browser is None:\n                    start_browser(log_callback=log)\n",
    "                if _get_browser() is None:\n                    start_browser(log_callback=log)\n",
)

path.write_text(text, encoding="utf-8")
import py_compile
try:
    py_compile.compile(str(path), doraise=True)
    print("COMPILE OK")
except Exception as e:
    print("COMPILE FAIL", e)
print("saved", path.stat().st_size)
