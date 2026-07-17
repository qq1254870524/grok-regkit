"""Browser-only token harvest for Castle / Turnstile (hybrid mode)."""
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
        """Capture castleRequestToken from native React fetch/XHR bodies."""
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
  window.__hybrid_create_email_ok = false;
  window.__hybrid_create_email_status = 0;
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
    } catch (e) {}
  }
  const ofetch = window.fetch;
  window.fetch = async function(input, init) {
    let url = '';
    try {
      url = (typeof input === 'string') ? input : (input && input.url) || '';
      captureBody(init && init.body, url);
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
  const osend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; return oopen.apply(this, arguments); };
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
        while time.time() < deadline:
            st = self.create_email_status_via_browser()
            c = self.read_captured_castle()
            if st.get("sent"):
                self._lg(
                    f"[*] CreateEmail UI evidence sent=1 reason={st.get('reason')} "
                    f"status={st.get('status')} seen={st.get('seen')} net_hits={st.get('net_hits')} "
                    f"castle_len={st.get('castle_len') or (len(c) if c else 0)}"
                )
                if c:
                    self._lg(f"[*] native castle len={len(c)} head={c[:20]}")
                    return c
            elif c and (time.time() + 8) >= deadline:
                self._lg(
                    f"[!] CreateEmail not confirmed yet but castle present "
                    f"len={len(c)} reason={st.get('reason')} — keep waiting/retry click"
                )

            if (not st.get("sent")) and (time.time() - last_retry >= 4.0) and retries < 6:
                retries += 1
                last_retry = time.time()
                try:
                    self._hooked = False
                    self.install_network_hook()
                except Exception:
                    pass
                click_r = self.click_email_continue_for_create(email)
                self._lg(
                    f"[*] UI CreateEmail retry#{retries} click={click_r} email={email} "
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

    def scrape_next_action(self) -> str:
        """Find SignUp server-action hash from page HTML or Next.js chunk scripts."""
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            # Fast path: inline HTML / inline scripts
            action = page.run_js(
                r"""
const html = document.documentElement.innerHTML || '';
let m = html.match(/next-action["'\s:=]+([a-f0-9]{40,})/i);
if (m) return m[1];
for (const s of Array.from(document.scripts || [])) {
  const t = s.textContent || '';
  if (t.includes('emailValidationCode') && t.includes('castleRequestToken')) {
    const m2 = t.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
    if (m2) return m2[1];
  }
  const idx = t.indexOf('createUserAndSession');
  if (idx >= 0) {
    const slice = t.slice(Math.max(0, idx - 400), idx + 500);
    const m3 = slice.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
    if (m3) return m3[1];
    const m4 = slice.match(/[a-f0-9]{40,64}/);
    if (m4) return m4[0];
  }
}
return '';
"""
            )
            if action:
                return str(action)
        except Exception as e:
            self._lg(f"[Debug] scrape next-action inline: {e}")

        # Slow path: fetch external chunks (hash lives in createServerReference chunk)
        try:
            action = page.run_js(
                r"""
return (async function(){
  const scripts = Array.from(document.querySelectorAll('script[src*="/_next/static/chunks/"]'));
  const urls = scripts.map(s => s.src).filter(Boolean).slice(0, 80);
  for (const url of urls) {
    try {
      const t = await fetch(url, {credentials:'same-origin'}).then(r => r.text());
      if (!t) continue;
      if (!(t.includes('emailValidationCode') && t.includes('castleRequestToken'))) continue;
      let m = t.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
      if (m) return m[1];
      const idx = t.indexOf('emailValidationCode');
      if (idx >= 0) {
        const slice = t.slice(Math.max(0, idx - 500), idx + 800);
        m = slice.match(/createServerReference\)?\(['\"]([a-f0-9]{40,})['\"]/);
        if (m) return m[1];
        m = slice.match(/[a-f0-9]{40,64}/);
        if (m) return m[0];
      }
    } catch (e) {}
  }
  return '';
})();
"""
            )
            # DrissionPage may return promise result already resolved
            if action and not str(action).startswith("<"):
                self._lg(f"[*] scrape next-action from chunks len={len(str(action))}")
                return str(action)
        except Exception as e:
            self._lg(f"[Debug] scrape next-action chunks: {e}")
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
        self._lg(
            f"[*] browser-fetch SignUp next-action={act[:20]}... "
            f"email={email} code_len={len(clean_code)} castle_len={len(castle_token or '')} "
            f"turnstile_len={len(turnstile_token or '')} timeout_ms={timeout_ms}"
        )
        try:
            raw = page.run_js(
                r"""
return (async function(){
  const email = String(arguments[0] || '');
  const code = String(arguments[1] || '');
  const givenName = String(arguments[2] || '');
  const familyName = String(arguments[3] || '');
  const password = String(arguments[4] || '');
  const turnstile = String(arguments[5] || '');
  const castle = String(arguments[6] || '');
  const nextAction = String(arguments[7] || '');
  const conversionId = String(arguments[8] || '');
  const tree = String(arguments[9] || '');
  const timeoutMs = Number(arguments[10] || 25000);
  const payload = [{
    emailValidationCode: code,
    createUserAndSessionRequest: {
      email: email,
      givenName: givenName,
      familyName: familyName,
      clearTextPassword: password,
      tosAcceptedVersion: 1
    },
    turnstileToken: turnstile,
    conversionId: conversionId,
    castleRequestToken: castle
  }];
  const body = JSON.stringify(payload);
  const headers = {
    'content-type': 'text/plain;charset=UTF-8',
    'accept': 'text/x-component',
    'next-action': nextAction,
    'next-router-state-tree': tree
  };
  const ctrl = new AbortController();
  const timer = setTimeout(function(){ try { ctrl.abort(); } catch(e){} }, timeoutMs);
  try {
    const r = await fetch('https://accounts.x.ai/sign-up?redirect=grok-com', {
      method: 'POST',
      credentials: 'include',
      headers: headers,
      body: body,
      signal: ctrl.signal
    });
    clearTimeout(timer);
    let text = '';
    try { text = await r.text(); } catch (e) { text = String(e); }
    return {
      status: r.status,
      ok: !!r.ok,
      text: String(text || '').slice(0, 8000),
      cookie: String(document.cookie || ''),
      url: String(location.href || '')
    };
  } catch (e) {
    clearTimeout(timer);
    return {
      status: 0,
      ok: false,
      text: String(e && (e.message || e) || e),
      cookie: String(document.cookie || ''),
      url: String(location.href || '')
    };
  }
})();
""",
                email,
                clean_code,
                given_name,
                family_name,
                password,
                turnstile_token or "",
                castle_token or "",
                act,
                cid,
                tree,
                timeout_ms,
            )
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
        status = raw.get("status")
        try:
            status = int(status)
        except Exception:
            status = 0

        sso = ""
        m = _re.search(r"(?:^|;\s*)sso=([^;]+)", cookie_str)
        if m and len(m.group(1)) > 20:
            sso = m.group(1)
        if not sso:
            m = _re.search(r"(?:^|;\s*)sso-rw=([^;]+)", cookie_str)
            if m and len(m.group(1)) > 20:
                sso = m.group(1)
        if not sso and text:
            m = _re.search(r"\bsso[\"']?\s*[:=]\s*[\"']([^\"']{20,})[\"']", text)
            if m:
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
        timeout: int = 90,
        cancel_callback=None,
    ) -> str:
        """Fill profile form in browser and wait for sso cookie after native SignUp."""
        from grok_register_ttk import _get_page

        page = _get_page()
        stop = cancel_callback or (lambda: False)
        self.install_network_hook()

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
        filled = False
        submitted = False
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
const given = Array.from(document.querySelectorAll('input[name="givenName"], input[data-testid="givenName"], input[autocomplete="given-name"]')).some(isVisible);
const family = Array.from(document.querySelectorAll('input[name="familyName"], input[data-testid="familyName"], input[autocomplete="family-name"]')).some(isVisible);
const pw = Array.from(document.querySelectorAll('input[type="password"], input[name="password"]')).some(isVisible);
const cf = document.querySelector('input[name="cf-turnstile-response"]');
const cfLen = cf ? String(cf.value||'').trim().length : 0;
return {given:!!given, family:!!family, pw:!!pw, cfLen:cfLen, url: location.href};
"""
                )
            except Exception as e:
                self._lg(f"[Debug] UI fallback state: {e}")
                time.sleep(0.6)
                continue

            if not isinstance(state, dict):
                time.sleep(0.5)
                continue

            self._lg(f"[*] UI fallback state={state}")

            # already left signup? check cookies early
            jar = self.export_cookies() or {}
            sso = jar.get("sso") or jar.get("sso-rw") or ""
            if sso and len(str(sso)) > 20:
                self._lg(f"[*] UI fallback sso from cookies early len={len(sso)}")
                return str(sso)

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
                import re as _re

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
