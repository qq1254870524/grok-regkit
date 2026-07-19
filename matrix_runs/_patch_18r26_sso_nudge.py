# -*- coding: utf-8 -*-
from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
text = p.read_text(encoding="utf-8")
old = '''            # 18r23b: stuck on "您正在登录"/signing-in without sso — navigate to force cookie mint
            now2 = time.time()
            if now2 - last_signin_nudge_at >= 8.0 and signin_nudge_count < 4:
                try:
                    probe = page.run_js(
                        r"""
const body = (document.body && document.body.innerText || '').replace(/\\s+/g, '');
const url = String(location.href || '');
const hit = body.includes('您正在登录') || body.includes('正在登录')
  || /signing\\s*in/i.test(body) || /youare(being)?signedin/i.test(body)
  || body.includes('登录中');
const hasLast = document.cookie.includes('last-logged-in-with');
return JSON.stringify({hit: !!hit, hasLast: !!hasLast, url: url.slice(0, 160), bodyHead: body.slice(0, 80)});
"""
                    )
                    info = {}
                    try:
                        import json as _json
                        info = _json.loads(probe) if isinstance(probe, str) else {}
                    except Exception:
                        info = {}
                    if info.get("hit") or info.get("hasLast") or ("last-logged-in-with" in last_seen_names):
                        signin_nudge_count += 1
                        last_signin_nudge_at = now2
                        if log_callback:
                            log_callback(
                                f"[*] SSO nudge {signin_nudge_count}/4 signing-in page "
                                f"url={info.get('url')} hasLast={info.get('hasLast')} body={info.get('bodyHead')}"
                            )
                        for dest in (
                            "https://grok.com/",
                            "https://accounts.x.ai/",
                            "https://grok.com/chat",
                        ):
                            try:
                                if log_callback:
                                    log_callback(f"[*] SSO nudge goto {dest}")
                                page.get(dest)
                                sleep_with_cancel(2.0, cancel_callback)
                                refresh_active_page()
                                cookies2 = page.cookies(all_domains=True, all_info=True) or []
                                for item2 in cookies2:
                                    if isinstance(item2, dict):
                                        n2 = str(item2.get("name", "")).strip()
                                        v2 = str(item2.get("value", "")).strip()
                                    else:
                                        n2 = str(getattr(item2, "name", "")).strip()
                                        v2 = str(getattr(item2, "value", "")).strip()
                                    if n2:
                                        last_seen_names.add(n2)
                                    if n2 == "sso" and v2:
                                        if log_callback:
                                            log_callback(f"[*] 已获取到 sso cookie (nudge {dest})")
                                        return v2
                            except Exception as nav_exc:
                                if log_callback:
                                    log_callback(f"[Debug] SSO nudge nav fail {dest}: {nav_exc}")
                except Exception as nudge_exc:
                    if log_callback:
                        log_callback(f"[Debug] SSO nudge probe fail: {nudge_exc}")
'''
new = '''            # 18r26: SSO nudge only after pure signing-in; never leave active signup form
            now2 = time.time()
            if now2 - last_signin_nudge_at >= 10.0 and signin_nudge_count < 4:
                try:
                    probe = page.run_js(
                        r"""
const body = (document.body && document.body.innerText || '').replace(/\\s+/g, '');
const url = String(location.href || '');
const hit = body.includes('您正在登录') || body.includes('正在登录')
  || /signing\\s*in/i.test(body) || /youare(being)?signedin/i.test(body)
  || body.includes('登录中');
const hasLast = document.cookie.includes('last-logged-in-with');
const stillSignupForm = /sign-up/i.test(url) && (
  body.includes('完成注册') || body.includes('创建账户') || body.includes('名') && body.includes('姓') && body.includes('密码')
  || /completeyoursignup|createaccount|firstname|lastname/i.test(body)
);
const pureSigningIn = !!hit && !stillSignupForm;
return JSON.stringify({
  hit: !!hit,
  hasLast: !!hasLast,
  stillSignupForm: !!stillSignupForm,
  pureSigningIn: !!pureSigningIn,
  url: url.slice(0, 180),
  bodyHead: body.slice(0, 100)
});
"""
                    )
                    info = {}
                    try:
                        import json as _json
                        info = _json.loads(probe) if isinstance(probe, str) else {}
                    except Exception:
                        info = {}
                    if info.get("stillSignupForm"):
                        if log_callback and (now2 - last_signin_nudge_at >= 10.0):
                            log_callback(
                                f"[*] SSO hold on signup form (no nudge yet) url={info.get('url')} "
                                f"hit={info.get('hit')} body={info.get('bodyHead')}"
                            )
                            last_signin_nudge_at = now2  # throttle hold logs
                    elif info.get("pureSigningIn") or info.get("hasLast") or ("last-logged-in-with" in last_seen_names):
                        # first pure-signing-in: dwell >= 18s before navigating away
                        dwell_ok = True
                        if signin_nudge_count == 0 and info.get("pureSigningIn") and not info.get("hasLast"):
                            # use final_no_submit_since as dwell anchor when available
                            anchor = final_no_submit_since or (now2 - 0.0)
                            if final_no_submit_since and (now2 - final_no_submit_since) < 18:
                                dwell_ok = False
                                if log_callback:
                                    log_callback(
                                        f"[*] SSO pure signing-in dwell {(now2 - final_no_submit_since):.1f}s/18s "
                                        f"url={info.get('url')}"
                                    )
                                last_signin_nudge_at = now2
                        if dwell_ok:
                            signin_nudge_count += 1
                            last_signin_nudge_at = now2
                            if log_callback:
                                log_callback(
                                    f"[*] SSO nudge {signin_nudge_count}/4 pure-signing-in "
                                    f"url={info.get('url')} hasLast={info.get('hasLast')} body={info.get('bodyHead')}"
                                )
                            for dest in (
                                "https://grok.com/",
                                "https://accounts.x.ai/",
                                "https://grok.com/chat",
                            ):
                                try:
                                    if log_callback:
                                        log_callback(f"[*] SSO nudge goto {dest}")
                                    page.get(dest)
                                    sleep_with_cancel(2.0, cancel_callback)
                                    refresh_active_page()
                                    cookies2 = page.cookies(all_domains=True, all_info=True) or []
                                    for item2 in cookies2:
                                        if isinstance(item2, dict):
                                            n2 = str(item2.get("name", "")).strip()
                                            v2 = str(item2.get("value", "")).strip()
                                        else:
                                            n2 = str(getattr(item2, "name", "")).strip()
                                            v2 = str(getattr(item2, "value", "")).strip()
                                        if n2:
                                            last_seen_names.add(n2)
                                        if n2 == "sso" and v2:
                                            if log_callback:
                                                log_callback(f"[*] 已获取到 sso cookie (nudge {dest})")
                                            return v2
                                except Exception as nav_exc:
                                    if log_callback:
                                        log_callback(f"[Debug] SSO nudge nav fail {dest}: {nav_exc}")
                except Exception as nudge_exc:
                    if log_callback:
                        log_callback(f"[Debug] SSO nudge probe fail: {nudge_exc}")
'''
if old not in text:
    raise SystemExit('OLD BLOCK NOT FOUND')
p.write_text(text.replace(old, new, 1), encoding='utf-8')
print('patched wait_for_sso_cookie 18r26')
# hybrid changelog
hp = Path(r"C:\Users\zhang\grok-regkit\hybrid_register.py")
ht = hp.read_text(encoding='utf-8')
marker = 'Changelog:\n'
ins = 'Changelog:\n- 2026-07-19r26: browser SSO nudge 不再在仍含「完成注册」表单时跳转 grok.com（避免打断注册）\n'
if '2026-07-19r26' not in ht:
    if marker not in ht:
        raise SystemExit('no changelog marker')
    hp.write_text(ht.replace(marker, ins, 1), encoding='utf-8')
    print('hybrid changelog ok')
else:
    print('hybrid already has r26')
