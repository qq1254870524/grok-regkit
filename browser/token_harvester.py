"""Browser-only token harvest for Castle / Turnstile (hybrid mode).
2026-07-18g: scrape_next_action 优先 createUserAndSession 邻域，避免抓到 CreateEmail。
2026-07-18i: 恢复主路径 scrape 回退：createUserAndSession → emailValidationCode+castleRequestToken → hook；
              不改变 hybrid 主流程（注册当时即时 SSO + schedule_post_registration；pending 仅兜底）。
2026-07-18j: 新增 scrape_next_action_candidates 多候选；单候选自动拒绝 hybrid 已知死 hash。
2026-07-18k: browser-fetch 用闭包绑定参数（修复 async IIFE arguments 全空导致 next-action 空串 404）；
              解析 Set-Cookie/sso；不再把当前 live SignUp hash 当死 hash 过滤。
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@dataclass
class HarvestedTokens:
    turnstile: str = ""
    castle: str = ""
    page_url: str = ""
    cookies: dict = field(default_factory=dict)
    next_action: str = ""


class BrowserTokenSession:
    """One Chromium session dedicated to token / cookie harvest."""

    def __init__(self, log: Optional[Callable[[str], None]] = None):
        self.log = log or (lambda _m: None)
        self._started = False
        self._hooked = False

    def _lg(self, msg: str):
        try:
            self.log(msg)
        except Exception:
            pass

    def start(self):
        from grok_register_ttk import start_browser

        start_browser(log_callback=self.log)
        self._started = True
        return self

    def install_network_hook(self) -> bool:
        """Capture castleRequestToken and next-action from native React fetch/XHR."""
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            res = page.run_js(
                r"""
