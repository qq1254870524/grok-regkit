from pathlib import Path
import re, ast
path = Path("grok_register_ttk.py")
text = path.read_text(encoding="utf-8")
orig = text

def must_replace(old, new, label):
    global text
    if old not in text:
        raise SystemExit("NOT FOUND: " + label)
    text = text.replace(old, new, 1)
    print("OK", label)

must_replace(
'''def wait_cloudflare_passthrough(timeout=45, log_callback=None, cancel_callback=None):
    """Wait for CF challenge page to clear (JS challenge may auto-pass)."""
    deadline = time.time() + timeout
    reported = False
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        refresh_active_page()
        if not page_is_cloudflare_challenge(page):
''',
'''def wait_cloudflare_passthrough(timeout=45, log_callback=None, cancel_callback=None):
    """Wait for CF challenge page to clear (JS challenge may auto-pass)."""
    deadline = time.time() + timeout
    reported = False
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = None
        try:
            page = refresh_active_page()
        except Exception:
            page = _get_page()
        if page is None:
            sleep_with_cancel(1, cancel_callback)
            continue
        if not page_is_cloudflare_challenge(page):
''',
"wait_cf_header")

must_replace(
'''        sleep_with_cancel(2, cancel_callback)
    return not page_is_cloudflare_challenge(page)


def refresh_cliproxy_and_restart_browser(log_callback=None):
''',
'''        sleep_with_cancel(2, cancel_callback)
    page = _get_page()
    return (not page_is_cloudflare_challenge(page)) if page is not None else False


def refresh_cliproxy_and_restart_browser(log_callback=None):
''',
"wait_cf_tail")

PAGE_RESOLVE = '''        page = _get_page()
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.5, cancel_callback)
            continue
'''

anchor = '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        filled = page.run_js(
            """
const email = arguments[0];
'''
if anchor not in text:
    raise SystemExit("fill_email anchor not found")
text = text.replace(anchor, '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
''' + PAGE_RESOLVE + '''
        try:
            filled = page.run_js(
            """
const email = arguments[0];
''', 1)
print("OK fill_email_loop_start")

pat = re.compile(r'(filled = page\.run_js\(\n            """\nconst email = arguments\[0\];.*?\n            email,\n        \)\n)(        state = )', re.S)
m = pat.search(text)
if not m:
    raise SystemExit("fill_email run_js end not found")
text = text[:m.start()] + m.group(1) + '''        except Exception as _fe_exc:
            em = str(_fe_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] fill_email page disconnected: {_fe_exc}")
                try:
                    refresh_active_page()
                except Exception:
                    try:
                        restart_browser(log_callback=log_callback)
                        open_signup_page(log_callback=log_callback, cancel_callback=cancel_callback)
                    except Exception:
                        pass
                sleep_with_cancel(0.8, cancel_callback)
                continue
            raise
