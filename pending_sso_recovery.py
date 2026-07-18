"""Pending SSO recovery helpers for grok-regkit hybrid.

2026-07-18e: pool-empty stop support helpers + pending_sso secondary recovery.

2026-07-18g: pending sign-in 直达、等待真实输入框、禁点“您正在登录/Loading”。
2026-07-18n: pending 登录页先点「使用邮箱登录」再等 email/password；配合 speed 补丁；日志不脱敏。
2026-07-18o: xAI 两步登录：email 就绪后先填邮箱点「下一步/继续」，再等 password；ready 仅在 email+pw 都在时成立；日志 email next / pw ready。
2026-07-18p: 登录后抓 page_err/body；登录成功后主动打开 grok.com 固化 cookie；document.cookie 兜底；仍停 sign-in 时重填重点登录。
2026-07-18q: 全域 cookies(all_domains) + CDP Network.getAllCookies 收 SSO；登录后即使仍在 sign-in 也轮询 accounts/grok 固化；submit 后 form.requestSubmit/Enter 双保险；详细 page body/url 日志。
2026-07-18r: 登录提交后强制等待 12s/URL变化/loading消失再 re-fill，禁止 1s 内连点打断；Cloudflare/captcha/challenge 未过完不跳 grok；仅确认离开 sign-in 后才固化 cookie；bad_password/account_missing 明确失败后移出 pending 并走重新注册(hybrid)，不是只删号；CF 未过完不跳 grok；网络/loading 日志细化。
2026-07-18r2: 修复页面标题「您正在登录」被误判为 loading 导致永久空等；loading 仅认 aria-busy/disabled/纯 spinner 文案。
2026-07-18r3: 识别页面 An error occurred/登录失败 为 auth_error；移出 pending 后走 hybrid 重新注册（不是只删号）；rate_limit 不直接重注册。
"""
from __future__ import annotations

import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent

STATUS_SUCCESS = "success"
STATUS_FAIL = "fail"
STATUS_PENDING_SSO = "pending_sso"
STATUS_POOL_EMPTY = "pool_empty"
STATUS_STOPPED = "stopped"

def result(status: str, **extra: Any) -> dict:
    out = {"status": status, "ok": status == STATUS_SUCCESS}
    out.update(extra)
    return out

def is_pool_empty_error(exc: BaseException | str) -> bool:
    msg = str(exc or "")
    low = msg.lower()
    keys = (
        "pool empty", "account pool empty", "configure aol_accounts", "no fresh email",
        "邮箱池", "获取邮箱失败", "account pool", "no available", "no idle", "empty pool",
        "池已空", "池为空", "没有可用邮箱", "无可用邮箱", "all accounts", "no accounts", "exhausted",
    )
    return any(k in msg or k in low for k in keys)


def _extract_sso_from_cookie_blob(blob: str) -> str:
    import re as _re
    blob = str(blob or "")
    if not blob:
        return ""
    for key in ("sso", "sso-rw"):
        m = _re.search(rf"(?:^|;\s*){key}=([^;]+)", blob)
        if m and len(m.group(1).strip()) >= 20:
            return m.group(1).strip()
    return ""


def _collect_sso_from_page(page, browser=None, log=None) -> str:
    """Harvest sso from browser cookie jar with multiple fallbacks."""
    log = log or (lambda _m: None)
    jar = {}
    if browser is not None:
        try:
            jar.update(dict(browser.export_cookies() or {}))
        except Exception as e:
            log(f"[pending-sso] export_cookies fail: {e}")
    cookies = []
    if page is not None:
        for kwargs in (
            {"all_domains": True, "all_info": True},
            {"all_domains": True},
            {},
        ):
            try:
                cookies = page.cookies(**kwargs) or []
                if cookies:
                    break
            except TypeError:
                try:
                    cookies = page.cookies() or []
                    break
                except Exception:
                    cookies = []
            except Exception:
                cookies = []
        for item in cookies or []:
            if isinstance(item, dict):
                n = str(item.get("name") or "")
                v = str(item.get("value") or "")
            else:
                n = str(getattr(item, "name", "") or "")
                v = str(getattr(item, "value", "") or "")
            if n and v:
                jar[n] = v
        try:
            doc = page.run_js("return document.cookie || ''") or ""
            sso_doc = _extract_sso_from_cookie_blob(doc)
            if sso_doc and "sso" not in jar:
                jar["sso"] = sso_doc
        except Exception:
            pass
        for runner_name in ("run_cdp", "run_cdp_loaded", "_run_cdp"):
            runner = getattr(page, runner_name, None)
            if not callable(runner):
                continue
            try:
                res = runner("Network.getAllCookies")
            except Exception:
                try:
                    res = runner("Network.getCookies")
                except Exception:
                    res = None
            if isinstance(res, dict):
                for item in res.get("cookies") or []:
                    n = str(item.get("name") or "")
                    v = str(item.get("value") or "")
                    if n and v:
                        jar[n] = v
            break
    sso = str(jar.get("sso") or jar.get("sso-rw") or "").strip()
    if sso and len(sso) >= 20:
        return sso
    return ""


def normalize_result(value: Any) -> dict:
    if isinstance(value, dict) and value.get("status"):
        return value
    if value is True:
        return result(STATUS_SUCCESS)
    if value is False:
        return result(STATUS_FAIL)
    return result(STATUS_FAIL, detail=str(value))