(function(){
  if (window.__hybrid_net_hooked) return 'already';
  window.__hybrid_net_hooked = true;
  window.__hybrid_castles = [];
  window.__hybrid_castle = '';
  window.__hybrid_net = [];
  window.__hybrid_next_actions = window.__hybrid_next_actions || [];
  window.__hybrid_next_action = window.__hybrid_next_action || '';
  window.__hybrid_create_email_ok = false;
  window.__hybrid_create_email_status = 0;
  function pushNextAction(v) {
    try {
      const s = String(v || '').trim();
      if (!/^[a-f0-9]{40,64}$/i.test(s)) return;
      window.__hybrid_next_action = s;
      if (window.__hybrid_next_actions.indexOf(s) < 0) {
        window.__hybrid_next_actions.push(s);
      }
    } catch (e) {}
  }
  function captureHeaders(headers) {
    try {
      if (!headers) return;
      if (typeof headers.forEach === 'function') {
        headers.forEach(function(val, key){
          if (String(key || '').toLowerCase() === 'next-action') pushNextAction(val);
        });
        return;
      }
      if (typeof headers.get === 'function') {
        pushNextAction(headers.get('next-action') || headers.get('Next-Action'));
        return;
      }
      if (Array.isArray(headers)) {
        for (const pair of headers) {
          if (!pair) continue;
          const k = pair[0] != null ? pair[0] : (pair.name || '');
          const v = pair[1] != null ? pair[1] : (pair.value || '');
          if (String(k).toLowerCase() === 'next-action') pushNextAction(v);
        }
        return;
      }
      for (const k of Object.keys(headers || {})) {
        if (String(k).toLowerCase() === 'next-action') pushNextAction(headers[k]);
      }
    } catch (e) {}
  }
  function captureBody(body, url) {
    try {
      if (!body) return;
      let s = '';
      if (typeof body === 'string') s = body;
      else if (body instanceof ArrayBuffer) s = new TextDecoder().decode(body);
      else if (body instanceof Uint8Array) s = new TextDecoder().decode(body);
      else return;
      const u = String(url||'');
      window.__hybrid_net.push({url: u, len: s.length});
      if (u.includes('CreateEmailValidationCode')) {
        window.__hybrid_create_email_seen = true;
      }
      if (s.includes('castleRequestToken')) {
        try {
          const j = JSON.parse(s);
          const tok = j && j[0] && j[0].castleRequestToken;
          if (tok && String(tok).length > 200) {
            window.__hybrid_castle = String(tok);
            window.__hybrid_castles.push(String(tok));
          }
        } catch (e) {
          const m = s.match(/castleRequestToken["']?\s*:\s*["']([^"']{200,})/);
          if (m) {
            window.__hybrid_castle = m[1];
            window.__hybrid_castles.push(m[1]);
          }
        }
      }
      const m2 = s.match(/IBYIll\|[A-Za-z0-9+/=|_-]{200,}/);
      if (m2) {
        window.__hybrid_castle = m2[0];
        window.__hybrid_castles.push(m2[0]);
      }
      const m3 = s.match(/["']next-action["']\s*[:=]\s*["']([a-f0-9]{40,64})["']/i);
      if (m3) pushNextAction(m3[1]);
    } catch (e) {}
  }
  const ofetch = window.fetch;
  window.fetch = async function(input, init) {
    let url = '';
    try {
      url = (typeof input === 'string') ? input : (input && input.url) || '';
      captureBody(init && init.body, url);
      captureHeaders(init && init.headers);
      if (input && typeof input === 'object') {
        try { captureHeaders(input.headers); } catch (e) {}
      }
    } catch (e) {}
    const resp = await ofetch.apply(this, arguments);
    try {
      if (String(url).includes('CreateEmailValidationCode')) {
        window.__hybrid_create_email_status = resp.status || 0;
        window.__hybrid_create_email_ok = !!(resp.ok || (resp.status >= 200 && resp.status < 300));
      }
    } catch (e) {}
    return resp;
  };
  const oopen = XMLHttpRequest.prototype.open;
  const oset = XMLHttpRequest.prototype.setRequestHeader;
  const osend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; return oopen.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function(k,v){
    try {
      if (String(k || '').toLowerCase() === 'next-action') pushNextAction(v);
    } catch (e) {}
    return oset.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body){
    captureBody(body, this.__u);
    const xhr = this;
    try {
      xhr.addEventListener('load', function(){
        try {
          if (String(xhr.__u||'').includes('CreateEmailValidationCode')) {
            window.__hybrid_create_email_status = xhr.status || 0;
            window.__hybrid_create_email_ok = xhr.status >= 200 && xhr.status < 300;
          }
        } catch (e) {}
      });
    } catch (e) {}
    return osend.apply(this, arguments);
  };
  return 'hooked';
})();
"""
            )
            self._hooked = True
            self._lg(f"[*] net hook={res}")
            return True
        except Exception as e:
            self._lg(f"[Debug] net hook: {e}")
            return False


    def create_email_status_via_browser(self) -> dict:
        """Return detailed CreateEmailValidationCode network evidence from page hook."""
        from grok_register_ttk import _get_page

        page = _get_page()
        data = {
            "ok": False,
            "status": 0,
            "seen": False,
            "castle_len": 0,
            "net_hits": 0,
            "sent": False,
            "reason": "no_data",
        }
        try:
            raw = page.run_js(
                """
const net = window.__hybrid_net || [];
const hits = net.filter(n => String((n&&n.url)||'').includes('CreateEmailValidationCode'));
return {
  ok: !!window.__hybrid_create_email_ok,
  status: Number(window.__hybrid_create_email_status||0),
  seen: !!window.__hybrid_create_email_seen,
  castle_len: Number((window.__hybrid_castle||'').length||0),
  net_hits: hits.length,
  net_urls: hits.slice(0, 5).map(n => String((n&&n.url)||'').slice(0, 160))
};
"""
            )
            if isinstance(raw, dict):
                data.update(
                    {
                        "ok": bool(raw.get("ok")),
                        "status": int(raw.get("status") or 0),
                        "seen": bool(raw.get("seen")),
                        "castle_len": int(raw.get("castle_len") or 0),
                        "net_hits": int(raw.get("net_hits") or 0),
                        "net_urls": list(raw.get("net_urls") or []),
                    }
                )
        except Exception as exc:
            data["reason"] = f"js_error:{exc}"
            return data

        status = int(data.get("status") or 0)
        ok = bool(data.get("ok"))
        seen = bool(data.get("seen")) or int(data.get("net_hits") or 0) > 0
        # Strict: only treat as sent when CreateEmail request was observed.
        # Do NOT treat "have castle only" as CreateEmail success.
        if ok and (status == 0 or 200 <= status < 300):
            data["sent"] = True
            data["reason"] = f"ok_status={status}"
        elif seen and 200 <= status < 300:
            data["sent"] = True
            data["reason"] = f"seen_status={status}"
        elif seen and status == 0:
            data["sent"] = True
            data["reason"] = "seen_status_unknown"
        elif seen and status >= 400:
            data["sent"] = False
            data["reason"] = f"seen_http_{status}"
        else:
            data["sent"] = False
            data["reason"] = "not_seen"
        return data

    def create_email_sent_via_browser(self) -> bool:
        st = self.create_email_status_via_browser()
        return bool(st.get("sent"))


    def click_email_continue_for_create(self, email: str) -> str:
        """Fill email field (React-safe), verify value, click Continue/发送 not generic 注册."""
        from grok_register_ttk import _get_page, click_email_signup_button

        page = _get_page()
        email = str(email or "").strip()
        if not email:
            return "empty-email"

        # Ensure we are on email-input step (not method chooser)
        try:
            state = page.run_js(
                """
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const emailInput = Array.from(document.querySelectorAll('input, textarea')).some((n) => {
  if (!isVisible(n) || n.disabled) return false;
  const type = String(n.type || '').toLowerCase();
  if (['password','hidden','checkbox','radio','submit','button'].includes(type)) return false;
  const meta = [type, n.name, n.id, n.placeholder, n.getAttribute('data-testid'), n.getAttribute('aria-label'), n.autocomplete].join(' ').toLowerCase();
  return type === 'email' || meta.includes('email') || meta.includes('mail');
});
return {url: location.href, emailInput: !!emailInput, title: document.title || ''};
"""
            )
            self._lg(f"[*] UI page state before fill: {state}")
            if isinstance(state, dict) and not state.get("emailInput"):
                try:
                    click_email_signup_button(timeout=8, log_callback=self.log)
                    time.sleep(1.2)
                except Exception as e:
                    self._lg(f"[!] click_email_signup_button: {e}")
        except Exception as e:
            self._lg(f"[!] UI pre-state: {e}")

        # Prefer proven fill path used by profile step
        try:
            fill_r = self._set_input_and_submit(email, "email")
            self._lg(f"[*] UI _set_input_and_submit(email) => {fill_r} email={email}")
        except Exception as e:
            fill_r = f"set_input_error:{e}"
            self._lg(f"[!] UI _set_input_and_submit fail: {e}")

        # Explicit fill+click with value verification (full email in log, no redaction)
        try:
            detail = page.run_js(
                """
const email = String(arguments[0] || '');
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (!style) return false;
  if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity||1) === 0) return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function setInputValue(input, v) {
  input.focus();
  try { input.click(); } catch (e) {}
  const proto = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
    || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (setter) setter.call(input, '');
  else input.value = '';
  if (tracker) tracker.setValue('');
  if (setter) setter.call(input, v);
  else input.value = v;
  input.dispatchEvent(new Event('focus', {bubbles:true}));
  input.dispatchEvent(new InputEvent('beforeinput', {bubbles:true, data:v, inputType:'insertText'}));
  input.dispatchEvent(new InputEvent('input', {bubbles:true, data:v, inputType:'insertText'}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  input.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key:'a'}));
}
const all = Array.from(document.querySelectorAll('input, textarea'));
const candidates = all.map((n, idx) => {
  const type = String(n.type || n.getAttribute('type') || '').toLowerCase();
  const meta = [type, n.name, n.id, n.placeholder, n.getAttribute('data-testid'), n.getAttribute('aria-label'), n.autocomplete].join(' ').toLowerCase();
  return {
    idx,
    type,
    name: String(n.name||''),
    id: String(n.id||''),
    placeholder: String(n.placeholder||''),
    meta,
    visible: isVisible(n),
    disabled: !!n.disabled,
    value: String(n.value||''),
    emailish: type === 'email' || meta.includes('email') || meta.includes('mail') || meta.includes('邮箱')
  };
});
let input = all.find((n) => {
  if (!isVisible(n) || n.disabled) return false;
  const type = String(n.type || '').toLowerCase();
  if (['password','hidden','checkbox','radio','submit','button'].includes(type)) return false;
  const meta = [type, n.name, n.id, n.placeholder, n.getAttribute('data-testid'), n.getAttribute('aria-label'), n.autocomplete].join(' ').toLowerCase();
  return type === 'email' || meta.includes('email') || meta.includes('mail') || meta.includes('邮箱');
});
if (!input) {
  input = all.find((n) => isVisible(n) && !n.disabled && !['password','hidden','checkbox','radio','submit','button'].includes(String(n.type||'').toLowerCase()));
}
if (!input) {
  return {ok:false, reason:'no-input', candidates, url: location.href};
}
setInputValue(input, email);
const filled = String(input.value || '');
const filledOk = filled === email || filled.toLowerCase() === email.toLowerCase();
// Prefer Continue/发送/Next over generic 注册 when email already filled
const btnNodes = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], a'));
const scoreBtn = (n) => {
  if (!isVisible(n)) return -1;
  if (n.disabled || n.getAttribute('aria-disabled') === 'true') return -1;
  const t = ((n.innerText || n.textContent || n.value || n.getAttribute('aria-label') || '') + '')
    .replace(/\\s+/g, '').toLowerCase();
  let s = 0;
  if (t.includes('继续') || t.includes('continue')) s += 100;
  if (t.includes('下一步') || t.includes('next')) s += 90;
  if (t.includes('发送') || t.includes('send') || t.includes('submit')) s += 85;
  if (t.includes('验证') || t.includes('verify') || t.includes('confirm') || t.includes('确认')) s += 70;
  if (String(n.getAttribute('type')||'').toLowerCase() === 'submit') s += 40;
  // demote method-switch buttons after email is filled
  if (t.includes('注册') || t.includes('signup') || t.includes('sign-up') || t.includes('createaccount')) s += 10;
  if (t.includes('google') || t.includes('apple') || t.includes('github') || t.includes('登录') || t.includes('login') || t.includes('使用邮箱')) s -= 100;
  return s;
};
let best = null, bestScore = 0, ranked = [];
for (const n of btnNodes) {
  const sc = scoreBtn(n);
  const t = ((n.innerText || n.textContent || n.value || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 60);
  if (sc > 0) ranked.push({score: sc, text: t});
  if (sc > bestScore) { bestScore = sc; best = n; }
}
ranked.sort((a,b) => b.score - a.score);
let clickHow = 'none';
if (best && bestScore > 0) {
  try { best.scrollIntoView({block:'center', inline:'nearest'}); } catch (e) {}
  try { best.click(); clickHow = 'click'; }
  catch (e1) {
    try {
      best.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
      clickHow = 'mouse';
    } catch (e2) { clickHow = 'click-fail'; }
  }
} else {
  try {
    const form = input.form || input.closest('form');
    if (form && typeof form.requestSubmit === 'function') { form.requestSubmit(); clickHow = 'form-requestSubmit'; }
    else if (form) { form.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true})); clickHow = 'form-submit'; }
    else {
      input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
      clickHow = 'enter';
    }
  } catch (e) { clickHow = 'fallback-fail'; }
}
return {
  ok: filledOk && clickHow !== 'none' && clickHow !== 'click-fail' && clickHow !== 'fallback-fail',
  reason: filledOk ? ('filled+' + clickHow) : ('fill-mismatch+' + clickHow),
  filled: filled,
  expected: email,
  filledOk: filledOk,
  clickHow: clickHow,
  bestScore: bestScore,
  bestText: best ? ((best.innerText || best.textContent || best.value || '') + '').replace(/\\s+/g,' ').trim().slice(0,80) : '',
  ranked: ranked.slice(0, 8),
  url: location.href,
  candidates: candidates.filter(c => c.visible).slice(0, 12)
};
                """,
                email,
            )
        except Exception as e:
            detail = {"ok": False, "reason": f"js_error:{e}", "expected": email}

        self._lg(f"[*] UI email fill/click detail={detail}")
        if isinstance(detail, dict):
            if detail.get("filledOk"):
                self._lg(
                    f"[+] UI email filled OK value={detail.get('filled')} "
                    f"click={detail.get('clickHow')} btn={detail.get('bestText')!r} score={detail.get('bestScore')}"
                )
                return f"ok:{detail.get('clickHow')}:{detail.get('bestText')}"
            self._lg(
                f"[!] UI email NOT filled as expected expected={email} "
                f"got={detail.get('filled')!r} reason={detail.get('reason')} "
                f"candidates={detail.get('candidates')}"
            )
            return f"fail:{detail.get('reason')}"
        return f"detail:{detail}|fill_r:{fill_r}"


    def browser_user_agent(self) -> str:
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            ua = page.run_js("return navigator.userAgent || ''")
            return str(ua or "").strip()
        except Exception:
            return ""

    def read_captured_castle(self) -> str:
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            data = page.run_js(
                """
