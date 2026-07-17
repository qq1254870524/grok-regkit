"""Pending SSO recovery helpers for grok-regkit hybrid.

2026-07-18e: pool-empty stop support helpers + pending_sso secondary recovery.

2026-07-18g: pending sign-in 直达、等待真实输入框、禁点“您正在登录/Loading”。
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
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]');
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]');
return {
  url: location.href,
  title: document.title || '',
  email: !!emailInput,
  pw: !!pwInput,
  ready: !!(emailInput && pwInput),
  body: (document.body && document.body.innerText || '').slice(0, 180).replace(/\s+/g, ' ')
};
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
            wait_deadline = time.time() + 35
            last_wait = {}
            while time.time() < wait_deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    last_wait = page.run_js(wait_inputs_js) or {}
                except Exception as wait_exc:
                    last_wait = {"error": str(wait_exc)}
                if isinstance(last_wait, dict) and last_wait.get("ready"):
                    ready = True
                    break
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

            sso = ""
            deadline = time.time() + 75
            last_url = ""
            while time.time() < deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                jar = {}
                try:
                    jar = dict(browser.export_cookies() or {})
                except Exception:
                    jar = {}
                sso = str(jar.get("sso") or jar.get("sso-rw") or "").strip()
                if sso and len(sso) >= 20:
                    break
                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                if cur and cur != last_url:
                    log(f"[pending-sso] url={cur}")
                    last_url = cur
                if "sign-in" in cur and not sso:
                    try:
                        st = page.run_js(wait_inputs_js) or {}
                    except Exception:
                        st = {}
                    if isinstance(st, dict) and st.get("ready"):
                        try:
                            page.run_js(fill_js, email, password)
                        except Exception:
                            pass
                sleep_with_cancel(1.0, stop)

            if not sso:
                log(f"[pending-sso] no sso after sign-in email={email} last_fill={fill_state}")
                return result(STATUS_FAIL, email=email, detail="no sso after sign-in")

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
            if controller.should_stop() or status == STATUS_STOPPED:
                log("[*] 当前 pending 恢复因停止请求中断，统计保持不变")
                break
            if status == STATUS_SUCCESS:
                success_count += 1
            else:
                fail_count += 1
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