def parse_pending_account_line(line: str) -> dict | None:
    text = str(line or "").strip()
    if not text or text.startswith("#") or "----" not in text:
        return None
    parts = [p.strip() for p in text.split("----")]
    if len(parts) < 2:
        return None
    email, password = parts[0], parts[1]
    if not email or not password:
        return None
    note = parts[2] if len(parts) >= 3 else ""
    return {"email": email, "password": password, "note": note, "raw": text}


def load_pending_sso_accounts(include_timestamped: bool = True) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def _add_from(path: Path) -> None:
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if not parsed:
                continue
            key = parsed["email"].lower()
            if key in seen:
                continue
            seen.add(key)
            parsed["source"] = path.name
            items.append(parsed)

    _add_from(ROOT / "accounts_registered_pending_sso.txt")
    if include_timestamped:
        for pth in sorted(ROOT.glob("accounts_no_sso_*.txt"), key=lambda x: x.stat().st_mtime, reverse=True):
            _add_from(pth)
    return items


def remove_pending_sso_account(email: str, log: Callable[[str], None] | None = None) -> int:
    target = str(email or "").strip().lower()
    if not target:
        return 0
    removed = 0
    paths = [ROOT / "accounts_registered_pending_sso.txt"]
    paths.extend(sorted(ROOT.glob("accounts_no_sso_*.txt")))
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            if log:
                log(f"[pending] read {path.name} fail: {exc}")
            continue
        kept: list[str] = []
        file_removed = 0
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if parsed and parsed["email"].lower() == target:
                file_removed += 1
                continue
            kept.append(ln)
        if file_removed:
            try:
                path.write_text(("\n".join(kept) + ("\n" if kept else "")), encoding="utf-8")
                removed += file_removed
                if log:
                    log(f"[pending] removed {target} x{file_removed} from {path.name}")
            except Exception as exc:
                if log:
                    log(f"[pending] write {path.name} fail: {exc}")
    return removed


def recover_one_pending_sso(
    *,
    email: str,
    password: str,
    log: Callable[[str], None],
    proxy: str = "",
    should_stop: Optional[Callable[[], bool]] = None,
    post_success: bool = True,
    accounts_file: Path | None = None,
) -> dict:
    """Browser sign-in for a verified account and harvest sso/sso-rw cookies."""
    from browser.token_harvester import BrowserTokenSession
    from grok_register_ttk import (
        _get_page,
        open_signup_page,
        schedule_post_registration,
        sleep_with_cancel,
    )

    stop = should_stop or (lambda: False)
    email = str(email or "").strip()
    password = str(password or "").strip()
    if not email or not password:
        return result(STATUS_FAIL, detail="missing email/password", email=email)
    if stop():
        return result(STATUS_STOPPED, email=email)

    signin_url = "https://accounts.x.ai/sign-in?redirect=grok-com"
    t0 = time.time()
    log(f"[pending-sso] start recover email={email}")

    wait_inputs_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]');
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]');
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'))
  .filter(n => isVisible(n) && !n.disabled)
  .map(buttonText).filter(Boolean).slice(0, 8);
return {
  url: location.href,
  title: document.title || '',
  email: !!emailInput,
  pw: !!pwInput,
  ready: !!(emailInput && pwInput),
  emailOnly: !!(emailInput && !pwInput),
  buttons: buttons,
  body: (document.body && document.body.innerText || '').slice(0, 180).replace(/\s+/g, ' ')
};
"""

    advance_email_step_js = r"""