const list = window.__hybrid_castles || [];
let best = window.__hybrid_castle || '';
for (const t of list) {
  if (String(t||'').length > String(best||'').length) best = t;
}
return {castle: String(best||''), n: list.length};
"""
            )
            if isinstance(data, dict):
                c = str(data.get("castle") or "")
                if len(c) >= 1000 and c.startswith("IBYIll"):
                    return c
                if len(c) >= 2000:
                    return c
        except Exception:
            pass
        return ""


    def harvest_castle_via_email_submit(self, email: str, timeout: int = 40) -> str:
        """Fill email + click Continue/Send so native CreateEmail fires; capture castle."""
        from grok_register_ttk import _get_page

        if not self._hooked:
            self.install_network_hook()
        page = _get_page()
        # clear previous castle + CreateEmail evidence
        try:
            page.run_js(
                """
window.__hybrid_castle='';
window.__hybrid_castles=[];
window.__hybrid_net=[];
window.__hybrid_create_email_ok=false;
window.__hybrid_create_email_status=0;
window.__hybrid_create_email_seen=false;
true;
"""
            )
        except Exception:
            pass

        self._lg(f"[*] harvest CreateEmail start email={email} timeout={timeout}")
        click_r = self.click_email_continue_for_create(email)
        self._lg(f"[*] UI email submit click={click_r} email={email}")
        if str(click_r).startswith("fail:") or str(click_r) in ("no-input", "empty-email"):
            self._lg(f"[!] first email fill/click failed: {click_r} — will retry in loop")

        deadline = time.time() + max(15, int(timeout))
        last_retry = time.time()
        retries = 0
        # Hard limit: at most 1 re-click. Multiple CreateEmail on same mailbox
        # triggers xAI "验证码过多 / retry in N minutes".
        max_retries = 1
        while time.time() < deadline:
            st = self.create_email_status_via_browser()
            c = self.read_captured_castle()
            if st.get("sent"):
                self._lg(
                    f"[*] CreateEmail UI evidence sent=1 reason={st.get('reason')} "
                    f"status={st.get('status')} seen={st.get('seen')} net_hits={st.get('net_hits')} "
                    f"castle_len={st.get('castle_len') or (len(c) if c else 0)}"
                )
                # Once sent is confirmed, NEVER re-click even if castle is late.
                if c:
                    self._lg(f"[*] native castle len={len(c)} head={c[:20]}")
                    return c
                # wait a bit more for castle only; no more clicks
                time.sleep(0.45)
                continue
            elif c and (time.time() + 8) >= deadline:
                self._lg(
                    f"[!] CreateEmail not confirmed yet but castle present "
                    f"len={len(c)} reason={st.get('reason')} — wait without extra click"
                )

            if (not st.get("sent")) and (time.time() - last_retry >= 5.0) and retries < max_retries:
                retries += 1
                last_retry = time.time()
                try:
                    self._hooked = False
                    self.install_network_hook()
                except Exception:
                    pass
                click_r = self.click_email_continue_for_create(email)
                self._lg(
                    f"[*] UI CreateEmail retry#{retries}/{max_retries} click={click_r} email={email} "
                    f"status={st.get('status')} seen={st.get('seen')} ok={st.get('ok')} "
                    f"net_hits={st.get('net_hits')} reason={st.get('reason')} "
                    f"castle_len={st.get('castle_len')} full_status={st}"
                )
            time.sleep(0.45)

        st = self.create_email_status_via_browser()
        c = self.read_captured_castle()
        self._lg(
            f"[!] harvest end CreateEmail sent={st.get('sent')} reason={st.get('reason')} "
            f"status={st.get('status')} seen={st.get('seen')} net_hits={st.get('net_hits')} "
            f"castle_len={len(c) if c else 0}"
        )
        if c:
            self._lg(f"[*] native castle (unconfirmed CreateEmail) len={len(c)} head={c[:20]}")
            return c
        self._lg("[!] native castle timeout; try injected SDK")
        return self.get_castle_token_injected(timeout=15)

    def get_castle_token_injected(self, timeout: int = 45) -> str:
        """Legacy CDN inject path (often short / wrong format)."""
        return self._get_castle_token_injected_impl(timeout=timeout)

    def close(self):
        from grok_register_ttk import shutdown_browser

        try:
            shutdown_browser()
        except Exception:
            pass
        self._started = False

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
        return False

    def open_signup(self, cancel_callback=None):
        """Open signup in the current browser and honor an external stop request."""
        from grok_register_ttk import open_signup_page

        open_signup_page(log_callback=self.log, cancel_callback=cancel_callback)

    def export_cookies(self) -> dict:
        from grok_register_ttk import _get_browser

        jar = {}
        try:
            browser = _get_browser()
            cookies = browser.cookies() if browser else []
            for c in cookies or []:
                if isinstance(c, dict):
                    n, v = c.get("name", ""), c.get("value", "")
                else:
                    n, v = getattr(c, "name", ""), getattr(c, "value", "")
                if n:
                    jar[str(n)] = str(v)
        except Exception as e:
            self._lg(f"[Debug] export_cookies: {e}")
        return jar

    def read_captured_next_actions(self) -> list[str]:
        """Return next-action hashes captured by the page network hook."""
        from grok_register_ttk import _get_page
        import re as _re

        page = _get_page()
        out: list[str] = []
        try:
            raw = page.run_js(
                """
const arr = Array.isArray(window.__hybrid_next_actions) ? window.__hybrid_next_actions : [];
const cur = String(window.__hybrid_next_action || '').trim();
const all = arr.slice();
if (cur) all.unshift(cur);
return all.map(x => String(x || '').trim()).filter(Boolean).slice(0, 20);
"""
            )
            vals = raw if isinstance(raw, list) else ([raw] if raw else [])
            for v in vals:
                s = str(v or "").strip()
                if _re.fullmatch(r"[a-fA-F0-9]{40,64}", s) and s not in out:
                    out.append(s)
        except Exception as e:
            self._lg(f"[Debug] read captured next-actions: {e}")
        return out


    def scrape_next_action_candidates(self) -> list[str]:
        """Return ordered SignUp next-action candidates (deduped).

        Main registration path uses these for immediate SSO. Dead hashes are filtered
        when hybrid_register.is_dead_next_action is importable.
        """
        from grok_register_ttk import _get_page

        def _is_dead(v: str) -> bool:
            try:
                from hybrid_register import is_dead_next_action
                return bool(is_dead_next_action(v))
            except Exception:
                return False

        out: list[str] = []

        def _add(v: str, src: str = "") -> None:
            a = str(v or "").strip()
            if not a or len(a) < 40:
                return
            if _is_dead(a):
                self._lg(f"[*] scrape candidates skip dead src={src or '-'} hash={a[:20]}...")
                return
            if a not in out:
                out.append(a)
                self._lg(
                    f"[*] scrape candidate[{len(out)}] src={src or '-'} "
                    f"hash={a[:20]}... len={len(a)}"
                )

        try:
            for a in (self.read_captured_next_actions() or []):
                _add(a, "network_hook")
        except Exception as e:
            self._lg(f"[Debug] scrape candidates hook: {e}")

        page = _get_page()
        try:
            found = page.run_js(
                r"""