''' + m.group(2) + text[m.end():]
print("OK fill_email try/except")

must_replace(
'''def fill_code_and_submit(email, dev_token, timeout=180, log_callback=None, cancel_callback=None):
    def _resend_code():
        page.run_js(
''',
'''def fill_code_and_submit(email, dev_token, timeout=180, log_callback=None, cancel_callback=None):
    def _resend_code():
        page = _get_page()
        if page is None:
            return False
        page.run_js(
''',
"fill_code_resend")

idx_def = text.find("def fill_code_and_submit")
idx_prof = text.find("def fill_profile_and_submit")
seg = text[idx_def:idx_prof]
old_loop = '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        filled = page.run_js(
'''
if old_loop not in seg:
    raise SystemExit("fill_code loop not found")
seg = seg.replace(old_loop, '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
''' + PAGE_RESOLVE + '''
        try:
            filled = page.run_js(
''', 1)
m2 = re.search(r'(try:\n            filled = page\.run_js\((?:.|\n){200,9000}?\n        \)\n)([ \t]*\w)', seg)
if not m2:
    raise SystemExit("fill_code run_js end not found")
seg = seg[:m2.start()] + m2.group(1) + '''        except Exception as _fc_exc:
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
''' + m2.group(2) + seg[m2.end():]
text = text[:idx_def] + seg + text[idx_prof:]
print("OK fill_code")

idx_prof = text.find("def fill_profile_and_submit")
idx_sso = text.find("def wait_for_sso_cookie")
seg = text[idx_prof:idx_sso]
oldp = '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        if not form_filled_once:
            filled = page.run_js(
'''
if oldp not in seg:
    raise SystemExit("fill_profile loop not found")
seg = seg.replace(oldp, '''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
''' + PAGE_RESOLVE + '''
        if not form_filled_once:
            try:
                filled = page.run_js(
''', 1)
m3 = re.search(r'(try:\n                filled = page\.run_js\((?:.|\n){200,12000}?\n            \)\n)', seg)
if not m3:
    raise SystemExit("fill_profile end not found")
seg = seg[:m3.start()] + m3.group(1) + '''            except Exception as _fp_exc:
                em = str(_fp_exc)
                if (
                    ("NoneType" in em and "run_js" in em)
                    or "页面被刷新" in em
                    or "PageDisconnected" in em
                    or "与页面的连接已断开" in em
                ):
                    if log_callback:
                        log_callback(f"[!] fill_profile page disconnected: {_fp_exc}")
                    try:
                        refresh_active_page()
                    except Exception:
                        pass
                    sleep_with_cancel(0.8, cancel_callback)
                    continue
                raise
''' + seg[m3.end():]
text = text[:idx_prof] + seg + text[idx_sso:]
print("OK fill_profile")

must_replace(
'''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        try:
            refresh_active_page()
            if page is None:
                sleep_with_cancel(1, cancel_callback)
                continue

            # 仍停留在“完成注册”页时，若 Cloudflare 已通过，周期性重试点击提交
            now = time.time()
            if now - last_submit_retry >= 2.5:
                retried = page.run_js(
''',
'''    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        try:
            try:
                refresh_active_page()
            except Exception:
                pass
            page = _get_page()
            if page is None:
                sleep_with_cancel(1, cancel_callback)
                continue

            # 仍停留在“完成注册”页时，若 Cloudflare 已通过，周期性重试点击提交
            now = time.time()
            if now - last_submit_retry >= 2.5:
                retried = page.run_js(
''',
"wait_sso_page_resolve")

must_replace(
'''                finally:
                    coord.log_stats()
                    try:
                        if controller.should_stop():
                            break
                        if _get_browser() is None:
                            start_browser(log_callback=wlog)
                        else:
                            restart_browser(log_callback=wlog)
                    except Exception as rb:
                        wlog(f"[!] restart browser: {rb}")
                    sleep_with_cancel(1, controller.should_stop)
''',
'''                finally:
                    coord.log_stats()
                    try:
                        if controller.should_stop():
                            break
                        # 18r35: only hard-restart when browser/page is dead.
                        # Always-restart caused infinite open/close under workers=10.
                        b = _get_browser()
                        p = _get_page()
                        need_restart = b is None or p is None
                        if not need_restart:
                            try:
                                _ = p.url
                            except Exception:
                                need_restart = True
                        if need_restart:
                            if b is None:
                                start_browser(log_callback=wlog)
                            else:
                                restart_browser(log_callback=wlog)
                        else:
                            try:
                                open_signup_page(log_callback=wlog, cancel_callback=controller.should_stop)
                            except Exception as os_exc:
                                wlog(f"[!] soft open_signup failed, hard restart: {os_exc}")
                                restart_browser(log_callback=wlog)
                    except Exception as rb:
                        wlog(f"[!] restart browser: {rb}")
                    sleep_with_cancel(0.6, controller.should_stop)
''',
"browser_mt_soft_restart")

# click_email: simple line-based patch
old_click = '''    deadline = time.time() + timeout
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        if log_callback:
            log_callback("[Debug] 尝试查找“使用邮箱注册”按钮...")

        clicked = page.run_js(r"""
'''
new_click = '''    deadline = time.time() + timeout
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = _get_page() or page
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.4, cancel_callback)
            continue
        if log_callback:
            log_callback("[Debug] 尝试查找“使用邮箱注册”按钮...")

        try:
            clicked = page.run_js(r"""
'''
must_replace(old_click, new_click, "click_email_refresh_page")

# wrap end of click run_js - exact ending from file
old_end = '''return candidates[0].text || true;
        """)

        if clicked:
'''
new_end = '''return candidates[0].text || true;
        """)
        except Exception as _ce_exc:
            em = str(_ce_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] click_email page disconnected: {_ce_exc}")
                try:
                    page = refresh_active_page()
                except Exception:
                    page = _get_page()
                sleep_with_cancel(0.5, cancel_callback)
                continue
            raise

        if clicked:
'''
must_replace(old_end, new_end, "click_email_try_except")

path.write_text(text, encoding="utf-8")
print("WROTE", path, "delta", len(text) - len(orig))
ast.parse(text)
print("AST_OK")