const email = String(arguments[0] || '');
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pickAll(sel) {
  return Array.from(document.querySelectorAll(sel)).filter(n => isVisible(n) && !n.disabled);
}
function pick(sel) {
  return pickAll(sel)[0] || null;
}
function setVal(input, value) {
  if (!input) return false;
  try { input.removeAttribute('readonly'); } catch (e) {}
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('blur', { bubbles: true }));
  return String(input.value || '').trim() === String(value || '').trim();
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function isBusyText(t) {
  const s = String(t || '').toLowerCase();
  return (
    s.includes('您正在登录') ||
    s.includes('正在登录') ||
    s.includes('signing in') ||
    s.includes('logging in') ||
    s.includes('loading') ||
    s.includes('please wait') ||
    s.includes('请稍候') ||
    s.includes('处理中') ||
    s.includes('submitting')
  );
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]')
  || pickAll('input').find(n => {
      const t = ((n.name||'') + ' ' + (n.id||'') + ' ' + (n.placeholder||'') + ' ' + (n.getAttribute('aria-label')||'')).toLowerCase();
      return t.includes('email') || t.includes('user') || t.includes('邮箱') || t.includes('账号');
    }) || null;
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]');
const out = {
  url: location.href,
  email: !!emailInput,
  pw: !!pwInput,
  emailFilled: false,
  clicked: false,
  btn: '',
  reason: ''
};
if (pwInput) {
  out.reason = 'password_already_ready';
  return out;
}
if (!emailInput) {
  out.reason = 'no_email_input';
  return out;
}
out.emailFilled = setVal(emailInput, email);
out.emailVal = String(emailInput.value || '');
if (!out.emailFilled) {
  out.reason = 'email_fill_mismatch';
  return out;
}
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(n => isVisible(n) && !n.disabled);
const btn = buttons.find(n => {
  const t = buttonText(n);
  const low = t.toLowerCase().replace(/\s+/g, '');
  if (!t || isBusyText(t)) return false;
  if (n.getAttribute('aria-disabled') === 'true') return false;
  if (n.getAttribute('aria-busy') === 'true') return false;
  if (String(n.getAttribute('type') || '').toLowerCase() === 'submit') return true;
  return (
    low.includes('下一步') ||
    low.includes('继续') ||
    low.includes('繼續') ||
    low.includes('next') ||
    low.includes('continue') ||
    low === '登录' ||
    (low.includes('登录') && !low.includes('正在') && !low.includes('邮箱登录'))
  );
}) || null;
if (btn) {
  out.btn = buttonText(btn);
  try { btn.focus(); btn.click(); out.clicked = true; out.reason = 'email_next_clicked'; }
  catch (e) { out.reason = 'click_err:' + String(e); }
} else {
  out.reason = 'no_next_button';
  try {
    emailInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    emailInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    out.clicked = true;
    out.btn = 'ENTER_ON_EMAIL';
    out.reason = 'email_enter';
  } catch (e) {
    out.reason = 'no_next_and_enter_fail:' + String(e);
  }
}
return out;
"""

    click_email_signin_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function score(node) {
  const t = buttonText(node);
  const compact = t.replace(/\s+/g, '').toLowerCase();
  if (!t) return -1;
  if (compact.includes('使用邮箱登录') || compact.includes('用邮箱登录')) return 100;
  if (compact.includes('邮箱') && compact.includes('登录')) return 95;
  if (compact.includes('continuewithemail') || compact.includes('signinwithemail') || compact.includes('sign-inwithemail')) return 92;
  if (compact.includes('email') && (compact.includes('sign') || compact.includes('log'))) return 90;
  return -1;
}
const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div[tabindex], span[role="button"]'))
  .filter(n => isVisible(n));
let best = null, bestScore = -1;
for (const n of nodes) {
  const s = score(n);
  if (s > bestScore) { best = n; bestScore = s; }
}
if (!best || bestScore < 0) {
  return {clicked:false, reason:'no-email-signin-btn', candidates: nodes.map(buttonText).filter(Boolean).slice(0,12)};
}
try { best.scrollIntoView({block:'center'}); } catch (e) {}
try { best.focus(); } catch (e) {}
try { best.click(); } catch (e) { return {clicked:false, reason:String(e), text:buttonText(best)}; }
return {clicked:true, score:bestScore, text:buttonText(best)};
"""

    fill_js = r"""
const email = String(arguments[0] || '');
const password = String(arguments[1] || '');
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pickAll(sel) {
  return Array.from(document.querySelectorAll(sel)).filter(n => isVisible(n) && !n.disabled);
}
function pick(sel) {
  return pickAll(sel)[0] || null;
}
function setVal(input, value) {
  if (!input) return false;
  try { input.removeAttribute('readonly'); } catch (e) {}
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('blur', { bubbles: true }));
  return String(input.value || '').trim() === String(value || '').trim();
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function isBusyText(t) {
  const s = String(t || '').toLowerCase();
  return (
    s.includes('您正在登录') ||
    s.includes('正在登录') ||
    s.includes('signing in') ||
    s.includes('logging in') ||
    s.includes('loading') ||
    s.includes('please wait') ||
    s.includes('请稍候') ||
    s.includes('处理中') ||
    s.includes('submitting')
  );
}
function isSubmitCandidate(node) {
  if (!node || node.disabled) return false;
  const t = buttonText(node);
  const low = t.toLowerCase();
  if (!t || isBusyText(t)) return false;
  if (node.getAttribute('aria-disabled') === 'true') return false;
  if (node.getAttribute('aria-busy') === 'true') return false;
  if (String(node.getAttribute('type') || '').toLowerCase() === 'submit') return true;
  return (
    low.includes('sign in') ||
    low.includes('log in') ||
    low === '登录' ||
    (low.includes('登录') && !low.includes('正在')) ||
    low.includes('繼續') ||
    low.includes('继续') ||
    low.includes('next') ||
    low.includes('continue') ||
    low.includes('submit')
  );
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]')
  || pickAll('input').find(n => {
      const t = ((n.name||'') + ' ' + (n.id||'') + ' ' + (n.placeholder||'') + ' ' + (n.getAttribute('aria-label')||'')).toLowerCase();
      return t.includes('email') || t.includes('user') || t.includes('邮箱') || t.includes('账号');
    }) || null;
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]')
  || pickAll('input[type="password"]')[0] || null;
const out = {
  url: location.href,
  email: !!emailInput,
  pw: !!pwInput,
  filled: false,
  clicked: false,
  btn: '',
  emailVal: emailInput ? String(emailInput.value||'') : '',
  pwLen: pwInput ? String(pwInput.value||'').length : 0
};
if (!emailInput || !pwInput) {
  out.reason = 'inputs_not_ready';
  return out;
}
out.emailFilled = setVal(emailInput, email);
out.pwFilled = setVal(pwInput, password);
out.filled = !!(out.emailFilled && out.pwFilled);
out.emailVal = String(emailInput.value || '');
out.pwLen = String(pwInput.value || '').length;
if (!out.filled) {
  out.reason = 'fill_mismatch';
  return out;
}
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(isVisible);
const btn = buttons.find(isSubmitCandidate) || null;
if (btn) {
  out.btn = buttonText(btn);
  if (isBusyText(out.btn)) {
    out.reason = 'busy_button';
    out.clicked = false;
    return out;
  }
  try { btn.focus(); btn.click(); out.clicked = true; } catch (e) { out.clickErr = String(e); }
} else {
  out.reason = 'no_submit_button';
  try {
    pwInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    pwInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    out.clicked = true;
    out.btn = 'ENTER_ON_PASSWORD';
  } catch (e) {
    out.clickErr = String(e);
  }
}
return out;
"""

    try:
        with BrowserTokenSession(log=log) as browser:
            if stop():
                return result(STATUS_STOPPED, email=email)
            try:
                open_signup_page(log_callback=log, cancel_callback=stop)
            except Exception as open_exc:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                log(f"[pending-sso] open browser bootstrap fail: {open_exc}")
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

            ready = False
            wait_deadline = time.time() + 55
            last_wait = {}
            email_btn_clicks = 0
            email_next_clicks = 0
            while time.time() < wait_deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    last_wait = page.run_js(wait_inputs_js) or {}
                except Exception as wait_exc:
                    last_wait = {"error": str(wait_exc)}
                if isinstance(last_wait, dict) and last_wait.get("ready"):
                    ready = True
                    log(f"[pending-sso] pw ready state={last_wait}")
                    break
                # xAI sign-in first screen only shows social + "使用邮箱登录"; click it.
                if (
                    isinstance(last_wait, dict)
                    and not last_wait.get("email")
                    and not last_wait.get("pw")
                    and email_btn_clicks < 4
                ):
                    try:
                        click_r = page.run_js(click_email_signin_js) or {}
                    except Exception as click_exc:
                        click_r = {"clicked": False, "error": str(click_exc)}
                    if isinstance(click_r, dict) and click_r.get("clicked"):
                        email_btn_clicks += 1
                        log(f"[pending-sso] clicked email sign-in btn#{email_btn_clicks}: {click_r.get('text')}")
                        sleep_with_cancel(1.0, stop)
                        continue
                    elif email_btn_clicks == 0 and isinstance(click_r, dict):
                        # log once for diagnostics (candidates, no secrets)
                        if not last_wait.get("_email_btn_logged"):
                            log(f"[pending-sso] email sign-in btn not found yet: {click_r}")
                            if isinstance(last_wait, dict):
                                last_wait["_email_btn_logged"] = True
                # Two-step login: email field first, then click 下一步 / Continue, then password appears.
                if (
                    isinstance(last_wait, dict)
                    and last_wait.get("email")
                    and not last_wait.get("pw")
                    and email_next_clicks < 5
                ):
                    try:
                        step_r = page.run_js(advance_email_step_js, email) or {}
                    except Exception as step_exc:
                        step_r = {"clicked": False, "error": str(step_exc)}
                    email_next_clicks += 1
                    log(f"[pending-sso] email next #{email_next_clicks}: {step_r}")
                    sleep_with_cancel(1.2 if email_next_clicks == 1 else 0.9, stop)
                    continue
                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                if "sign-up" in cur:
                    try:
                        page.get(signin_url)
                    except Exception:
                        pass
                sleep_with_cancel(0.8, stop)
            log(f"[pending-sso] wait inputs ready={ready} state={last_wait}")
            if not ready:
                return result(STATUS_FAIL, email=email, detail=f"sign-in inputs not ready: {last_wait}")

            fill_state = {}
            for fill_try in range(1, 5):
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    fill_state = page.run_js(fill_js, email, password) or {}
                except Exception as fill_exc:
                    log(f"[pending-sso] fill/sign-in js fail try={fill_try}: {fill_exc}")
                    fill_state = {"error": str(fill_exc)}
                log(f"[pending-sso] fill state try={fill_try} {fill_state}")
                if isinstance(fill_state, dict) and fill_state.get("filled"):
                    break
                sleep_with_cancel(1.0, stop)
            if not (isinstance(fill_state, dict) and fill_state.get("filled")):
                return result(STATUS_FAIL, email=email, detail=f"fill failed: {fill_state}")

            page_state_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const body = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 240);