return (async function(){
  function collectFromText(t, bag) {
    if (!t) return;
    function pushNear(idx, radius) {
      if (idx < 0) return;
      const slice = t.slice(Math.max(0, idx - radius), idx + radius);
      const re = /createServerReference\)?\(['"]([a-f0-9]{40,})['"]/g;
      let m;
      while ((m = re.exec(slice)) !== null) bag.push(m[1]);
      const re2 = /['"]([a-f0-9]{40,64})['"]/g;
      while ((m = re2.exec(slice)) !== null) bag.push(m[1]);
    }
    pushNear(t.indexOf('createUserAndSession'), 1400);
    pushNear(t.indexOf('createUserAndSessionRequest'), 1400);
    pushNear(t.indexOf('emailValidationCode'), 1200);
    pushNear(t.indexOf('castleRequestToken'), 1200);
  }
  const bag = [];
  for (const s of Array.from(document.scripts || [])) {
    collectFromText(s.textContent || '', bag);
  }
  collectFromText(document.documentElement.innerHTML || '', bag);
  const scripts = Array.from(document.querySelectorAll('script[src*="/_next/static/chunks/"]'));
  const urls = scripts.map(s => s.src).filter(Boolean).slice(0, 100);
  for (const url of urls) {
    try {
      const t = await fetch(url, {credentials:'same-origin'}).then(r => r.text());
      if (!t) continue;
      if (!(
        t.includes('createUserAndSession') ||
        t.includes('emailValidationCode') ||
        t.includes('castleRequestToken')
      )) continue;
      collectFromText(t, bag);
    } catch (e) {}
  }
  const seen = new Set();
  const out = [];
  for (const h of bag) {
    if (!h || seen.has(h)) continue;
    seen.add(h);
    out.push(h);
  }
  return out.slice(0, 12);
})();
"""
            )
            if isinstance(found, list):
                for a in found:
                    _add(a, "browser_multi")
            elif found:
                _add(str(found), "browser_multi")
        except Exception as e:
            self._lg(f"[Debug] scrape candidates multi: {e}")

        if not out:
            try:
                one = (self.scrape_next_action() or "").strip()
                _add(one, "browser_scrape_single")
            except Exception as e:
                self._lg(f"[Debug] scrape candidates single fallback: {e}")
        return out

    def scrape_next_action(self) -> str:
        """Find SignUp server-action hash from network hook, HTML, or Next.js chunks.

        Priority (main registration path, not pending recovery):
        1) createUserAndSession neighborhood (true SignUp)
        2) legacy signup markers: emailValidationCode + castleRequestToken
        3) network-hook captured next-action (last resort; may be CreateEmail)
        """
        from grok_register_ttk import _get_page

        def _reject_dead_action(val: str) -> str:
            a = str(val or "").strip()
            if not a:
                return ""
            try:
                from hybrid_register import is_dead_next_action
                if is_dead_next_action(a):
                    self._lg(f"[*] scrape next-action reject dead hash={a[:20]}...")
                    return ""
            except Exception:
                pass
            return a


        # Network hook may capture CreateEmail/other actions. Prefer SignUp-marked
        # chunk/HTML hashes first; use hook only as a secondary candidate source.
        hook_actions = []
        try:
            hook_actions = self.read_captured_next_actions() or []
            if hook_actions:
                self._lg(
                    f"[*] scrape next-action network hook candidates "
                    f"count={len(hook_actions)} first={str(hook_actions[0])[:20]}..."
                )
        except Exception as e:
            self._lg(f"[Debug] scrape next-action hook: {e}")

        page = _get_page()
        try:
            # Fast path: inline HTML / inline scripts
            action = page.run_js(
                r"""
