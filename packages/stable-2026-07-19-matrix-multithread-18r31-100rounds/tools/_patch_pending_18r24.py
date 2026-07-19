# -*- coding: utf-8 -*-
from pathlib import Path
import py_compile

p = Path(r"C:\Users\zhang\grok-regkit\pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")

old = '''            log("[pending-sso] browser ready; direct-to-sign-in (no sign-up navigation)")
            page = _get_page()
            if page is None:
                return result(STATUS_FAIL, email=email, detail="no browser page")

            for nav_try in range(1, 4):
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    page.get(signin_url)
                    try:
                        page.wait.doc_loaded()
                    except Exception:
                        pass
                    sleep_with_cancel(1.0, stop)
                    cur = str(getattr(page, "url", "") or "")
                    log(f"[pending-sso] navigate sign-in try={nav_try} url={cur}")
                    if "sign-in" in cur or "accounts.x.ai" in cur:
                        break
                except Exception as nav_exc:
                    if stop():
                        return result(STATUS_STOPPED, email=email)
                    log(f"[pending-sso] navigate sign-in fail try={nav_try}: {nav_exc}")
                    if nav_try >= 3:
                        return result(STATUS_FAIL, email=email, detail=str(nav_exc))
                    sleep_with_cancel(1.0, stop)
'''

new = '''            log("[pending-sso] browser ready; direct-to-sign-in (no sign-up navigation)")
            page = _get_page()
            if page is None:
                return result(STATUS_FAIL, email=email, detail="no browser page")

            # 18r24: prefer email=true deep-link so we skip flaky "使用邮箱登录" social landing.
            signin_email_url = signin_url
            if "email=" not in str(signin_url):
                signin_email_url = (
                    str(signin_url)
                    + ("&" if "?" in str(signin_url) else "?")
                    + "email=true"
                )
            nav_targets = [signin_email_url, signin_url]
            for nav_try in range(1, 5):
                if stop():
                    return result(STATUS_STOPPED, email=email)
                target = nav_targets[(nav_try - 1) % len(nav_targets)]
                try:
                    page.get(target)
                    try:
                        page.wait.doc_loaded()
                    except Exception:
                        pass
                    sleep_with_cancel(1.2, stop)
                    cur = str(getattr(page, "url", "") or "")
                    log(f"[pending-sso] navigate sign-in try={nav_try} target={target} url={cur}")
                    # if already on email form path, stop retrying nav
                    if "email=true" in cur or "sign-in" in cur or "accounts.x.ai" in cur:
                        # probe once whether email input exists
                        try:
                            probe = page.run_js(wait_inputs_js) or {}
                        except Exception:
                            probe = {}
                        if isinstance(probe, dict) and (probe.get("email") or probe.get("pw") or probe.get("ready")):
                            log(f"[pending-sso] sign-in inputs visible after nav: {probe}")
                            break
                        if nav_try >= 2 and "email=true" in cur:
                            break
                except Exception as nav_exc:
                    if stop():
                        return result(STATUS_STOPPED, email=email)
                    log(f"[pending-sso] navigate sign-in fail try={nav_try}: {nav_exc}")
                    if nav_try >= 4:
                        return result(STATUS_FAIL, email=email, detail=str(nav_exc))
                    sleep_with_cancel(1.0, stop)
'''

if old not in t:
    raise SystemExit('nav block not found')
t = t.replace(old, new, 1)

# also after email btn max clicks, force navigate email=true once
old2 = '''                    if isinstance(click_r, dict) and click_r.get("clicked"):
                        email_btn_clicks += 1
                        log(f"[pending-sso] clicked email sign-in btn#{email_btn_clicks}: {click_r.get('text')}")
                        sleep_with_cancel(1.0, stop)
                        continue
'''
new2 = '''                    if isinstance(click_r, dict) and click_r.get("clicked"):
                        email_btn_clicks += 1
                        log(f"[pending-sso] clicked email sign-in btn#{email_btn_clicks}: {click_r.get('text')}")
                        sleep_with_cancel(1.0, stop)
                        # 18r24: after 2 empty clicks, force email=true deep link
                        if email_btn_clicks >= 2:
                            try:
                                force_u = signin_url
                                if "email=" not in str(force_u):
                                    force_u = str(force_u) + ("&" if "?" in str(force_u) else "?") + "email=true"
                                log(f"[pending-sso] force email=true deep-link after empty clicks -> {force_u}")
                                page.get(force_u)
                                try:
                                    page.wait.doc_loaded()
                                except Exception:
                                    pass
                                sleep_with_cancel(1.2, stop)
                            except Exception as force_exc:
                                log(f"[pending-sso] force email=true fail: {force_exc}")
                        continue
'''
if old2 not in t:
    raise SystemExit('click block not found')
t = t.replace(old2, new2, 1)

# changelog head
if '18r24 pending' not in t[:1500]:
    t = t.replace(
        '"""',
        '"""\n18r24: pending-sso sign-in prefers ?email=true deep-link; after 2 empty social-btn clicks force email form URL.\n',
        1,
    )

p.write_text(t, encoding='utf-8')
py_compile.compile(str(p), doraise=True)
print('pending_sso_recovery patched OK')