const low = body.toLowerCase();
let err = '';
if ((low.includes('密码') || low.includes('password')) && (low.includes('错误') || low.includes('不正确') || low.includes('invalid') || low.includes('wrong') || low.includes('incorrect'))) err = 'bad_password';
else if (low.includes('incorrect') || low.includes('invalid password') || low.includes('wrong password') || low.includes('密码错误') || low.includes('密码不正确')) err = 'bad_password';
else if (low.includes('过多') || low.includes('too many') || low.includes('rate') || low.includes('try again later') || low.includes('稍后')) err = 'rate_limit';
else if ((low.includes('验证') || low.includes('verify') || low.includes('challenge')) && (low.includes('人机') || low.includes('captcha') || low.includes('turnstile') || low.includes('cloudflare'))) err = 'captcha';
else if (low.includes('不存在') || low.includes('no account') || low.includes('not found') || low.includes('找不到') || low.includes('未能找到')) err = 'account_missing';
else if (low.includes('an error occurred') || low.includes('出错了') || low.includes('发生错误') || low.includes('something went wrong') || low.includes('unable to sign') || low.includes('无法登录') || low.includes('登录失败')) err = 'auth_error';
return {
  url: location.href,
  title: document.title || '',
  body: body,
  err: err,
  hasPw: !!Array.from(document.querySelectorAll('input[type="password"]')).find(isVisible),
  cookie: document.cookie || ''
};
"""

            # After first submit, also force form.requestSubmit / Enter once.
            submit_ts = time.time()
            try:
                boost = page.run_js(r"""