function pickSignupAction(t) {
  if (!t) return '';
  // 1) Strict: hashes near createUserAndSession (true SignUp).
  const idxCu = t.indexOf('createUserAndSession');
  if (idxCu >= 0) {
    const sliceCu = t.slice(Math.max(0, idxCu - 800), idxCu + 1200);
    let m = sliceCu.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
    if (m) return m[1];
    m = sliceCu.match(/['\"]([a-f0-9]{40,64})['\"]/);
    if (m) return m[1];
  }
  // 2) Legacy working markers used before strict-only scrape:
  //    SignUp payload fields emailValidationCode + castleRequestToken.
  if (t.includes('emailValidationCode') && t.includes('castleRequestToken')) {
    let m = t.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
    if (m) return m[1];
    const idx = t.indexOf('emailValidationCode');
    if (idx >= 0) {
      const slice = t.slice(Math.max(0, idx - 600), idx + 900);
      m = slice.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
      if (m) return m[1];
      m = slice.match(/[a-f0-9]{40,64}/);
      if (m) return m[0];
    }
  }
  return '';
}
// Prefer inline scripts with signup markers. Do NOT grab arbitrary next-action from full HTML.
for (const s of Array.from(document.scripts || [])) {
  const hit = pickSignupAction(s.textContent || '');
  if (hit) return hit;
}
const html = document.documentElement.innerHTML || '';
// Prefer marker-based pick; last inline fallback is explicit next-action attr near signup form.
let hit = pickSignupAction(html);
if (hit) return hit;
const mAttr = html.match(/next-action["'\s:=]+([a-f0-9]{40,})/i);
return mAttr ? mAttr[1] : '';
"""
            )
            if action:
                action = _reject_dead_action(str(action))
                if action:
                    self._lg(
                        f"[*] scrape next-action from inline signup markers "
                        f"len={len(action)} value={action[:20]}..."
                    )
                    return action
        except Exception as e:
            self._lg(f"[Debug] scrape next-action inline: {e}")

        # Slow path: fetch external chunks (hash lives in createServerReference chunk)
        try:
            action = page.run_js(
                r"""
return (async function(){
  function pickFromText(t) {
    if (!t) return '';
    // 1) createUserAndSession neighborhood
    const idxCu = t.indexOf('createUserAndSession');
    if (idxCu >= 0) {
      const sliceCu = t.slice(Math.max(0, idxCu - 800), idxCu + 1200);
      let m = sliceCu.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
      if (m) return m[1];
      m = sliceCu.match(/['\"]([a-f0-9]{40,64})['\"]/);
      if (m) return m[1];
    }
    // 2) legacy signup markers
    if (t.includes('emailValidationCode') && t.includes('castleRequestToken')) {
      let m = t.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
      if (m) return m[1];
      const idx = t.indexOf('emailValidationCode');
      if (idx >= 0) {
        const slice = t.slice(Math.max(0, idx - 600), idx + 900);
        m = slice.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
        if (m) return m[1];
        m = slice.match(/[a-f0-9]{40,64}/);
        if (m) return m[0];
      }
    }
    return '';
  }
  const scripts = Array.from(document.querySelectorAll('script[src*="/_next/static/chunks/"]'));
  const urls = scripts.map(s => s.src).filter(Boolean).slice(0, 100);
  // Pass 1: only chunks that mention createUserAndSession
  for (const url of urls) {
    try {
      const t = await fetch(url, {credentials:'same-origin'}).then(r => r.text());
      if (!t || !t.includes('createUserAndSession')) continue;
      const hit = pickFromText(t);
      if (hit) return hit;
    } catch (e) {}
  }
  // Pass 2: legacy emailValidationCode + castleRequestToken chunks
  for (const url of urls) {
    try {
      const t = await fetch(url, {credentials:'same-origin'}).then(r => r.text());
      if (!t) continue;
      if (!(t.includes('emailValidationCode') && t.includes('castleRequestToken'))) continue;
      const hit = pickFromText(t);
      if (hit) return hit;
    } catch (e) {}
  }
  return '';
})();
"""
            )
            # DrissionPage may return promise result already resolved
            if action and not str(action).startswith("<"):
                action = _reject_dead_action(str(action))
                if action:
                    self._lg(
                        f"[*] scrape next-action from chunks "
                        f"len={len(action)} value={action[:20]}..."
                    )
                    return action
        except Exception as e:
            self._lg(f"[Debug] scrape next-action chunks: {e}")
        # Fallback to network-hook captured action only after SignUp-marked scrape fails.
        if hook_actions:
            self._lg(
                f"[*] scrape next-action fallback network hook "
                f"value={str(hook_actions[0])[:20]}..."
            )
            alive = _reject_dead_action(str(hook_actions[0]))
            if alive:
                return alive
        return ""

    def _extract_castle_pk(self) -> str:
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            pk = page.run_js(
                r"""
const html = document.documentElement.innerHTML || '';
const patterns = [
  /"castlePk":"([^"]+)"/,
  /castlePk\\":\\"([^\\"]+)/,
  /castlePk["']?\s*[:=]\s*["'](pk_[^"']+)/,
];
for (const p of patterns) {
  const m = html.match(p);
  if (m && m[1]) return m[1];
}
return '';
"""
            )
            if pk and str(pk).startswith("pk_"):
                return str(pk)
        except Exception as e:
            self._lg(f"[Debug] castle pk: {e}")
        return "pk_p8GGWvD3TmFJZRsX3BQcqAv9aFVispNz"

    def _ensure_castle_sdk(self, pk: str) -> bool:
        """Inject @castleio/castle-js and start createRequestToken (no top-level await)."""
        from grok_register_ttk import _get_page

        page = _get_page()
        # already minting / done?
        try:
            st = page.run_js(
                "return {s: window.__hybrid_castle_status||'', l:(window.__hybrid_castle||'').length};"
            )
            if isinstance(st, dict) and (st.get("s") == "done" or int(st.get("l") or 0) > 40):
                return True
        except Exception:
            pass

        cdn = "https://cdn.jsdelivr.net/npm/@castleio/castle-js@2.1.8/dist/castle.min.js"
        try:
            page.run_js(
                f"""
window.__hybrid_castle = window.__hybrid_castle || '';
window.__hybrid_castle_status = 'loading-sdk';
window.__hybrid_castle_err = '';
(function(){{
  function mint(C) {{
    try {{
      var api = C;
      if (api && api.default) api = api.default;
      if (api && typeof api.configure === 'function') {{
        try {{ api.configure({{pk: {pk!r}}}); }} catch (e1) {{}}
      }}
      var fn = null;
      if (api && typeof api.createRequestToken === 'function') fn = api.createRequestToken.bind(api);
      if (!fn && typeof C === 'function') {{
        try {{
          var inst = C({{pk: {pk!r}}});
          if (inst && typeof inst.createRequestToken === 'function') fn = inst.createRequestToken.bind(inst);
        }} catch (e2) {{}}
      }}
      if (!fn) {{
        window.__hybrid_castle_status = 'no-method';
        window.__hybrid_castle_methods = api ? Object.keys(api) : [];
        return;
      }}
      window.__hybrid_castle_status = 'minting';
      Promise.resolve(fn()).then(function(t){{
        window.__hybrid_castle = String(t || '');
        window.__hybrid_castle_status = (window.__hybrid_castle.length > 20) ? 'done' : 'empty';
      }}).catch(function(e){{
        window.__hybrid_castle_err = String(e);
        window.__hybrid_castle_status = 'error';
      }});
    }} catch (e) {{
      window.__hybrid_castle_err = String(e);
      window.__hybrid_castle_status = 'exception';
    }}
  }}
  var existing = window.Castle || window.castle || window['@castleio/castle-js'] || null;
  if (existing) {{ mint(existing); return; }}
  if (window.__hybrid_castle_script) {{ return; }}
  window.__hybrid_castle_script = true;
  var s = document.createElement('script');
  s.src = {cdn!r};
  s.onload = function(){{
    var C = window.Castle || window.castle || window['@castleio/castle-js'] || null;
    mint(C);
  }};
  s.onerror = function(){{
    window.__hybrid_castle_err = 'sdk script load failed';
    window.__hybrid_castle_status = 'sdk-fail';
  }};
  document.head.appendChild(s);
}})();
true;
"""
            )
            return True
        except Exception as e:
            self._lg(f"[Debug] ensure castle sdk: {e}")
            return False

    def _get_castle_token_injected_impl(self, timeout: int = 45) -> str:
        """Mint Castle request token via injected SDK (page has no window.Castle)."""
        from grok_register_ttk import _get_page

        page = _get_page()
        pk = self._extract_castle_pk()
        self._lg(f"[*] castle pk={pk[:16]}...")
        self._ensure_castle_sdk(pk)
        deadline = time.time() + timeout
        last_status = ""
        while time.time() < deadline:
            try:
                data = page.run_js(
                    """
let castle = '';
try {
  // prefer native-captured long token if present
  if (window.__hybrid_castles && window.__hybrid_castles.length) {
    for (const t of window.__hybrid_castles) {
      if (String(t||'').length > String(castle||'').length) castle = String(t);
    }
  }
  if ((!castle || castle.length < 1000) && window.__hybrid_castle) castle = String(window.__hybrid_castle);
} catch (e) {}
const el = document.querySelector('input[name*="castle" i], textarea[name*="castle" i]');
if (!castle && el) castle = String(el.value || '').trim();
return {
  castle: castle || '',
  status: String(window.__hybrid_castle_status || ''),
  err: String(window.__hybrid_castle_err || ''),
  methods: window.__hybrid_castle_methods || []
};
"""
                )
                if isinstance(data, dict):
                    castle = str(data.get("castle") or "")
                    last_status = f"{data.get('status')}|{data.get('err')}|{data.get('methods')}"
                    # accept short injected tokens only as last resort
                    if len(castle) >= 40:
                        self._lg(f"[*] castle token len={len(castle)}")
                        return castle
                    st = str(data.get("status") or "")
                    if st in ("no-method", "sdk-fail", "error", "exception", "empty"):
                        page.run_js(
                            "window.__hybrid_castle_script=false; window.__hybrid_castle_status=''; true;"
                        )
                        self._ensure_castle_sdk(pk)
            except Exception:
                pass
            time.sleep(0.5)
        self._lg(f"[!] castle token timeout last={last_status}")
        return ""

    def get_castle_token(self, timeout: int = 45) -> str:
        """Prefer native-captured IBYIll token; fallback to injected SDK."""
        c = self.read_captured_castle()
        if c:
            self._lg(f"[*] castle from capture len={len(c)}")
            return c
        return self._get_castle_token_injected_impl(timeout=timeout)

    def _extract_turnstile_sitekey(self) -> str:
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            sk = page.run_js(
                r"""
const html = document.documentElement.innerHTML || '';
const pats = [
  /"sitekey":"(0x4[^"]+)"/,
  /sitekey\\":\\"(0x4[^\\"]+)/,
  /sitekey["']?\s*[:=]\s*["'](0x4[^"']+)/i,
];
for (const p of pats) {
  const m = html.match(p);
  if (m && m[1]) return m[1];
}
const el = document.querySelector('[data-sitekey], .cf-turnstile');
if (el) {
  const v = el.getAttribute('data-sitekey') || '';
  if (v) return v;
}
return '';
"""
            )
            if sk and str(sk).startswith("0x"):
                return str(sk)
        except Exception as e:
            self._lg(f"[Debug] sitekey: {e}")
        return "0x4AAAAAAAhr9JGVDZbrZOo0"

    def inject_turnstile_widget(self, sitekey: str = "") -> bool:
        """Mount a standalone Turnstile widget (turnstilePatch can auto-solve)."""
        from grok_register_ttk import _get_page

        page = _get_page()
        sk = (sitekey or self._extract_turnstile_sitekey()).strip()
        self._lg(f"[*] turnstile sitekey={sk[:20]}...")
        try:
            page.run_js(
                f"""
window.__hybrid_turnstile = '';
window.__hybrid_turnstile_status = 'init';
(function(){{
  var sitekey = {sk!r};
  function renderWhenReady() {{
    if (!window.turnstile || typeof turnstile.render !== 'function') {{
      window.__hybrid_turnstile_status = 'waiting-api';
      return false;
    }}
    var host = document.getElementById('hybrid-turnstile-host');
    if (!host) {{
      host = document.createElement('div');
      host.id = 'hybrid-turnstile-host';
      host.style.cssText = 'position:fixed;right:8px;bottom:8px;z-index:2147483647;background:#111;padding:8px;';
      document.body.appendChild(host);
    }} else {{
      host.innerHTML = '';
    }}
    try {{
      turnstile.render(host, {{
        sitekey: sitekey,
        theme: 'dark',
        size: 'flexible',
        callback: function(token) {{
          window.__hybrid_turnstile = String(token || '');
          window.__hybrid_turnstile_status = 'done';
        }},
        'error-callback': function() {{
          window.__hybrid_turnstile_status = 'error';
        }},
        'expired-callback': function() {{
          window.__hybrid_turnstile_status = 'expired';
        }}
      }});
      window.__hybrid_turnstile_status = 'rendered';
      return true;
    }} catch (e) {{
      window.__hybrid_turnstile_status = 'render-fail';
      window.__hybrid_turnstile_err = String(e);
      return false;
    }}
  }}
  if (renderWhenReady()) return;
  if (!document.getElementById('hybrid-cf-script')) {{
    var s = document.createElement('script');
    s.id = 'hybrid-cf-script';
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true;
    s.onload = function(){{ renderWhenReady(); }};
    s.onerror = function(){{ window.__hybrid_turnstile_status = 'script-fail'; }};
    document.head.appendChild(s);
  }}
  var n = 0;
  var t = setInterval(function(){{
    n += 1;
    if (renderWhenReady() || n > 40) clearInterval(t);
  }}, 250);
}})();
true;
"""
            )
            return True
        except Exception as e:
            self._lg(f"[Debug] inject turnstile: {e}")
            return False

    def get_turnstile_token(self, timeout: int = 90, inject: bool = True, cancel_callback=None) -> str:
        from grok_register_ttk import _get_page, getTurnstileToken

        page = _get_page()
        if inject:
            self.inject_turnstile_widget()

        # try official helper first (uses turnstilePatch click path)
        try:
            tok = getTurnstileToken(log_callback=self.log, cancel_callback=cancel_callback)
            if tok and len(str(tok)) >= 80:
                return str(tok)
        except TypeError:
            # older signature without cancel_callback
            try:
                tok = getTurnstileToken(log_callback=self.log)
                if tok and len(str(tok)) >= 80:
                    return str(tok)
            except Exception as e:
                self._lg(f"[Debug] getTurnstileToken: {e}")
        except Exception as e:
            self._lg(f"[Debug] getTurnstileToken: {e}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                tok = page.run_js(
                    """
let tok = '';
try { if (window.__hybrid_turnstile) tok = String(window.__hybrid_turnstile); } catch (e) {}
if (!tok) {
  const byInput = String((document.querySelector('input[name="cf-turnstile-response"]') || {}).value || '').trim();
  if (byInput) tok = byInput;
}
try {
  if (!tok && window.turnstile && typeof turnstile.getResponse === 'function') {
    tok = String(turnstile.getResponse() || '').trim();
  }
} catch (e) {}
return {
  tok: tok || '',
  status: String(window.__hybrid_turnstile_status || ''),
  err: String(window.__hybrid_turnstile_err || '')
};
"""
                )
                if isinstance(tok, dict):
                    status = tok.get("status")
                    val = str(tok.get("tok") or "").strip()
                    if len(val) >= 80:
                        self._lg(f"[*] turnstile len={len(val)} status={status}")
                        return val
                    if status in ("script-fail", "render-fail", "error"):
                        self.inject_turnstile_widget()
                else:
                    val = str(tok or "").strip()
                    if len(val) >= 80:
                        self._lg(f"[*] turnstile len={len(val)}")
                        return val
            except Exception:
                pass
            if cancel_callback and cancel_callback():
                self._lg("[!] turnstile cancelled by stop")
                return ""
            time.sleep(1)
        self._lg("[!] turnstile timeout")
        return ""

    def _set_input_and_submit(self, value: str, kind: str) -> str:
        """Fill visible email/code input and click continue. kind=email|code"""
        from grok_register_ttk import _get_page

        page = _get_page()
        return str(
            page.run_js(
                """
const value = String(arguments[0] || '');
const kind = String(arguments[1] || 'email');
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function setInputValue(input, v) {
  input.focus(); input.click();
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (setter) setter.call(input, v); else input.value = v;
  input.dispatchEvent(new Event('focus', {bubbles:true}));
  input.dispatchEvent(new InputEvent('beforeinput', {bubbles:true, data:v, inputType:'insertText'}));
  input.dispatchEvent(new InputEvent('input', {bubbles:true, data:v, inputType:'insertText'}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  input.dispatchEvent(new Event('blur', {bubbles:true}));
}
let input = null;
if (kind === 'email') {
  input = Array.from(document.querySelectorAll('input, textarea')).find((node) => {
    if (!isVisible(node) || node.disabled) return false;
    const type = String(node.getAttribute('type') || '').toLowerCase();
    if (['password','hidden','checkbox','radio','submit','button'].includes(type)) return false;
    const meta = [node.getAttribute('data-testid'), node.name, node.id, node.placeholder, type].join(' ').toLowerCase();
    return meta.includes('email') || meta.includes('mail') || type === 'email';
  }) || null;
} else {
  input = Array.from(document.querySelectorAll(
    'input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[inputmode="text"]'
  )).find((node) => isVisible(node) && !node.disabled && Number(node.maxLength || 6) > 1) || null;
  if (!input) {
    const boxes = Array.from(document.querySelectorAll('input')).filter((node) => {
      if (!isVisible(node) || node.disabled) return false;
      return Number(node.maxLength || 0) === 1;
    });
    if (boxes.length >= value.length) {
      for (let i = 0; i < value.length; i++) {
        setInputValue(boxes[i], value[i] || '');
      }
      input = boxes[0];
    }
  }
}
if (!input && kind === 'email') return 'no-email-input';
if (!input && kind === 'code') return 'no-code-input';
if (kind === 'email' || Number(input.maxLength || 6) > 1) setInputValue(input, value);
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"]'))
  .filter((node) => isVisible(node) && !node.disabled);
const submit = buttons.find((node) => {
  const t = (node.innerText || node.textContent || '').replace(/\\s+/g, '').toLowerCase();
  return t.includes('注册') || t.includes('继续') || t.includes('下一步') || t.includes('完成')
    || t.includes('continue') || t.includes('next') || t.includes('confirm') || t.includes('sign');
}) || buttons.find((n) => String(n.getAttribute('type')||'').toLowerCase()==='submit') || buttons[0];
if (submit) { submit.click(); return 'submitted'; }
return 'filled-no-button';
                """,
                value,
                kind,
            )
            or ""
        )

    def prepare_profile_step_for_turnstile(
        self, email: str, code: str, timeout: int = 90
    ) -> bool:
        """Drive UI email→code→profile so Turnstile widget mounts.

        Protocol already verified the code; UI path still needed for widget.
        """
        from grok_register_ttk import _get_page

        page = _get_page()
        clean = str(code or "").replace("-", "").strip()
        try:
            self.open_signup()
        except Exception as e:
            self._lg(f"[Debug] reopen signup: {e}")

        deadline = time.time() + timeout
        email_done = code_done = False
        while time.time() < deadline:
            state = page.run_js(
                """
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const pw = Array.from(document.querySelectorAll('input[type="password"], input[name="password"]')).some(isVisible);
const cf = !!document.querySelector('input[name="cf-turnstile-response"], div.cf-turnstile, iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]');
const email = Array.from(document.querySelectorAll('input[type="email"], input[name="email"], input[data-testid="email"]')).some(isVisible);
const code = Array.from(document.querySelectorAll('input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"]')).some(isVisible)
  || Array.from(document.querySelectorAll('input')).filter(n => isVisible(n) && Number(n.maxLength||0)===1).length >= 4;
const given = Array.from(document.querySelectorAll('input[name="givenName"], input[name="familyName"], input[autocomplete="given-name"]')).some(isVisible);
return {pw:!!pw, cf:!!cf, email:!!email, code:!!code, given:!!given, url: location.href};
"""
            )
            if isinstance(state, dict) and (state.get("pw") or state.get("cf") or state.get("given")):
                self._lg(f"[*] profile/turnstile ready state={state}")
                return True

            if isinstance(state, dict) and state.get("email") and not email_done:
                r = self._set_input_and_submit(email, "email")
                self._lg(f"[*] UI email submit: {r}")
                email_done = True
                time.sleep(1.5)
                continue

            if isinstance(state, dict) and state.get("code") and not code_done:
                r = self._set_input_and_submit(clean, "code")
                self._lg(f"[*] UI code submit: {r}")
                code_done = True
                time.sleep(2.0)
                continue

            # maybe still on method chooser
            if isinstance(state, dict) and not state.get("email") and not state.get("code"):
                try:
                    from grok_register_ttk import click_email_signup_button

                    click_email_signup_button(timeout=5, log_callback=self.log)
                except Exception:
                    pass
            time.sleep(0.8)
        self._lg("[!] profile step timeout")
        return False



    def fetch_signup_server_action(
        self,
        *,
        email: str,
        code: str,
        given_name: str,
        family_name: str,
        password: str,
        turnstile_token: str,
        castle_token: str,
        next_action: str,
        conversion_id: str = "",
        router_state_tree: str = "",
        timeout: float = 25,
    ) -> dict:
        """POST SignUp server action from inside the browser (same-origin + CF cookies).

        curl_cffi may hang/timeout on accounts.x.ai via SOCKS while Chromium already works.
        """
        import json as _json
        import re as _re
        import uuid as _uuid

        from grok_register_ttk import _get_page

        page = _get_page()
        act = (next_action or "").strip()
        if not act:
            return {"status": 0, "text": "next-action missing", "sso": "", "cookies": {}}
        clean_code = str(code or "").replace("-", "").strip()
        cid = conversion_id or str(_uuid.uuid4())
        tree = (router_state_tree or "").strip() or (
            "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C0%5D%7D%2Cnull%2Cnull%2C0%5D%7D%2Cnull%2Cnull%2C0%5D%7D%2Cnull%2Cnull%2C0%5D%7D%2Cnull%2Cnull%2C16%5D"
        )
        timeout_ms = int(max(5, float(timeout or 25)) * 1000)
        # Bind args via JS closure. DrissionPage does NOT inject *args into
        # async IIFE as `arguments` when script is `return (async function(){...})();`.
        # Passing empty next-action produced hard 404 "Server action not found".
        self._lg(
            f"[*] browser-fetch SignUp next-action={act[:20]}... "
            f"email={email} code_len={len(clean_code)} castle_len={len(castle_token or '')} "
            f"turnstile_len={len(turnstile_token or '')} timeout_ms={timeout_ms}"
        )
        email_js = _json.dumps(str(email or ""))
        code_js = _json.dumps(str(clean_code or ""))
        given_js = _json.dumps(str(given_name or ""))
        family_js = _json.dumps(str(family_name or ""))
        password_js = _json.dumps(str(password or ""))
        turnstile_js = _json.dumps(str(turnstile_token or ""))
        castle_js = _json.dumps(str(castle_token or ""))
        action_js = _json.dumps(str(act or ""))
        conv_js = _json.dumps(str(cid or ""))
        tree_js = _json.dumps(str(tree or ""))
        script = f"""
return (async function(){{
  const email = {email_js};
  const code = {code_js};
  const givenName = {given_js};
  const familyName = {family_js};
  const password = {password_js};
  const turnstile = {turnstile_js};
  const castle = {castle_js};
  const nextAction = {action_js};
  const conversionId = {conv_js};
  const tree = {tree_js};
  const timeoutMs = {int(timeout_ms)};
  if (!nextAction) {{
    return {{status:0, ok:false, text:'next-action empty in browser-fetch', cookie:String(document.cookie||''), url:String(location.href||''), setCookie:''}};
  }}
  const payload = [{{
    emailValidationCode: code,
    createUserAndSessionRequest: {{
      email: email,
      givenName: givenName,
      familyName: familyName,
      clearTextPassword: password,
      tosAcceptedVersion: 1
    }},
    turnstileToken: turnstile,
    conversionId: conversionId,
    castleRequestToken: castle
  }}];
  const body = JSON.stringify(payload);
  const headers = {{
    'content-type': 'text/plain;charset=UTF-8',
    'accept': 'text/x-component',
    'next-action': nextAction,
    'next-router-state-tree': tree
  }};
  const ctrl = new AbortController();
  const timer = setTimeout(function(){{ try {{ ctrl.abort(); }} catch(e){{}} }}, timeoutMs);
  try {{
    const r = await fetch(location.href.split('#')[0] || 'https://accounts.x.ai/sign-up?redirect=grok-com', {{
      method: 'POST',
      credentials: 'include',
      headers: headers,
      body: body,
      signal: ctrl.signal
    }});
    clearTimeout(timer);
    let text = '';
    try {{ text = await r.text(); }} catch (e) {{ text = String(e); }}
    let setCookie = '';
    try {{
      if (typeof r.headers.getSetCookie === 'function') {{
        setCookie = (r.headers.getSetCookie() || []).join('\\n');
      }} else {{
        setCookie = r.headers.get('set-cookie') || '';
      }}
    }} catch (e) {{ setCookie = ''; }}
    return {{
      status: r.status,
      ok: !!r.ok,
      text: String(text || '').slice(0, 8000),
      cookie: String(document.cookie || ''),
      setCookie: String(setCookie || ''),
      url: String(location.href || ''),
      nextAction: nextAction
    }};
  }} catch (e) {{
    clearTimeout(timer);
    return {{
      status: 0,
      ok: false,
      text: String(e && (e.message || e) || e),
      cookie: String(document.cookie || ''),
      setCookie: '',
      url: String(location.href || ''),
      nextAction: nextAction
    }};
  }}
}})();
"""
        try:
            raw = page.run_js(script)
        except Exception as e:
            self._lg(f"[!] browser-fetch SignUp exception: {e}")
            return {
                "status": 0,
                "text": str(e),
                "sso": "",
                "cookies": {},
                "error_hints": ["browser_fetch_exception"],
            }

        if isinstance(raw, str):
            try:
                raw = _json.loads(raw)
            except Exception:
                raw = {"status": 0, "text": raw, "cookie": ""}
        if not isinstance(raw, dict):
            raw = {"status": 0, "text": str(raw), "cookie": ""}

        text = str(raw.get("text") or "")
        cookie_str = str(raw.get("cookie") or "")
        set_cookie_str = str(raw.get("setCookie") or raw.get("set_cookie") or "")
        status = raw.get("status")
        try:
            status = int(status)
        except Exception:
            status = 0

        # Guard: if JS still got empty next-action, surface clearly.
        try:
            used_act = str(raw.get("nextAction") or "").strip()
            if used_act:
                self._lg(f"[*] browser-fetch used next-action={used_act[:20]}... status={status}")
            else:
                self._lg(f"[!] browser-fetch JS reports empty nextAction; status={status}")
        except Exception:
            pass

        sso = ""
        for blob in (cookie_str, set_cookie_str, text):
            if sso:
                break
            m = _re.search(r"(?:^|\n|;\s*)sso=([^;\s]+)", blob or "")
            if m and len(m.group(1)) > 20:
                sso = m.group(1)
                continue
            m = _re.search(r"(?:^|\n|;\s*)sso-rw=([^;\s]+)", blob or "")
            if m and len(m.group(1)) > 20:
                sso = m.group(1)
                continue
            m = _re.search(r"\bsso[\"']?\s*[:=]\s*[\"']([^\"']{20,})[\"']", blob or "")
            if m and len(m.group(1)) > 20:
                sso = m.group(1)

        jar = {}
        try:
            jar = self.export_cookies() or {}
            if not sso:
                sso = jar.get("sso") or jar.get("sso-rw") or ""
        except Exception:
            pass

        low = text.lower()
        hints = []
        for key in (
            "error",
            "invalid",
            "already",
            "exists",
            "castle",
            "turnstile",
            "forbidden",
            "server action not found",
            "$sreact.fragment",
            "abort",
            "timeout",
        ):
            if key.lower() in low:
                hints.append(key)

        self._lg(
            f"[*] browser-fetch SignUp done status={status} sso_len={len(sso or '')} "
            f"text_len={len(text)} url={raw.get('url')!r} hints={hints}"
        )
        return {
            "status": status,
            "text": text[:8000],
            "text_len": len(text),
            "cookies": jar,
            "sso": sso or "",
            "redirect_url": "",
            "set_cookie_blob": cookie_str[:2000],
            "error_hints": hints,
            "castle_len": len(castle_token or ""),
            "turnstile_len": len(turnstile_token or ""),
            "tos_accepted_version": 1,
            "next_action": act,
            "path": "browser-fetch",
        }

    def submit_profile_and_wait_sso(
        self,
        *,
        given_name: str,
        family_name: str,
        password: str,
        turnstile_token: str = "",
        email: str = "",
        code: str = "",
        timeout: int = 90,
        cancel_callback=None,
    ) -> str:
        """Advance signup UI (email/code/profile) and wait for sso cookie.

        When protocol/browser-fetch next-action fails, the page may still be on
        email or verification step. Advance those steps first, then fill profile.
        """
        from grok_register_ttk import _get_page

        page = _get_page()
        stop = cancel_callback or (lambda: False)
        self.install_network_hook()

        email_val = (email or "").strip()
        code_val = (code or "").strip()
        import re as _re

        code_digits = "".join(_re.findall(r"\d+", code_val))
        if len(code_digits) >= 4:
            code_val = code_digits[-6:] if len(code_digits) > 6 else code_digits

        # Ensure turnstile token is in the page if we already solved it.
        tok = (turnstile_token or "").strip()
        if tok:
            try:
                page.run_js(
                    """
const token = String(arguments[0] || '').trim();
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!cfInput || !token) return 0;
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) nativeSetter.call(cfInput, token);
else cfInput.value = token;
cfInput.dispatchEvent(new Event('input', { bubbles: true }));
cfInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(cfInput.value || '').trim().length;
""",
                    tok,
                )
                self._lg(f"[*] UI fallback inject turnstile len={len(tok)}")
            except Exception as e:
                self._lg(f"[Debug] UI fallback inject turnstile: {e}")

        deadline = time.time() + max(30, int(timeout or 90))
        email_done = False
        code_done = False
        filled = False
        submitted = False
        last_state_sig = ""
        while time.time() < deadline:
            if stop():
                self._lg("[*] UI fallback cancelled")
                return ""
            try:
                state = page.run_js(
                    """
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="email"], input[data-testid="email"]');
const codeInput = pick('input[name="code"], input[name="emailValidationCode"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[data-testid="code"]');
const given = Array.from(document.querySelectorAll('input[name="givenName"], input[data-testid="givenName"], input[autocomplete="given-name"]')).some(isVisible);
const family = Array.from(document.querySelectorAll('input[name="familyName"], input[data-testid="familyName"], input[autocomplete="family-name"]')).some(isVisible);
const pw = Array.from(document.querySelectorAll('input[type="password"], input[name="password"]')).some(isVisible);
const cf = document.querySelector('input[name="cf-turnstile-response"]');
const cfLen = cf ? String(cf.value||'').trim().length : 0;
return {
  email: !!emailInput,
  code: !!codeInput,
  given: !!given,
  family: !!family,
  pw: !!pw,
  cfLen: cfLen,
  url: location.href,
  hasProfile: !!(given && family && pw)
};
"""
                )
            except Exception as e:
                self._lg(f"[Debug] UI fallback state: {e}")
                time.sleep(0.6)
                continue

            if not isinstance(state, dict):
                time.sleep(0.5)
                continue

            sig = (
                f"e={state.get('email')} c={state.get('code')} "
                f"g={state.get('given')} f={state.get('family')} "
                f"p={state.get('pw')} cf={state.get('cfLen')} url={state.get('url')}"
            )
            if sig != last_state_sig:
                self._lg(f"[*] UI fallback state={state}")
                last_state_sig = sig

            # already left signup? check cookies early
            jar = self.export_cookies() or {}
            sso = jar.get("sso") or jar.get("sso-rw") or ""
            if sso and len(str(sso)) > 20:
                self._lg(f"[*] UI fallback sso from cookies early len={len(sso)}")
                return str(sso)

            has_profile = bool(
                state.get("hasProfile")
                or (state.get("given") and state.get("family") and state.get("pw"))
            )

            # Step 1: still on email page.
            if email_val and state.get("email") and not has_profile and not email_done:
                try:
                    step_r = page.run_js(
                        """
const email = String(arguments[0] || '').trim();
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
function setVal(input, value) {
  if (!input) return false;
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.blur();
  return String(input.value||'').trim() === String(value||'').trim();
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label')]
    .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
const input = pick('input[type="email"], input[name="email"], input[autocomplete="email"], input[data-testid="email"]');
if (!input) return 'no-email-input';
if (!setVal(input, email)) return 'email-fill-failed';
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]'))
  .filter(n => isVisible(n) && !n.disabled && n.getAttribute('aria-disabled') !== 'true');
const btn = buttons.find(n => {
  const t = buttonText(n).replace(/\\s+/g, '').toLowerCase();
  return t.includes('继续') || t.includes('下一步') || t.includes('continue') || t.includes('next') || t.includes('发送') || t.includes('send');
}) || buttons.find(n => String(n.getAttribute('type')||'').toLowerCase() === 'submit') || buttons[0] || null;
if (!btn) return 'email-filled-no-btn';
btn.focus();
btn.click();
return 'email-submitted:' + buttonText(btn);
""",
                        email_val,
                    )
                    self._lg(f"[*] UI fallback email step={step_r}")
                    if str(step_r).startswith("email-submitted") or str(step_r) == "email-filled-no-btn":
                        email_done = True
                        time.sleep(1.2)
                        continue
                except Exception as e:
                    self._lg(f"[Debug] UI fallback email step: {e}")

            # Step 2: still on verification code page.
            if code_val and state.get("code") and not has_profile and not code_done:
                try:
                    step_r = page.run_js(
                        """
const code = String(arguments[0] || '').trim();
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
function setVal(input, value) {
  if (!input) return false;
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.blur();
  return String(input.value||'').replace(/\\s+/g,'') === String(value||'').replace(/\\s+/g,'');
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label')]
    .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
const input = pick('input[name="code"], input[name="emailValidationCode"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[data-testid="code"], input[type="text"], input[type="tel"]');
if (!input) return 'no-code-input';
if (!setVal(input, code)) return 'code-fill-failed';
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]'))
  .filter(n => isVisible(n) && !n.disabled && n.getAttribute('aria-disabled') !== 'true');
const btn = buttons.find(n => {
  const t = buttonText(n).replace(/\\s+/g, '').toLowerCase();
  return t.includes('继续') || t.includes('下一步') || t.includes('验证') || t.includes('confirm') || t.includes('continue') || t.includes('next') || t.includes('verify');
}) || buttons.find(n => String(n.getAttribute('type')||'').toLowerCase() === 'submit') || buttons[0] || null;
if (!btn) return 'code-filled-no-btn';
btn.focus();
btn.click();
return 'code-submitted:' + buttonText(btn);
""",
                        code_val,
                    )
                    self._lg(f"[*] UI fallback code step={step_r}")
                    if str(step_r).startswith("code-submitted") or str(step_r) == "code-filled-no-btn":
                        code_done = True
                        time.sleep(1.5)
                        continue
                except Exception as e:
                    self._lg(f"[Debug] UI fallback code step: {e}")

            if state.get("given") and state.get("family") and state.get("pw") and not filled:
                try:
                    fill_r = page.run_js(
                        """
const givenName = arguments[0];
const familyName = arguments[1];
const password = arguments[2];
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
function setVal(input, value) {
  if (!input) return false;
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.blur();
  return String(input.value||'').trim() === String(value||'').trim();
}
const g = pick('input[name="givenName"], input[data-testid="givenName"], input[autocomplete="given-name"]');
const f = pick('input[name="familyName"], input[data-testid="familyName"], input[autocomplete="family-name"]');
const p = pick('input[type="password"], input[name="password"], input[autocomplete="new-password"]');
if (!g || !f || !p) return 'not-ready';
const ok = setVal(g, givenName) && setVal(f, familyName) && setVal(p, password);
return ok ? 'filled' : 'fill-failed';
""",
                        given_name,
                        family_name,
                        password,
                    )
                    self._lg(f"[*] UI fallback fill={fill_r} name={given_name} {family_name}")
                    if fill_r == "filled":
                        filled = True
                except Exception as e:
                    self._lg(f"[Debug] UI fallback fill: {e}")

            if filled and not submitted:
                # require turnstile if present
                cf_len = int(state.get("cfLen") or 0)
                if cf_len < 80 and tok:
                    try:
                        page.run_js(
                            """
const token = String(arguments[0] || '').trim();
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!cfInput || !token) return 0;
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) nativeSetter.call(cfInput, token);
else cfInput.value = token;
cfInput.dispatchEvent(new Event('input', { bubbles: true }));
cfInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(cfInput.value || '').trim().length;
""",
                            tok,
                        )
                    except Exception:
                        pass
                try:
                    click_r = page.run_js(
                        r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]'))
  .filter(n => isVisible(n) && !n.disabled && n.getAttribute('aria-disabled') !== 'true');
const submitBtn = buttons.find(n => {
  const t = buttonText(n).replace(/\s+/g, '').toLowerCase();
  return t.includes('完成注册') || t.includes('创建账户') || t.includes('signup') || t.includes('createaccount') || t.includes('sign up') || t.includes('register');
}) || buttons.find(n => String(n.getAttribute('type')||'').toLowerCase() === 'submit') || null;
if (!submitBtn) {
  return 'no-submit:' + buttons.map(buttonText).filter(Boolean).slice(0, 8).join(' | ');
}
submitBtn.focus();
submitBtn.click();
return 'submitted:' + buttonText(submitBtn);
"""
                    )
                    self._lg(f"[*] UI fallback click={click_r}")
                    if str(click_r).startswith("submitted"):
                        submitted = True
                except Exception as e:
                    self._lg(f"[Debug] UI fallback click: {e}")

            # poll sso after submit or always
            jar = self.export_cookies() or {}
            sso = jar.get("sso") or jar.get("sso-rw") or ""
            if sso and len(str(sso)) > 20:
                self._lg(f"[*] UI fallback sso ok len={len(sso)}")
                return str(sso)

            # document.cookie fallback
            try:
                doc = page.run_js(
                    "return document.cookie || '';"
                ) or ""
                m = _re.search(r"(?:^|;\s*)sso=([^;]+)", str(doc))
                if m and len(m.group(1)) > 20:
                    self._lg(f"[*] UI fallback sso from document.cookie len={len(m.group(1))}")
                    return m.group(1)
            except Exception:
                pass

            time.sleep(0.8)

        self._lg("[!] UI fallback timeout without sso")
        return ""



def harvest_tokens(
    *,
    stay_on_profile: bool = True,
    timeout: int = 90,
    log: Optional[Callable[[str], None]] = None,
) -> HarvestedTokens:
    """Backward-compatible one-shot harvest."""
    out = HarvestedTokens()
    with BrowserTokenSession(log=log) as sess:
        sess.open_signup()
        out.castle = sess.get_castle_token(timeout=min(45, timeout))
        out.turnstile = sess.get_turnstile_token(timeout=min(30, timeout)) if stay_on_profile else ""
        out.cookies = sess.export_cookies()
        out.next_action = sess.scrape_next_action()
        out.page_url = "https://accounts.x.ai/sign-up"
    return out


if __name__ == "__main__":
    t = harvest_tokens(log=print, timeout=60)
    print("turnstile_len", len(t.turnstile))
    print("castle_len", len(t.castle))
    print("cookies", list((t.cookies or {}).keys())[:10])
    print("next_action", t.next_action[:40] if t.next_action else "")