const form = document.querySelector('form');
const pw = document.querySelector('input[type="password"]');
const btns = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
const out = {submit:false, enter:false, click:false, btn:''};
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function isDisabled(node) {
  if (!node) return true;
  if (node.disabled) return true;
  const aria = (node.getAttribute('aria-disabled') || '').toLowerCase();
  if (aria === 'true') return true;
  return false;
}
try {
  let loginBtn = null;
  for (const b of btns) {
    if (!isVisible(b) || isDisabled(b)) continue;
    const t = ((b.innerText || b.textContent || b.value || '') + ' ' + (b.getAttribute('aria-label') || '')).replace(/\s+/g, ' ').trim();
    const low = t.toLowerCase();
    if (!t) continue;
    if (low.includes('返回') || low.includes('back') || low.includes('注册') || low.includes('sign up') || low.includes('忘记')) continue;
    if (low.includes('您正在登录') || low.includes('logging in') || low.includes('loading') || low.includes('请稍候')) continue;
    if (low.includes('登录') || low.includes('log in') || low.includes('sign in') || low.includes('continue') || low.includes('下一步') || low.includes('next')) {
      loginBtn = b; out.btn = t; break;
    }
  }
  if (loginBtn) {
    try { loginBtn.click(); out.click = true; } catch (e) { out.clickErr = String(e); }
  }
  if (form && form.requestSubmit) { form.requestSubmit(); out.submit = true; }
  else if (form) { form.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true})); out.submit = true; }
} catch (e) { out.submitErr = String(e); }
try {
  if (pw) {
    pw.focus();
    pw.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    pw.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    pw.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    out.enter = true;
  }
} catch (e) { out.enterErr = String(e); }
return out;
""") or {}
                log(f"[pending-sso] submit boost={boost}")
            except Exception as boost_exc:
                log(f"[pending-sso] submit boost fail: {boost_exc}")

            # Hard wait: do NOT re-fill immediately; re-fill used to interrupt in-flight login.
            try:
                sleep_with_cancel(2.5, stop)
            except Exception:
                pass

            sso = ""
            deadline = time.time() + 120
            last_url = ""
            last_err = ""
            last_body = ""
            visited_accounts = False
            visited_grok = False
            refill_tries = 0
            harvest_rounds = 0
            last_refill_ts = 0.0
            left_signin_once = False
            cf_seen = False
            post_submit_quiet_until = submit_ts + 12.0  # first 12s: observe only

            loading_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const body = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 280);
const low = body.toLowerCase();
const hasCf = !!(document.querySelector('#challenge-form, #cf-challenge-running, .cf-browser-verification, iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]')
  || low.includes('checking your browser') || low.includes('just a moment') || low.includes('verify you are human')
  || low.includes('正在验证') || low.includes('人机验证') || low.includes('请完成验证'));
// NOTE: page heading itself is often "您正在登录" — do NOT treat that alone as loading.
const loadingText = low.includes('logging in') || low.includes('signing in') || low.includes('请稍候') || low.includes('please wait') || (low.includes('loading') && !low.includes('log in'));
const busyBtn = Array.from(document.querySelectorAll('button,[role="button"]')).some(b => {
  if (!isVisible(b)) return false;
  const ariaBusy = (b.getAttribute('aria-busy') || '').toLowerCase() === 'true';
  if (ariaBusy || b.disabled) return true;
  const t = ((b.innerText || b.textContent || '') + '').replace(/\s+/g,' ').trim().toLowerCase();
  // only spinner-like exclusive labels
  if (!t) return false;
  if (t === 'loading' || t === '请稍候' || t === 'logging in' || t === 'signing in') return true;
  return false;
});
return {
  url: location.href,
  body: body,
  hasCf: hasCf,
  loading: loadingText || busyBtn,
  hasPw: !!Array.from(document.querySelectorAll('input[type="password"]')).find(isVisible),
  title: document.title || ''
};
"""

            while time.time() < deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                harvest_rounds += 1
                now = time.time()

                sso = _collect_sso_from_page(page, browser=browser, log=log)
                if sso and len(sso) >= 20:
                    log(f"[pending-sso] sso harvested len={len(sso)} round={harvest_rounds}")
                    break

                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                if cur and cur != last_url:
                    log(f"[pending-sso] url={cur}")
                    last_url = cur

                try:
                    pst = page.run_js(page_state_js) or {}
                except Exception as pst_exc:
                    pst = {"error": str(pst_exc)}

                try:
                    loadst = page.run_js(loading_js) or {}
                except Exception:
                    loadst = {}

                page_err = ""
                body = ""
                if isinstance(pst, dict):
                    page_err = str(pst.get("err") or "").strip()
                    body = str(pst.get("body") or "")
                    if body and body != last_body and (page_err or harvest_rounds <= 4 or harvest_rounds % 6 == 0):
                        log(f"[pending-sso] page body={body}")
                        last_body = body
                    body_low = body.lower()
                    if (not page_err) and body and (
                        "an error occurred" in body_low
                        or "something went wrong" in body_low
                        or "无法登录" in body
                        or "登录失败" in body
                        or "出错了" in body
                    ):
                        page_err = "auth_error"
                    if page_err and page_err != last_err:
                        log(f"[pending-sso] page_err={page_err} body={body}")
                        last_err = page_err
                        if page_err in {"bad_password", "account_missing", "auth_error"}:
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=page_err,
                            )
                    cookie_doc = str(pst.get("cookie") or "")
                    sso_doc = _extract_sso_from_cookie_blob(cookie_doc)
                    if sso_doc:
                        sso = sso_doc
                        log(f"[pending-sso] sso from document.cookie len={len(sso)}")
                        break

                has_cf = bool(isinstance(loadst, dict) and loadst.get("hasCf")) or page_err == "captcha"
                is_loading = bool(isinstance(loadst, dict) and loadst.get("loading"))
                if has_cf:
                    cf_seen = True
                    if harvest_rounds == 1 or harvest_rounds % 5 == 0:
                        log(f"[pending-sso] waiting cloudflare/captcha round={harvest_rounds} url={cur}")
                    # Never jump away while CF challenge is up.
                    sleep_with_cancel(1.5, stop)
                    continue

                left_signin = bool(cur) and ("sign-in" not in cur)
                on_consent = bool(cur) and ("consent" in cur or "authorize" in cur or "set-cookie" in cur or "auth" in cur)
                if left_signin or on_consent:
                    left_signin_once = True

                # Only after confirmed leave-sign-in, materialize cookies on accounts/grok.
                if left_signin_once and (not sso) and (left_signin or on_consent):
                    if not visited_accounts:
                        visited_accounts = True
                        try:
                            log("[pending-sso] left sign-in -> open accounts.x.ai to materialize sso cookies")
                            page.get("https://accounts.x.ai/")
                            try:
                                page.wait.doc_loaded()
                            except Exception:
                                pass
                            sleep_with_cancel(1.5, stop)
                            sso = _collect_sso_from_page(page, browser=browser, log=log)
                            if sso:
                                log(f"[pending-sso] sso after accounts.x.ai len={len(sso)}")
                                break
                        except Exception as acc_exc:
                            log(f"[pending-sso] open accounts.x.ai fail: {acc_exc}")
                    if (not sso) and (not visited_grok):
                        visited_grok = True
                        try:
                            log("[pending-sso] left sign-in -> open grok.com to materialize session cookies")
                            page.get("https://grok.com/")
                            try:
                                page.wait.doc_loaded()
                            except Exception:
                                pass
                            sleep_with_cancel(1.8, stop)
                            sso = _collect_sso_from_page(page, browser=browser, log=log)
                            if sso:
                                log(f"[pending-sso] sso after grok.com len={len(sso)}")
                                break
                        except Exception as grok_exc:
                            log(f"[pending-sso] open grok.com fail: {grok_exc}")

                # Still on sign-in: wait quietly after submit; re-fill only if settled and no progress.
                if ("sign-in" in (cur or "")) and (not sso):
                    quiet = now < post_submit_quiet_until
                    if quiet or is_loading:
                        if harvest_rounds <= 3 or harvest_rounds % 4 == 0:
                            log(
                                f"[pending-sso] post-submit wait quiet={quiet} loading={is_loading} "
                                f"cf={cf_seen} elapsed={now - submit_ts:.1f}s url={cur}"
                            )
                        sleep_with_cancel(1.2, stop)
                        continue

                    # Allow re-fill only after quiet window + 10s since last refill, max 3.
                    can_refill = (
                        refill_tries < 3
                        and (now - last_refill_ts) >= 10.0
                        and (now - submit_ts) >= 12.0
                        and (not is_loading)
                        and (not has_cf)
                    )
                    if can_refill:
                        try:
                            st = page.run_js(wait_inputs_js) or {}
                        except Exception:
                            st = {}
                        if isinstance(st, dict) and st.get("ready"):
                            refill_tries += 1
                            last_refill_ts = now
                            post_submit_quiet_until = now + 12.0
                            try:
                                fill_state = page.run_js(fill_js, email, password) or {}
                                log(f"[pending-sso] re-fill/sign-in try={refill_tries} after_wait {fill_state}")
                                try:
                                    page.run_js(r"""
const form=document.querySelector('form');
const pw=document.querySelector('input[type="password"]');
const btns=Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]'));
function isVisible(node){if(!node)return false;const s=getComputedStyle(node);if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0')return false;const r=node.getBoundingClientRect();return r.width>0&&r.height>0;}
function isDisabled(node){if(!node)return true;if(node.disabled)return true;return (node.getAttribute('aria-disabled')||'').toLowerCase()==='true';}
let clicked=false;
for (const b of btns){
  if(!isVisible(b)||isDisabled(b)) continue;
  const t=((b.innerText||b.textContent||b.value||'')+' '+(b.getAttribute('aria-label')||'')).replace(/\s+/g,' ').trim().toLowerCase();
  if(!t) continue;
  if(t.includes('返回')||t.includes('back')||t.includes('注册')||t.includes('sign up')||t.includes('忘记')) continue;
  if(t.includes('您正在登录')||t.includes('logging in')||t.includes('loading')) continue;
  if(t.includes('登录')||t.includes('log in')||t.includes('sign in')||t.includes('continue')||t.includes('下一步')||t.includes('next')){
    try{b.click();clicked=true;break;}catch(e){}
  }
}
if(form&&form.requestSubmit) form.requestSubmit();
if(pw){pw.focus();pw.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));}
return {clicked:clicked};
""")
                                except Exception:
                                    pass
                            except Exception as refill_exc:
                                log(f"[pending-sso] re-fill fail: {refill_exc}")
                            sleep_with_cancel(2.0, stop)
                            continue

                    # DO NOT jump to grok while still stuck on sign-in without leaving once.
                    if (not visited_accounts) and (now - submit_ts) >= 55 and harvest_rounds >= 25:
                        visited_accounts = True
                        try:
                            log("[pending-sso] long-wait soft probe accounts.x.ai (still may be unauthenticated)")
                            page.get("https://accounts.x.ai/")
                            sleep_with_cancel(1.5, stop)
                            sso = _collect_sso_from_page(page, browser=browser, log=log)
                            if sso:
                                log(f"[pending-sso] sso after long-wait accounts probe len={len(sso)}")
                                break
                            try:
                                page.get("https://accounts.x.ai/sign-in?redirect=grok-com")
                            except Exception:
                                pass
                        except Exception as acc_exc:
                            log(f"[pending-sso] long-wait accounts probe fail: {acc_exc}")

                sleep_with_cancel(1.0, stop)

            if not sso:
                try:
                    pst = page.run_js(page_state_js) or {}
                except Exception:
                    pst = {}
                log(f"[pending-sso] no sso after sign-in email={email} last_fill={fill_state} last_page={pst}")
                return result(STATUS_FAIL, email=email, detail=f"no sso after sign-in page={pst}")

            try:
                from protocol.sso_util import (
                    is_session_sso,
                    is_wrapper_sso,
                    materialize_sso_via_browser,
                    materialize_sso_via_http,
                )
                if is_wrapper_sso(sso) or not is_session_sso(sso):
                    log(f"[pending-sso] materialize wrapper sso len={len(sso)}")
                    sess_sso = ""
                    try:
                        page2 = _get_page()
                        sess_sso = materialize_sso_via_browser(page2, sso, log=log, timeout=40)
                    except Exception:
                        sess_sso = ""
                    if not sess_sso or not is_session_sso(sess_sso):
                        try:
                            sess_sso = materialize_sso_via_http(
                                sso,
                                proxy=proxy,
                                log=log,
                            ) or sess_sso
                        except Exception:
                            pass
                    if sess_sso and is_session_sso(sess_sso):
                        sso = sess_sso
                        log(f"[pending-sso] session sso ready len={len(sso)}")
            except Exception as mat_exc:
                log(f"[pending-sso] sso materialize: {mat_exc}")

            out_path = accounts_file or (
                ROOT / f"accounts_pending_sso_recovered_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            )
            try:
                line = f"{email}----{password}----{sso}\n"
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(line)
                log(f"[pending-sso] saved recovered account -> {out_path.name}")
            except Exception as save_exc:
                log(f"[pending-sso] save recovered fail: {save_exc}")

            try:
                remove_pending_sso_account(email, log=log)
            except Exception as rm_exc:
                log(f"[pending-sso] remove pending entry fail: {rm_exc}")

            jar_full = {}
            try:
                jar_full = dict(browser.export_cookies() or {})
            except Exception:
                jar_full = {}
            jar_full["sso"] = sso
            jar_full["sso-rw"] = jar_full.get("sso-rw") or sso
            cookie_list = [{"name": k, "value": v} for k, v in jar_full.items()]

            if post_success:
                try:
                    schedule_post_registration(
                        email, password, sso, page=None, cookies=cookie_list, log_callback=log
                    )
                except Exception as post_exc:
                    log(f"[pending-sso] post_success: {post_exc}")

            log(f"[pending-sso][+] recovered email={email} sso_len={len(sso)} elapsed={time.time()-t0:.1f}s")
            return result(STATUS_SUCCESS, email=email, sso_len=len(sso), accounts_file=str(out_path))

    except Exception as exc:
        if stop():
            log("[pending-sso] stopped during recover")
            return result(STATUS_STOPPED, email=email)
        log(f"[pending-sso] exception: {exc}")
        import traceback
        try:
            log(traceback.format_exc())
        except Exception:
            pass
        return result(STATUS_FAIL, email=email, detail=str(exc))


def run_pending_sso_recovery_job(count=0, log_callback=None, controller=None):
    """Recover SSO for pending accounts via browser sign-in."""
    import grok_register_ttk as engine

    log = log_callback or engine.cli_log
    if controller is None:
        controller = engine.CliStopController()

    pending = load_pending_sso_accounts(include_timestamped=True)
    if count and count > 0:
        pending = pending[: int(count)]

    success_count = 0
    fail_count = 0
    skipped = 0
    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_pending_sso_recovered_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] pending_sso 二次补 SSO 启动，待处理: {len(pending)}（count限制={count or 'all'}）")
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")

    mode = str(engine.config.get("proxy_mode", "direct") or "direct")
    try:
        resolved_proxy = engine.apply_resolved_proxy_to_config(log_callback=log, fetch_live=True)
    except Exception as proxy_exc:
        log(f"[!] 获取/解析代理失败: {proxy_exc}")
        raise
    if resolved_proxy:
        log(f"[*] 代理模式: {mode} | {resolved_proxy}")
    else:
        log(f"[*] 代理模式: {mode or 'direct'}（直连）")
    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    try:
        if not pending:
            log("[*] pending_sso 列表为空，无需恢复")
        for i, item in enumerate(pending):
            if controller.should_stop():
                break
            email = item.get("email") or ""
            password = item.get("password") or ""
            log(f"--- [pending-sso] 开始第 {i + 1}/{len(pending)} 个账号 email={email} source={item.get('source')} ---")
            raw = recover_one_pending_sso(
                email=email,
                password=password,
                log=log,
                proxy=proxy,
                should_stop=controller.should_stop,
                post_success=True,
                accounts_file=Path(accounts_output_file),
            )
            res = normalize_result(raw)
            status = res.get("status")
            detail = str(res.get("detail") or "")
            fail_reason = str(res.get("fail_reason") or "")
            if not fail_reason:
                low = detail.lower()
                if "bad_password" in low or "page_err=bad_password" in low:
                    fail_reason = "bad_password"
                elif "account_missing" in low or "page_err=account_missing" in low:
                    fail_reason = "account_missing"
                elif "auth_error" in low or "page_err=auth_error" in low or "an error occurred" in low:
                    fail_reason = "auth_error"
            if controller.should_stop() or status == STATUS_STOPPED:
                log("[*] 当前 pending 恢复因停止请求中断，统计保持不变")
                break
            if status == STATUS_SUCCESS:
                success_count += 1
            else:
                fail_count += 1
                # 密码错误/账号不存在：不是简单丢弃，移出 pending 后走注册主流程重跑
                if fail_reason in {"bad_password", "account_missing", "auth_error"} or res.get("remove_pending"):
                    try:
                        remove_pending_sso_account(email, log=log)
                        log(
                            f"[pending-sso] {fail_reason or 'auth_fail'} -> 移出 pending，改走注册流程 email={email}"
                        )
                    except Exception as rm_exc:
                        log(f"[pending-sso] remove pending before re-register fail: {rm_exc}")
                    if not controller.should_stop():
                        try:
                            from hybrid_register import register_one_hybrid
                            log(f"[pending-sso] re-register via hybrid start (reason={fail_reason or detail})")
                            re_accounts = Path(accounts_output_file)
                            # also keep a dedicated re-register success sink
                            try:
                                re_accounts = ROOT / f"accounts_reregistered_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt"
                            except Exception:
                                re_accounts = ROOT / f"accounts_reregistered_{time.strftime('%Y%m%d_%H%M%S')}.txt"
                            rr = register_one_hybrid(
                                log=log,
                                proxy=proxy,
                                should_stop=controller.should_stop,
                                accounts_file=re_accounts,
                                post_success=True,
                            )
                            rr = normalize_result(rr)
                            rr_status = rr.get("status")
                            log(f"[pending-sso] re-register result status={rr_status} detail={rr.get('detail')}")
                            if rr_status == STATUS_SUCCESS:
                                success_count += 1
                                fail_count = max(0, fail_count - 1)
                            elif rr_status == STATUS_PENDING_SSO:
                                log("[pending-sso] re-register got pending_sso again; kept as pending fallback")
                            elif rr_status == STATUS_STOPPED:
                                log("[pending-sso] re-register stopped")
                                break
                            elif rr_status == STATUS_POOL_EMPTY:
                                skipped += 1
                                log("[pending-sso] re-register pool empty")
                        except Exception as reg_exc:
                            log(f"[pending-sso] re-register exception: {reg_exc}")
                            try:
                                log(traceback.format_exc())
                            except Exception:
                                pass
            log(f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count} | pending_sso 0 | 跳过(池空) {skipped}")
            engine.sleep_with_cancel(1, controller.should_stop)
    except KeyboardInterrupt:
        controller.stop()
        log("[!] 收到 Ctrl+C，正在停止")
    except Exception as exc:
        log(f"[!] pending_sso 恢复任务异常: {exc}")
        try:
            log(traceback.format_exc())
        except Exception:
            pass
    finally:
        try:
            if controller.should_stop():
                engine.force_stop_registration(log_callback=log, reason="pending_sso_job_stopped")
            else:
                engine.stop_browser(log_callback=log)
        except Exception as stop_exc:
            log(f"[!] pending finally stop browser: {stop_exc}")
        try:
            engine.wait_post_success_queue(timeout=15 if controller.should_stop() else 45, log_callback=log)
        except Exception:
            pass
        try:
            engine.cleanup_runtime_memory(log_callback=log, reason="pending_sso 恢复任务结束")
        except Exception:
            pass
        log(f"[*] pending_sso 恢复结束。成功 {success_count} | 失败 {fail_count} | pending_sso 0 | 跳过(池空) {skipped}")

    return {
        "success": success_count,
        "fail": fail_count,
        "pending_sso": 0,
        "skipped": skipped,
        "pool_empty": False,
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
        "job": "pending_sso_recovery",
    }
