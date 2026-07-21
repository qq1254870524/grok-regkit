"""18r43: isVisible accepts 0x0 rects for silent/minimized browsers.
Browser-only token harvest for Castle / Turnstile (hybrid mode).
2026-07-19r20: CreateEmail 重复请求共享首个 Promise/Response（不再 AbortError，避免 UI toast incomplete envelope）；
2026-07-19r19: blocked_duplicate CreateEmail 不再返回假 JSON(会触发页面 [invalid_argument] protocol error: incomplete envelope)；
              改为 AbortError/abort 静默取消第2+次请求，首发仍放行；consent 见 sso_to_auth_json 18r19。
2026-07-19r18: CreateEmail first-send-only lock — block concurrent 2nd+ CreateEmail (dual-code/rate-limit root fix); first real request always allowed.
2026-07-18g: scrape_next_action 优先 createUserAndSession 邻域，避免抓到 CreateEmail。
2026-07-18i: 恢复主路径 scrape 回退：createUserAndSession → emailValidationCode+castleRequestToken → hook；
              不改变 hybrid 主流程（注册当时即时 SSO + schedule_post_registration；pending 仅兜底）。
2026-07-18j: 新增 scrape_next_action_candidates 多候选；单候选自动拒绝 hybrid 已知死 hash。
2026-07-18k: browser-fetch 用闭包绑定参数（修复 async IIFE arguments 全空导致 next-action 空串 404）；
              解析 Set-Cookie/sso；不再把当前 live SignUp hash 当死 hash 过滤。
2026-07-18r4: CreateEmail 填邮箱前强制等到 email 输入框；点「使用邮箱注册」后轮询；
              仍无输入则硬刷新/重开 signup；CF/空白页不盲填；失败日志带 body/buttons。

2026-07-18r7: 协议已 VerifyEmail 后禁止 open_signup/使用邮箱注册/email re-submit（根因双码）；
              prepare_profile 只确认验证码/等待 profile；UI fallback 有 code 时默认 block CreateEmail。
2026-07-18r12: RESTORE protocol: CreateEmail hook observe-only (no fake Response short-circuit);
               do not disable whole form after click; send-lock skip only after real 2xx;
               UI desync fast-abort after protocol VerifyEmail; last_ui_fallback_result for pending gate.
2026-07-18r10: CreateEmail true-send lock (fetch/XHR short-circuit after first request);
              status exposes actual_send_count/net_hits_raw; click path disables controls after fire.
2026-07-18r9: mint_fresh_castle early-abort on repeated weak ~744 injected tokens; cap redrive/log flood; prefer reuse CreateEmail IBYIll over 32s empty mint.
2026-07-18r8: CreateEmail net_hits>=1+2xx 后禁止二次 click；prepare ready 必须 given/pw/profile，
              仅 cf+code 不算 ready；UI stuck-on-code 可试 alt code；弱 castle(len<1000) 不当 fresh。
2026-07-19r17: prepare_profile stuck on code page >14s abort (no re-send).
2026-07-18r16: UI body rate-limit detect; freeze reclick when actual_send/net_hits>=1.
2026-07-18r14: CreateEmail status JS returns actual_send/blocked/inflight/sent_once; backfill actual from net_hits.
2026-07-20r37: actual_send backfill from net_hits only on 2xx; weak status_unknown no dual-send inflation.
2026-07-20r38: UI fallback reason=running is initial-only; early exits set code_page_stuck/cancelled;
              code-page stuck re-confirm; cf present wait limit 22s (was 14s).
"""
from __future__ import annotations

import os
import re
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
  window.__hybrid_create_email_seen = window.__hybrid_create_email_seen || false;
  window.__hybrid_create_email_inflight = false;
  window.__hybrid_create_email_sent_once = false;
  window.__hybrid_create_email_actual_sends = 0;
  window.__hybrid_create_email_blocked = 0;
  window.__hybrid_create_email_lock = false;
  function isCreateEmailUrl(u) {
    try { return String(u || '').includes('CreateEmailValidationCode'); } catch (e) { return false; }
  }
  // 18r18: first CreateEmail always goes through; block concurrent/duplicate 2nd+ send.
  // Root cause of dual-code / rate-limit was form double-fire (actual_send=2). Do NOT block first send.
  function noteCreateEmailRequest(url) {
    if (!isCreateEmailUrl(url)) return false;
    if (window.__hybrid_create_email_lock || Number(window.__hybrid_create_email_actual_sends || 0) >= 1) {
      window.__hybrid_create_email_blocked = Number(window.__hybrid_create_email_blocked || 0) + 1;
      return true; // block duplicate
    }
    window.__hybrid_create_email_lock = true;
    window.__hybrid_create_email_inflight = true;
    window.__hybrid_create_email_seen = true;
    window.__hybrid_create_email_actual_sends = Number(window.__hybrid_create_email_actual_sends || 0) + 1;
    return false; // allow first
  }
  function markCreateEmailResponse(url, status, ok) {
    if (!isCreateEmailUrl(url)) return;
    window.__hybrid_create_email_status = Number(status || 0);
    window.__hybrid_create_email_ok = !!ok;
    window.__hybrid_create_email_inflight = false;
    if (ok || (Number(status) >= 200 && Number(status) < 300)) {
      window.__hybrid_create_email_sent_once = true;
    }
  }
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
      if (isCreateEmailUrl(u)) {
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
      // 18r20: share first CreateEmail promise so React never sees AbortError/incomplete envelope
      if (isCreateEmailUrl(url) && window.__hybrid_create_email_shared) {
        window.__hybrid_create_email_blocked = Number(window.__hybrid_create_email_blocked || 0) + 1;
        try { console.warn('[hybrid] CreateEmail blocked_duplicate share-first', url); } catch (e) {}
        return window.__hybrid_create_email_shared.then(function(r){
          try { return r.clone(); } catch (e2) { return r; }
        });
      }
      const blockDup = noteCreateEmailRequest(url);
      if (blockDup && window.__hybrid_create_email_shared) {
        try { console.warn('[hybrid] CreateEmail blocked_duplicate share-first(lock)', url); } catch (e) {}
        return window.__hybrid_create_email_shared.then(function(r){
          try { return r.clone(); } catch (e2) { return r; }
        });
      }
      captureBody(init && init.body, url);
      captureHeaders(init && init.headers);
      if (input && typeof input === 'object') {
        try { captureHeaders(input.headers); } catch (e) {}
      }
    } catch (e) {}
    const isCE = (function(){ try { return isCreateEmailUrl(url); } catch (e) { return false; } })();
    let p = ofetch.apply(this, arguments);
    if (isCE) {
      window.__hybrid_create_email_shared = p.then(async function(resp){
        try {
          markCreateEmailResponse(url, resp.status || 0, !!(resp.ok || (resp.status >= 200 && resp.status < 300)));
        } catch (e) {}
        return resp;
      });
      return window.__hybrid_create_email_shared;
    }
    const resp = await p;
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
    try {
      if (noteCreateEmailRequest(this.__u)) {
        // 18r20: complete XHR as aborted silently without error event that surfaces UI toast
        try { console.warn('[hybrid] CreateEmail XHR blocked_duplicate silent', this.__u); } catch (e) {}
        try {
          const xhr = this;
          Object.defineProperty(this, 'status', {configurable:true, get:function(){return 0;}});
          Object.defineProperty(this, 'readyState', {configurable:true, get:function(){return 4;}});
          Object.defineProperty(this, 'responseText', {configurable:true, get:function(){return '';}});
          Object.defineProperty(this, 'response', {configurable:true, get:function(){return '';}});
          // only onabort (not onerror) to avoid React incomplete envelope toast
          setTimeout(function(){
            try { if (typeof xhr.onabort === 'function') xhr.onabort(); } catch (e) {}
          }, 0);
        } catch (e) {}
        return;
      }
    } catch (e) {}
    captureBody(body, this.__u);
    const xhr = this;
    try {
      xhr.addEventListener('load', function(){
        try {
          if (isCreateEmailUrl(xhr.__u)) {
            markCreateEmailResponse(xhr.__u, xhr.status || 0, xhr.status >= 200 && xhr.status < 300);
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
// de-dupe identical url+len pairs so one request logged twice doesn't look like dual-send
const seenKey = new Set();
const uniq = [];
for (const n of hits) {
  const key = String((n&&n.url)||'') + '|' + String((n&&n.len)||0);
  if (seenKey.has(key)) continue;
  seenKey.add(key);
  uniq.push(n);
}
return {
  ok: !!window.__hybrid_create_email_ok,
  status: Number(window.__hybrid_create_email_status||0),
  seen: !!window.__hybrid_create_email_seen,
  castle_len: Number((window.__hybrid_castle||'').length||0),
  net_hits: uniq.length,
  net_hits_raw: hits.length,
  actual_send_count: Number(window.__hybrid_create_email_actual_sends||0),
  blocked_duplicate_count: Number(window.__hybrid_create_email_blocked||0),
  inflight: !!window.__hybrid_create_email_inflight,
  sent_once: !!window.__hybrid_create_email_sent_once,
  net_urls: uniq.slice(0, 5).map(n => String((n&&n.url)||'').slice(0, 160))
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
                        "net_hits_raw": int(raw.get("net_hits_raw") or raw.get("net_hits") or 0),
                        "net_hits_unique": int(raw.get("net_hits_unique") or raw.get("net_hits") or 0),
                        "actual_send_count": int(raw.get("actual_send_count") or 0),
                        "blocked_duplicate_count": int(raw.get("blocked_duplicate_count") or 0),
                        "inflight": bool(raw.get("inflight")),
                        "sent_once": bool(raw.get("sent_once")),
                        "net_urls": list(raw.get("net_urls") or []),
                    }
                )
                # 18r37: only backfill actual_send from net_hits when status is real 2xx.
                # Weak status=0 / seen_status_unknown must NOT inflate dual-send lock.
                _st = int(data.get("status") or 0)
                if (
                    int(data.get("actual_send_count") or 0) <= 0
                    and int(data.get("net_hits") or 0) > 0
                    and 200 <= _st < 300
                ):
                    data["actual_send_count"] = int(data.get("net_hits") or 0)
        except Exception as exc:
            data["reason"] = f"js_error:{exc}"
            return data

        status = int(data.get("status") or 0)
        ok = bool(data.get("ok"))
        seen = bool(data.get("seen")) or int(data.get("net_hits") or 0) > 0
        # Strict: only treat as sent when CreateEmail request was observed AND
        # we have a real success signal. seen_status_unknown alone is NOT enough
        # (network hook may mark seen without a completed 2xx response / code page).
        ui_code_step = False
        try:
            ui_raw = page.run_js(
                """
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity||1) === 0) return false;
  // 18r43: silent/minimized/offscreen windows often report 0x0 rects; still treat as present.
  const rect = node.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) return true;
  try {
    if (node.offsetParent !== null) return true;
    if (String(style.position || '').toLowerCase() === 'fixed') return true;
  } catch (e) {}
  // last resort: accept form controls that are enabled in DOM
  const tag = String(node.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') return !node.disabled;
  return false;
}
const inputs = Array.from(document.querySelectorAll('input, textarea')).filter((n) => isVisible(n) && !n.disabled);
const hasCode = inputs.some((n) => {
  const type = String(n.type || '').toLowerCase();
  const meta = [type, n.name, n.id, n.placeholder, n.getAttribute('aria-label'), n.autocomplete, n.inputMode]
    .join(' ').toLowerCase();
  return type === 'tel' || type === 'number' || meta.includes('code') || meta.includes('otp')
    || meta.includes('验证码') || meta.includes('one-time') || meta.includes('verification');
});
const bodyRaw = String((document.body && (document.body.innerText || document.body.textContent)) || '')
  .replace(/\s+/g, ' ').trim();
const body = bodyRaw.toLowerCase();
const bodyCode = body.includes('验证码') || body.includes('verification code') || body.includes('enter the code')
  || body.includes('check your email') || body.includes('we sent') || body.includes('已发送');
const rateLimited = body.includes('验证码过多') || body.includes('发送到此邮箱的验证码过多')
  || body.includes('too many') || body.includes('too_many')
  || ((body.includes('minute') || body.includes('minutes') || bodyRaw.includes('分钟'))
      && (body.includes('retry') || bodyRaw.includes('重试') || body.includes('try again')));
const busy = !!document.querySelector('[aria-busy="true"], button[disabled][aria-busy="true"]');
return {
  hasCode: !!hasCode,
  bodyCode: !!bodyCode,
  busy: busy,
  url: location.href || '',
  rateLimited: !!rateLimited,
  bodyText: bodyRaw.slice(0, 800)
};
"""
            )
            if isinstance(ui_raw, dict):
                data["ui_has_code"] = bool(ui_raw.get("hasCode"))
                data["ui_body_code"] = bool(ui_raw.get("bodyCode"))
                data["ui_busy"] = bool(ui_raw.get("busy"))
                data["ui_url"] = str(ui_raw.get("url") or "")
                data["ui_rate_limited"] = bool(ui_raw.get("rateLimited"))
                data["ui_body_text"] = str(ui_raw.get("bodyText") or "")
                data["ui_rate_limit_text"] = (
                    str(ui_raw.get("bodyText") or "") if ui_raw.get("rateLimited") else ""
                )
                ui_code_step = bool(ui_raw.get("hasCode") or ui_raw.get("bodyCode"))
                if data["ui_rate_limited"]:
                    data["sent"] = False
                    data["reason"] = "ui_rate_limited"
        except Exception as ui_exc:
            data["ui_probe_err"] = str(ui_exc)

        if ok and 200 <= status < 300:
            data["sent"] = True
            data["reason"] = f"ok_status={status}"
        elif ok and status == 0 and ui_code_step:
            data["sent"] = True
            data["reason"] = "ok_status_unknown_but_code_step"
        elif seen and 200 <= status < 300:
            data["sent"] = True
            data["reason"] = f"seen_status={status}"
        elif seen and status == 0 and ui_code_step:
            data["sent"] = True
            data["reason"] = "seen_status_unknown_code_step"
        elif seen and status == 0:
            # Request may have been initiated, but response not confirmed. Do NOT skip re-click.
            data["sent"] = False
            data["reason"] = "seen_status_unknown"
            data["maybe_inflight"] = True
        elif seen and status >= 400:
            data["sent"] = False
            data["reason"] = f"seen_http_{status}"
        else:
            data["sent"] = False
            data["reason"] = "not_seen"
        # 18r16: rate-limit UI message wins over any 2xx "sent" claim
        if data.get("ui_rate_limited"):
            data["sent"] = False
            data["reason"] = "ui_rate_limited"
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

        # 18r10: never dual-submit if network lock already fired CreateEmail.
        try:
            gate = page.run_js(
                """
return {
  inflight: !!window.__hybrid_create_email_inflight,
  sent_once: !!window.__hybrid_create_email_sent_once,
  actual: Number(window.__hybrid_create_email_actual_sends||0),
  seen: !!window.__hybrid_create_email_seen,
  status: Number(window.__hybrid_create_email_status||0)
};
"""
            )
            # 18r12: skip only after real CreateEmail 2xx (not inflight/status=0).
            st_n = int(gate.get("status") or 0) if isinstance(gate, dict) else 0
            if isinstance(gate, dict) and (
                gate.get("sent_once")
                or (int(gate.get("actual") or 0) >= 1 and 200 <= st_n < 300)
            ):
                self._lg(f"[*] UI CreateEmail click skipped (send-lock-2xx) gate={gate}")
                return f"skip:send-lock:actual={gate.get('actual')}:status={gate.get('status')}"
        except Exception as gate_exc:
            self._lg(f"[Debug] CreateEmail send-lock probe: {gate_exc}")

        # Ensure we are on email-input step (not method chooser / CF / blank SPA)
        def _signup_email_state():
            try:
                return page.run_js(
                    """
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity||1) === 0) return false;
  // 18r43: silent/minimized/offscreen windows often report 0x0 rects; still treat as present.
  const rect = node.getBoundingClientRect();
  if (rect.width > 0 && rect.height > 0) return true;
  try {
    if (node.offsetParent !== null) return true;
    if (String(style.position || '').toLowerCase() === 'fixed') return true;
  } catch (e) {}
  // last resort: accept form controls that are enabled in DOM
  const tag = String(node.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button') return !node.disabled;
  return false;
}
function nodeText(node) {
  return [node.innerText, node.textContent, node.getAttribute('aria-label'), node.getAttribute('title')]
    .filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
const inputs = Array.from(document.querySelectorAll('input, textarea')).filter((n) => isVisible(n) && !n.disabled);
const emailInput = inputs.some((n) => {
  const type = String(n.type || '').toLowerCase();
  if (['password','hidden','checkbox','radio','submit','button'].includes(type)) return false;
  const meta = [type, n.name, n.id, n.placeholder, n.getAttribute('data-testid'), n.getAttribute('aria-label'), n.autocomplete].join(' ').toLowerCase();
  return type === 'email' || meta.includes('email') || meta.includes('mail');
});
const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'))
  .filter((n) => isVisible(n) && !n.disabled)
  .map((n) => nodeText(n))
  .filter(Boolean)
  .slice(0, 12);
const body = String((document.body && (document.body.innerText || document.body.textContent)) || '')
  .replace(/\\s+/g, ' ').trim().slice(0, 240);
const title = document.title || '';
const url = location.href || '';
const blob = (title + ' ' + body + ' ' + url).toLowerCase();
const hasCf = (
  blob.includes('just a moment') || blob.includes('attention required') ||
  blob.includes('checking your browser') || blob.includes('cf-browser-verification') ||
  blob.includes('enable javascript and cookies') ||
  (blob.includes('cloudflare') && !blob.includes('sign'))
);
const hasEmailSignupBtn = buttons.some((t) => {
  const c = String(t||'').replace(/\\s+/g,'');
  const low = c.toLowerCase();
  return c.includes('使用邮箱注册') || low.includes('signupwithemail') ||
    (low.includes('email') && (low.includes('sign') || low.includes('continue') || low.includes('use')));
});
return {
  url, title, emailInput: !!emailInput, hasCf, hasEmailSignupBtn,
  inputCount: inputs.length, buttons, body
};
"""
                )
            except Exception as e:
                return {"error": str(e), "emailInput": False}

        def _wait_email_input(timeout_s: float = 12.0, label: str = "wait"):
            deadline = time.time() + max(2.0, float(timeout_s))
            last = None
            while time.time() < deadline:
                st = _signup_email_state()
                last = st
                if isinstance(st, dict) and st.get("emailInput"):
                    self._lg(f"[*] UI email input ready ({label}) state={st}")
                    return st
                if isinstance(st, dict) and st.get("hasCf"):
                    self._lg(f"[*] UI still CF/challenge ({label}) state={st}")
                time.sleep(0.45)
            self._lg(f"[!] UI email input NOT ready after {timeout_s}s ({label}) last={last}")
            return last if isinstance(last, dict) else {"emailInput": False, "last": last}

        try:
            state = _signup_email_state()
            self._lg(f"[*] UI page state before fill: {state}")
            if not (isinstance(state, dict) and state.get("emailInput")):
                # 1) click method chooser if present
                if isinstance(state, dict) and (state.get("hasEmailSignupBtn") or not state.get("emailInput")):
                    try:
                        click_email_signup_button(timeout=10, log_callback=self.log)
                    except Exception as e:
                        self._lg(f"[!] click_email_signup_button: {e}")
                state = _wait_email_input(15.0, label="after-email-signup-click")

            # 2) hard reopen signup if still missing input
            if not (isinstance(state, dict) and state.get("emailInput")):
                self._lg("[!] email input missing; hard reopen signup page")
                try:
                    from grok_register_ttk import open_signup_page
                    open_signup_page(log_callback=self.log)
                except Exception as e:
                    self._lg(f"[!] reopen open_signup_page fail: {e}")
                    try:
                        page.get("https://accounts.x.ai/sign-up?redirect=grok-com")
                        time.sleep(2.0)
                        click_email_signup_button(timeout=12, log_callback=self.log)
                    except Exception as e2:
                        self._lg(f"[!] manual signup reopen fail: {e2}")
                state = _wait_email_input(16.0, label="after-hard-reopen")

            # 3) one more method-button click + wait
            if not (isinstance(state, dict) and state.get("emailInput")):
                try:
                    click_email_signup_button(timeout=8, log_callback=self.log)
                except Exception as e:
                    self._lg(f"[!] final click_email_signup_button: {e}")
                state = _wait_email_input(8.0, label="final-wait")

            if not (isinstance(state, dict) and state.get("emailInput")):
                self._lg(f"[!] abort fill: still no email input state={state}")
                return "no-email-input"
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
  const t = ((n.innerText || n.textContent || n.value || '') + '').replace(/\s+/g, ' ').trim().slice(0, 60);
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
// 18r12: mark click once for logging only; DO NOT disable whole form (r10 broke SPA/profile).
try {
  if (filledOk && clickHow !== 'none' && clickHow !== 'click-fail' && clickHow !== 'fallback-fail') {
    window.__hybrid_create_email_ui_locked = true;
  }
} catch (eLockAll) {}
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
  candidates: candidates.filter(c => c.visible).slice(0, 12),
  ui_locked: !!window.__hybrid_create_email_ui_locked
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

    def clear_captured_castles(self, reason: str = "") -> None:
        """Drop native/injected castle captures so SignUp cannot reuse CreateEmail token."""
        from grok_register_ttk import _get_page

        page = _get_page()
        try:
            page.run_js(
                """
window.__hybrid_castle='';
window.__hybrid_castles=[];
window.__hybrid_castle_status='';
window.__hybrid_castle_err='';
window.__hybrid_castle_script=false;
true;
"""
            )
        except Exception as e:
            self._lg(f"[Debug] clear_captured_castles: {e}")
        else:
            why = f" reason={reason}" if reason else ""
            self._lg(f"[*] cleared captured castles{why}")

    def mint_fresh_castle_token(self, timeout: int = 25, reason: str = "signup") -> str:
        """Force a new Castle createRequestToken; never return previous capture first.

        18r9: injected junk tokens (~744) with status=done are not real Castle tokens.
        After a few consecutive weak results, abort early so hybrid can reuse CreateEmail
        IBYIll castle instead of burning ~32s of empty re-mint logs.
        """
        self.clear_captured_castles(reason=f"before_mint:{reason}")
        # Always re-drive SDK mint even if previous status was done.
        try:
            from grok_register_ttk import _get_page

            page = _get_page()
            page.run_js(
                "window.__hybrid_castle=''; window.__hybrid_castles=[]; window.__hybrid_castle_status=''; window.__hybrid_castle_script=false; true;"
            )
        except Exception:
            pass
        pk = self._extract_castle_pk()
        # Bypass "already done" short-circuit inside _ensure_castle_sdk by clearing status first.
        try:
            from grok_register_ttk import _get_page

            page = _get_page()
            page.run_js(
                "window.__hybrid_castle=''; window.__hybrid_castles=[]; window.__hybrid_castle_status=''; true;"
            )
        except Exception:
            pass
        self._ensure_castle_sdk(pk)
        # Prefer injected mint result (window.__hybrid_castle), not old capture list.
        from grok_register_ttk import _get_page

        page = _get_page()
        # 18r9: cap wall time; early abort on repeated weak injected tokens.
        deadline = time.time() + max(4, min(int(timeout or 25), 12))
        last = ""
        weak_hits = 0
        hard_fail_hits = 0
        redrive_count = 0
        while time.time() < deadline:
            try:
                data = page.run_js(
                    """
const status = String(window.__hybrid_castle_status || '');
const injected = String(window.__hybrid_castle || '');
const list = window.__hybrid_castles || [];
let best = injected;
for (const t of list) {
  if (String(t||'').length > String(best||'').length) best = String(t);
}
return {status: status, castle: best || '', injected_len: injected.length, n: list.length, err: String(window.__hybrid_castle_err||'')};
"""
                )
                if isinstance(data, dict):
                    castle = str(data.get("castle") or "")
                    st = str(data.get("status") or "")
                    last = f"{st}|inj={data.get('injected_len')}|n={data.get('n')}|err={data.get('err')}"
                    if castle and 0 < len(castle) < 1000:
                        weak_hits += 1
                        # 18r8/18r9: weak/injected junk must never be treated as fresh.
                        # Only log first 2 and every 5th to avoid log flood.
                        if weak_hits <= 2 or weak_hits % 5 == 0:
                            self._lg(
                                f"[!] mint_fresh_castle weak discard reason={reason} status={st} "
                                f"len={len(castle)} head={castle[:24]} weak_hits={weak_hits}"
                            )
                        # 18r9: after 3 consecutive weak "done" junk tokens, stop early.
                        if weak_hits >= 3 and st in ("done", "empty", "error", "exception", "sdk-fail", "no-method"):
                            self._lg(
                                f"[!] mint_fresh_castle early-abort reason={reason} "
                                f"weak_hits={weak_hits} last={last} (reuse CreateEmail castle)"
                            )
                            return ""
                        # redrive at most twice; more redrives just spam 744 junk
                        if redrive_count < 2:
                            redrive_count += 1
                            page.run_js(
                                "window.__hybrid_castle=''; window.__hybrid_castles=[]; "
                                "window.__hybrid_castle_status=''; window.__hybrid_castle_script=false; true;"
                            )
                            self._ensure_castle_sdk(pk)
                            time.sleep(0.35)
                        else:
                            time.sleep(0.25)
                        continue
                    if len(castle) >= 1000 and str(castle).startswith("IBYIll"):
                        src = "injected_fresh" if st in ("done", "minting", "") or int(data.get("injected_len") or 0) >= 1000 else "native_or_injected"
                        self._lg(
                            f"[*] mint_fresh_castle ok reason={reason} src={src} status={st} "
                            f"len={len(castle)} head={castle[:40]}"
                        )
                        return castle
                    if len(castle) >= 2000:
                        self._lg(
                            f"[*] mint_fresh_castle ok(long-nonprefix) reason={reason} status={st} "
                            f"len={len(castle)} head={castle[:40]}"
                        )
                        return castle
                    if st in ("no-method", "sdk-fail", "error", "exception", "empty"):
                        hard_fail_hits += 1
                        if hard_fail_hits >= 2:
                            self._lg(
                                f"[!] mint_fresh_castle hard-fail abort reason={reason} "
                                f"hits={hard_fail_hits} last={last}"
                            )
                            return ""
                        page.run_js(
                            "window.__hybrid_castle_script=false; window.__hybrid_castle_status=''; true;"
                        )
                        self._ensure_castle_sdk(pk)
            except Exception as e:
                last = str(e)
            time.sleep(0.35)
        self._lg(f"[!] mint_fresh_castle timeout reason={reason} last={last} weak_hits={weak_hits}")
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
window.__hybrid_create_email_inflight=false;
window.__hybrid_create_email_sent_once=false;
window.__hybrid_create_email_actual_sends=0;
window.__hybrid_create_email_blocked=0;
true;
"""
            )
        except Exception:
            pass

        self._lg(f"[*] harvest CreateEmail start email={email} timeout={timeout}")
        click_r = self.click_email_continue_for_create(email)
        self._lg(f"[*] UI email submit click={click_r} email={email}")
        if str(click_r).startswith("fail:") or str(click_r) in ("no-input", "no-email-input", "empty-email"):
            self._lg(f"[!] first email fill/click failed: {click_r} — will retry in loop (no-input does not count as CreateEmail send)")

        deadline = time.time() + max(15, int(timeout))
        last_retry = time.time()
        retries = 0
        # Hard limit: at most 1 re-click for unconfirmed send.
        # Extra case: button spinner / network stuck with seen_status_unknown → one more click.
        # Multiple CreateEmail on same mailbox triggers xAI "验证码过多 / retry in N minutes".
        max_retries = 1
        spinner_reclick_done = False
        first_seen_ts = 0.0
        while time.time() < deadline:
            st = self.create_email_status_via_browser()
            c = self.read_captured_castle()
            if st.get("seen") and not first_seen_ts:
                first_seen_ts = time.time()
            net_hits = int(st.get("net_hits") or 0)
            status_n = int(st.get("status") or 0)
            code_step = bool(st.get("ui_has_code") or st.get("ui_body_code"))
            # 18r8: any real CreateEmail evidence freezes further clicks (prevent dual-code).
            actual_n = int(st.get("actual_send_count") or 0)
            # 18r16: any real CreateEmail request already fired → freeze (防双发/验证码过多)
            hard_no_reclick = bool(
                st.get("sent")
                or actual_n >= 1
                or net_hits >= 1
                or (code_step and (st.get("seen") or net_hits >= 1 or bool(st.get("ok"))))
                or bool(st.get("ui_rate_limited"))
            )
            if st.get("ui_rate_limited"):
                self._lg(
                    f"[!] CreateEmail UI rate-limited body={st.get('ui_body_text')!r} "
                    f"email={email} actual_send={actual_n} net_hits={net_hits}"
                )
            if hard_no_reclick:
                self._lg(
                    f"[*] CreateEmail freeze-reclick reason={st.get('reason')} "
                    f"status={status_n} seen={st.get('seen')} net_hits={net_hits} "
                    f"raw={st.get('net_hits_raw')} actual_send={st.get('actual_send_count')} "
                    f"blocked_dup={st.get('blocked_duplicate_count')} "
                    f"sent={int(bool(st.get('sent')))} "
                    f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')} "
                    f"castle_len={st.get('castle_len') or (len(c) if c else 0)}"
                )
                if c:
                    self._lg(f"[*] native castle len={len(c)} head={c[:20]}")
                    return c
                time.sleep(0.45)
                continue
            elif c and (time.time() + 8) >= deadline:
                self._lg(
                    f"[!] CreateEmail not confirmed yet but castle present "
                    f"len={len(c)} reason={st.get('reason')} - wait without extra click"
                )

            # Spinner / net-card stuck: request seen but no 2xx and still on email step.
            maybe_inflight = bool(st.get("maybe_inflight") or st.get("reason") == "seen_status_unknown")
            ui_busy = bool(st.get("ui_busy"))
            stuck_long = bool(first_seen_ts and (time.time() - first_seen_ts >= 6.0))
            if net_hits >= 1:
                # Request already fired; only wait for status/code page, never dual-send.
                time.sleep(0.45)
                continue
            if (
                (not st.get("sent"))
                and maybe_inflight
                and stuck_long
                and (not spinner_reclick_done)
                and retries < max_retries
                and net_hits == 0
            ):
                spinner_reclick_done = True
                last_retry = time.time()
                try:
                    self._hooked = False
                    self.install_network_hook()
                except Exception:
                    pass
                click_r = self.click_email_continue_for_create(email)
                if str(click_r) not in ("no-email-input", "no-input", "empty-email") and not str(click_r).startswith("fail:no"):
                    retries += 1
                self._lg(
                    f"[*] UI CreateEmail spinner/stuck re-click#{retries}/{max_retries} "
                    f"click={click_r} email={email} busy={ui_busy} reason={st.get('reason')} "
                    f"status={st.get('status')} seen={st.get('seen')} net_hits={st.get('net_hits')} "
                    f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')}"
                )
            elif (
                (not st.get("sent"))
                and (time.time() - last_retry >= 5.0)
                and retries < max_retries
                and int(st.get("net_hits") or 0) == 0
                and not bool(st.get("ui_has_code") or st.get("ui_body_code"))
            ):
                last_retry = time.time()
                try:
                    self._hooked = False
                    self.install_network_hook()
                except Exception:
                    pass
                click_r = self.click_email_continue_for_create(email)
                # only burn the single re-click budget when page actually had an email input path
                if str(click_r) not in ("no-email-input", "no-input", "empty-email") and not str(click_r).startswith("fail:no"):
                    retries += 1
                self._lg(
                    f"[*] UI CreateEmail retry#{retries}/{max_retries} click={click_r} email={email} "
                    f"status={st.get('status')} seen={st.get('seen')} ok={st.get('ok')} "
                    f"net_hits={st.get('net_hits')} reason={st.get('reason')} "
                    f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')} "
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
        """Export cookies from current Chromium; prefer all_domains to catch host-only sso."""
        from grok_register_ttk import _get_browser, _get_page

        jar = {}
        try:
            browser = _get_browser()
            page = None
            try:
                page = _get_page()
            except Exception:
                page = None
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
            if not cookies and browser is not None:
                try:
                    cookies = browser.cookies() or []
                except Exception:
                    cookies = []
            for c in cookies or []:
                if isinstance(c, dict):
                    n, v = c.get("name", ""), c.get("value", "")
                else:
                    n, v = getattr(c, "name", ""), getattr(c, "value", "")
                if n:
                    jar[str(n)] = str(v)
            if page is not None and "sso" not in jar:
                try:
                    doc = page.run_js("return document.cookie || ''") or ""
                    import re as _re
                    m = _re.search(r"(?:^|;\s*)sso=([^;]+)", str(doc))
                    if m and len(m.group(1)) >= 20:
                        jar["sso"] = m.group(1)
                except Exception:
                    pass
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
        # already minting / done? Only skip when a non-empty token is still present.
        try:
            st = page.run_js(
                "return {s: window.__hybrid_castle_status||'', l:(window.__hybrid_castle||'').length};"
            )
            if isinstance(st, dict) and st.get("s") == "done" and int(st.get("l") or 0) > 40:
                return True
            if isinstance(st, dict) and st.get("s") == "minting" and int(st.get("l") or 0) > 40:
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

        # 18r42c: after helper fail, do not burn full 80s when widget never mounts
        effective_timeout = int(timeout)
        try:
            has_w = page.run_js(
                """
try {
  return !!(document.querySelector('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"], .cf-turnstile iframe, input[name="cf-turnstile-response"]'));
} catch (e) { return false; }
"""
            )
            if not has_w:
                effective_timeout = min(effective_timeout, 12)
                self._lg("[Debug] turnstile poll shortened: no widget on page")
        except Exception:
            pass
        deadline = time.time() + effective_timeout
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
        self,
        email: str,
        code: str,
        timeout: int = 90,
        *,
        allow_email_resend: bool = False,
        protocol_verified: bool = True,
    ) -> bool:
        """Drive UI toward profile/turnstile WITHOUT re-issuing CreateEmail.

        2026-07-18r7 root cause fix:
        Protocol already CreateEmail + VerifyEmail. open_signup() + click email signup
        + email submit creates a SECOND validation code (dual-code), then old code fails.
        Default: never reopen signup, never click email-signup, never submit email.
        Only confirm code on verification page and wait for profile/turnstile.
        """
        from grok_register_ttk import _get_page

        page = _get_page()
        clean = re.sub(r"[^A-Za-z0-9]", "", str(code or ""))
        if len(clean) > 8:
            clean = clean[-8:]
        block_resend = bool(protocol_verified or clean) and not allow_email_resend
        code_stuck_since = None  # 18r17: track stuck-on-code duration
        self._lg(
            f"[*] prepare_profile_step start protocol_verified={int(bool(protocol_verified))} "
            f"allow_email_resend={int(bool(allow_email_resend))} block_resend={int(block_resend)} "
            f"code_len={len(clean)}"
        )

        # Inspect current page first. Do NOT open_signup when already mid-flow.
        try:
            cur = page.run_js(
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
        except Exception as e:
            cur = {}
            self._lg(f"[Debug] prepare_profile initial state: {e}")

        if isinstance(cur, dict) and (
            cur.get("pw") or cur.get("cf") or cur.get("given") or cur.get("code") or cur.get("email")
        ):
            self._lg(f"[*] prepare_profile keep current page (no open_signup) state={cur}")
        elif not block_resend:
            try:
                self.open_signup()
                self._lg("[*] prepare_profile open_signup (allow_email_resend path only)")
            except Exception as e:
                self._lg(f"[Debug] reopen signup: {e}")
        else:
            self._lg(
                "[*] prepare_profile SKIP open_signup (protocol already verified; "
                "reopen would re-click email signup and re-send code)"
            )

        deadline = time.time() + timeout
        email_done = False
        code_done = False
        chooser_clicks = 0
        while time.time() < deadline:
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
const pw = Array.from(document.querySelectorAll('input[type="password"], input[name="password"]')).some(isVisible);
const cf = !!document.querySelector('input[name="cf-turnstile-response"], div.cf-turnstile, iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]');
const email = Array.from(document.querySelectorAll('input[type="email"], input[name="email"], input[data-testid="email"]')).some(isVisible);
const code = Array.from(document.querySelectorAll('input[data-input-otp="true"], input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"]')).some(isVisible)
  || Array.from(document.querySelectorAll('input')).filter(n => isVisible(n) && Number(n.maxLength||0)===1).length >= 4;
const given = Array.from(document.querySelectorAll('input[name="givenName"], input[name="familyName"], input[autocomplete="given-name"]')).some(isVisible);
return {pw:!!pw, cf:!!cf, email:!!email, code:!!code, given:!!given, url: location.href};
"""
                )
            except Exception as e:
                self._lg(f"[Debug] prepare_profile state: {e}")
                time.sleep(0.6)
                continue

            # 18r8: only real profile/name/password is ready.
            # cf widget can exist on code page; code+cf is NOT profile ready.
            if isinstance(state, dict):
                has_profile_fields = bool(state.get("pw") or state.get("given"))
                still_on_code = bool(state.get("code")) and not has_profile_fields
                if has_profile_fields and not still_on_code:
                    self._lg(f"[*] profile/turnstile ready state={state}")
                    return True
                if state.get("cf") and still_on_code:
                    self._lg(
                        f"[*] prepare_profile cf present but still on code page; "
                        f"NOT ready state={state}"
                    )

            if isinstance(state, dict) and state.get("code") and clean and not code_done:
                r = self._set_input_and_submit(clean, "code")
                self._lg(f"[*] UI code submit (no-resend path): {r}")
                code_done = True
                time.sleep(2.0)
                continue
            if isinstance(state, dict) and state.get("code") and clean and code_done:
                if code_stuck_since is None:
                    code_stuck_since = time.time()
                stuck_for = time.time() - code_stuck_since
                # 18r38: cf widget on code page often needs longer + periodic re-confirm
                stuck_limit = 22.0 if bool(state.get("cf")) else 14.0
                self._lg(
                    f"[*] prepare_profile still on code after confirm; keep waiting "
                    f"(no open_signup / no email re-submit) stuck={stuck_for:.1f}s "
                    f"limit={stuck_limit:.0f}s state={state}"
                )
                # periodic re-confirm (not resend email) every ~4s
                if stuck_for >= 3.5 and int(stuck_for) % 4 == 0:
                    try:
                        r = self._set_input_and_submit(clean, "code")
                        self._lg(f"[*] prepare_profile stuck re-confirm code: {r}")
                    except Exception as re_exc:
                        self._lg(f"[Debug] prepare_profile stuck re-confirm: {re_exc}")
                if stuck_for >= stuck_limit:
                    self._lg(
                        f"[!] prepare_profile code page stuck {stuck_for:.1f}s >= {stuck_limit:.0f}s; "
                        f"abort without re-send protocol_verified={int(bool(protocol_verified))}"
                    )
                    try:
                        self.last_ui_fallback_result = {
                            "reason": "code_page_stuck",
                            "signup_confirmed": False,
                            "protocol_verified": bool(protocol_verified),
                            "submitted": False,
                            "stuck_for": round(stuck_for, 1),
                            "stuck_limit": stuck_limit,
                            "state": dict(state) if isinstance(state, dict) else {},
                        }
                    except Exception:
                        pass
                    return False
                time.sleep(1.0)
                continue

            if isinstance(state, dict) and state.get("email") and not email_done:
                if block_resend:
                    self._lg(
                        "[!] prepare_profile sees email page after protocol VerifyEmail; "
                        "SKIP email submit to prevent dual-code CreateEmail reissue"
                    )
                    email_done = True
                    time.sleep(0.8)
                    continue
                r = self._set_input_and_submit(email, "email")
                self._lg(f"[*] UI email submit: {r}")
                email_done = True
                time.sleep(1.5)
                continue

            if (
                isinstance(state, dict)
                and not state.get("email")
                and not state.get("code")
                and not state.get("given")
                and not state.get("pw")
            ):
                if block_resend:
                    if chooser_clicks == 0:
                        self._lg(
                            "[*] prepare_profile on method chooser but block_resend=1; "
                            "will NOT click email signup (prevents dual-code)"
                        )
                    chooser_clicks += 1
                else:
                    try:
                        from grok_register_ttk import click_email_signup_button

                        click_email_signup_button(timeout=5, log_callback=self.log)
                        chooser_clicks += 1
                    except Exception:
                        pass
            time.sleep(0.8)
        self._lg("[!] profile step timeout (no-resend)")
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
        2026-07-18n: after code-submitted keep advancing/confirming; capture page errors; one re-confirm if still on code.
        2026-07-18q: export_cookies 使用 page.cookies(all_domains) + document.cookie 兜底，避免漏收 host-only sso。
2026-07-18o: after VerifyEmail/protocol path, if UI still on code page: fill+confirm once/twice, longer wait for profile, Enter fallback, avoid endless 确认邮箱 loops; never re-send email.
2026-07-18r6: CreateEmail 仅在 HTTP 2xx/ok 或进入验证码页时算 sent；seen_status_unknown 不再当发信成功；注册按钮转圈超时后自动二次点击（限1次）。
2026-07-18r5: alnum verification codes (26I-NNM) no longer stripped to digits; force fresh castle mint helpers; UI stuck-on-code aborts early after prepare_profile push.
2026-07-18r7: code already present (=protocol VerifyEmail) => email_done True; block UI email submit/open_signup reissue; prepare_profile no-resend.
2026-07-18r8: prepare ready requires profile fields; CreateEmail freeze after first net hit; UI stuck-on-code tries alt codes once.
        """
        from grok_register_ttk import _get_page

        page = _get_page()
        stop = cancel_callback or (lambda: False)
        self.install_network_hook()

        email_val = (email or "").strip()
        code_val = (code or "").strip()
        import re as _re

        # xAI codes are often alnum like 26I-NNM; strip separators only.
        # Digits-only stripping used to destroy mixed codes and trap UI on 确认邮箱.
        code_raw = code_val
        code_alnum = _re.sub(r"[^A-Za-z0-9]", "", code_val)
        if len(code_alnum) >= 4:
            code_val = code_alnum[-8:] if len(code_alnum) > 8 else code_alnum
        self._lg(
            f"[*] UI fallback code normalize raw={code_raw!r} -> {code_val!r} "
            f"(alnum_len={len(code_alnum)})"
        )

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
        # Protocol path already did CreateEmail + VerifyEmail. Having a code means
        # re-submitting email would issue a second code (dual-code bug).
        protocol_verified = bool(code_val)
        email_done = bool(protocol_verified)
        code_done = False
        code_confirm_tries = 0
        filled = False
        submitted = False
        last_state_sig = ""
        last_page_err = ""
        email_page_blocked_hits = 0
        self.last_ui_fallback_result = {
            "reason": "running",
            "signup_confirmed": False,
            "protocol_verified": bool(protocol_verified),
            "submitted": False,
            "email_page_blocked_hits": 0,
        }
        if protocol_verified:
            self._lg(
                "[*] UI fallback protocol_verified=1; block email re-submit / open_signup "
                "(prevent dual-code CreateEmail)"
            )
        # 18r8: collect dual-code candidates for stuck verification recovery
        alt_codes = []
        try:
            from aol_mail import LAST_OAI_CODE_CANDIDATES

            for item in list(LAST_OAI_CODE_CANDIDATES or []):
                raw_c = ""
                if isinstance(item, dict):
                    raw_c = str(item.get("code") or "")
                else:
                    raw_c = str(item or "")
                cc = _re.sub(r"[^A-Za-z0-9]", "", raw_c)
                if len(cc) >= 4 and cc != code_val and cc not in alt_codes:
                    alt_codes.append(cc[-8:] if len(cc) > 8 else cc)
            if alt_codes:
                self._lg(
                    f"[*] UI fallback dual-code candidates={len(alt_codes)} "
                    f"alts={[a for a in alt_codes[:4]]}"
                )
        except Exception as alt_load_exc:
            self._lg(f"[Debug] UI fallback alt-code load: {alt_load_exc}")
        alt_code_idx = 0
        tried_alt_codes = set()
        while time.time() < deadline:
            if stop():
                self._lg("[*] UI fallback cancelled")
                try:
                    self.last_ui_fallback_result = {
                        "reason": "cancelled",
                        "signup_confirmed": False,
                        "protocol_verified": bool(protocol_verified),
                        "submitted": bool(submitted),
                        "email_page_blocked_hits": int(email_page_blocked_hits),
                    }
                except Exception:
                    pass
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
const bodyText = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 240);
let err = '';
const low = bodyText.toLowerCase();
if (low.includes('过多') || low.includes('too many') || low.includes('rate')) err = 'rate_limit';
else if (low.includes('invalid') || low.includes('不正确') || low.includes('无效') || low.includes('wrong')) err = 'invalid_code_or_input';
else if (low.includes('expired') || low.includes('过期')) err = 'expired';
return {
  email: !!emailInput,
  code: !!codeInput,
  given: !!given,
  family: !!family,
  pw: !!pw,
  cfLen: cfLen,
  url: location.href,
  hasProfile: !!(given && family && pw),
  err: err,
  body: bodyText
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
            page_err = str((state or {}).get("err") or "").strip()
            if page_err and page_err != last_page_err:
                self._lg(f"[!] UI fallback page_err={page_err} body={(state or {}).get('body')}")
                last_page_err = page_err

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
            # 18r7: if protocol already verified, never CreateEmail again.
            if (
                email_val
                and state.get("email")
                and not has_profile
                and not email_done
                and not protocol_verified
            ):
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
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
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

            if (
                protocol_verified
                and email_val
                and state.get("email")
                and not has_profile
                and not state.get("code")
            ):
                email_page_blocked_hits += 1
                if "email_page_blocked" not in last_state_sig:
                    last_state_sig = f"email_page_blocked|{last_state_sig}"
                    self._lg(
                        "[!] UI fallback sees email page after protocol VerifyEmail; "
                        "SKIP CreateEmail re-submit (dual-code prevention) "
                        f"hit={email_page_blocked_hits}"
                    )
                if email_page_blocked_hits >= 3:
                    self.last_ui_fallback_result = {
                        "reason": "email_page_desync_after_protocol_verify",
                        "signup_confirmed": False,
                        "protocol_verified": True,
                        "submitted": False,
                        "email_page_blocked_hits": email_page_blocked_hits,
                        "url": str(state.get("url") or ""),
                    }
                    self._lg(
                        f"[!] UI fallback abort: protocol verified but UI stuck on email page "
                        f"hits={email_page_blocked_hits} (not registered; not pending_sso)"
                    )
                    return ""


            # Step 2: still on verification code page.
            # Protocol may already have VerifyEmail; UI can lag. Confirm limited times, wait for profile.
            if code_val and state.get("code") and not has_profile and (not code_done or code_confirm_tries < 2):
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
  return String(input.value||'').replace(/\s+/g,'') === String(value||'').replace(/\s+/g,'');
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
const input = pick('input[name="code"], input[name="emailValidationCode"], input[autocomplete="one-time-code"], input[inputmode="numeric"], input[data-testid="code"], input[type="text"], input[type="tel"]');
if (!input) return 'no-code-input';
if (!setVal(input, code)) return 'code-fill-failed';
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]'))
  .filter(n => isVisible(n) && !n.disabled && n.getAttribute('aria-disabled') !== 'true');
const btn = buttons.find(n => {
  const t = buttonText(n).replace(/\s+/g, '').toLowerCase();
  return t.includes('继续') || t.includes('下一步') || t.includes('验证') || t.includes('confirm') || t.includes('continue') || t.includes('next') || t.includes('verify') || t.includes('确认邮箱') || t.includes('确认');
}) || buttons.find(n => String(n.getAttribute('type')||'').toLowerCase() === 'submit') || null;
if (!btn) {
  try {
    input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    return 'code-enter';
  } catch (e) {
    return 'code-filled-no-btn';
  }
}
btn.focus();
btn.click();
return 'code-submitted:' + buttonText(btn);
""",
                        code_val,
                    )
                    self._lg(f"[*] UI fallback code step={step_r}")
                    if str(step_r).startswith("code-submitted") or str(step_r) in ("code-filled-no-btn", "code-enter"):
                        code_done = True
                        code_confirm_tries += 1
                        # longer wait for profile form after protocol VerifyEmail
                        time.sleep(3.2 if code_confirm_tries == 1 else 2.0)
                        continue
                except Exception as e:
                    self._lg(f"[Debug] UI fallback code step: {e}")

            # Protocol VerifyEmail already 200: if still on code after 2 confirms, try profile push then fail fast.
            if code_done and not has_profile and state.get("code") and code_confirm_tries >= 2 and code_confirm_tries < 4:
                try:
                    body = str((state or {}).get("body") or "")
                    self._lg(
                        f"[*] UI fallback still on code after confirms tries={code_confirm_tries}; "
                        f"push prepare_profile_step body={body[:120]!r}"
                    )
                    pushed = self.prepare_profile_step_for_turnstile(
                        email_val or email,
                        code_val,
                        timeout=25,
                        allow_email_resend=False,
                        protocol_verified=True,
                    )
                    self._lg(f"[*] UI fallback prepare_profile_step pushed={pushed} (no-resend)")
                    code_confirm_tries = 4
                    time.sleep(1.2)
                    continue
                except Exception as prep_exc:
                    self._lg(f"[Debug] UI fallback prepare_profile_step: {prep_exc}")
                    code_confirm_tries = 4

            # 18r8: before hard abort, try next dual-code candidate once each.
            if (
                code_done
                and not has_profile
                and state.get("code")
                and code_confirm_tries >= 2
                and alt_code_idx < len(alt_codes)
            ):
                nxt = alt_codes[alt_code_idx]
                alt_code_idx += 1
                if nxt and nxt not in tried_alt_codes:
                    tried_alt_codes.add(nxt)
                    self._lg(
                        f"[*] UI fallback stuck on code; try alt dual-code "
                        f"{alt_code_idx}/{len(alt_codes)} code={nxt}"
                    )
                    code_val = nxt
                    code_done = False
                    code_confirm_tries = 0
                    time.sleep(0.8)
                    continue

            # Hard fail: still code page after push attempts - avoid 90s empty loop.
            if code_done and not has_profile and state.get("code") and code_confirm_tries >= 4:
                body = str((state or {}).get("body") or "")
                page_err = str((state or {}).get("err") or "")
                self._lg(
                    f"[!] UI fallback stuck on verification page after protocol VerifyEmail; "
                    f"abort early err={page_err!r} body={body[:160]!r} "
                    f"alts_tried={len(tried_alt_codes)}"
                )
                try:
                    self.last_ui_fallback_result = {
                        "reason": "code_page_stuck",
                        "signup_confirmed": False,
                        "protocol_verified": bool(protocol_verified),
                        "submitted": False,
                        "email_page_blocked_hits": int(email_page_blocked_hits),
                        "code_confirm_tries": int(code_confirm_tries),
                        "alts_tried": len(tried_alt_codes),
                        "page_err": page_err[:160],
                    }
                except Exception:
                    pass
                return ""

            # If stuck after code confirm, try continue/next/Enter without re-sending email.
            if code_done and not has_profile and not state.get("email") and code_confirm_tries >= 1 and code_confirm_tries <= 3:
                try:
                    cont_r = page.run_js(
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
const btn = buttons.find(n => {
  const t = buttonText(n).replace(/\s+/g, '').toLowerCase();
  if (t.includes('重新') || t.includes('resend') || t.includes('发送验证') || t.includes('sendcode')) return false;
  return t.includes('继续') || t.includes('下一步') || t.includes('确认') || t.includes('验证') ||
         t.includes('continue') || t.includes('next') || t.includes('confirm') || t.includes('verify');
}) || null;
if (!btn) {
  const codeInput = Array.from(document.querySelectorAll('input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"]')).find(isVisible) || null;
  if (codeInput) {
    try {
      codeInput.focus();
      codeInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
      codeInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
      return 'enter-on-code:' + buttons.map(buttonText).filter(Boolean).slice(0, 8).join(' | ');
    } catch (e) {}
  }
  return 'no-continue:' + buttons.map(buttonText).filter(Boolean).slice(0, 8).join(' | ');
}
btn.focus();
btn.click();
return 'continue:' + buttonText(btn);
"""
                    )
                    self._lg(f"[*] UI fallback post-code continue={cont_r}")
                    code_confirm_tries += 1
                    time.sleep(1.6)
                except Exception as e:
                    self._lg(f"[Debug] UI fallback post-code continue: {e}")

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
                        try:
                            self.last_ui_fallback_result = dict(self.last_ui_fallback_result or {})
                            self.last_ui_fallback_result.update({
                                "submitted": True,
                                "signup_confirmed": True,
                                "reason": "profile_submitted",
                            })
                        except Exception:
                            pass
                except Exception as e:
                    self._lg(f"[Debug] UI fallback click: {e}")

            # poll sso after submit or always
            jar = self.export_cookies() or {}
            sso = jar.get("sso") or jar.get("sso-rw") or ""
            if sso and len(str(sso)) > 20:
                self._lg(f"[*] UI fallback sso ok len={len(sso)}")
                try:
                    self.last_ui_fallback_result = {
                        "reason": "sso_ok",
                        "signup_confirmed": True,
                        "protocol_verified": bool(protocol_verified),
                        "submitted": bool(submitted),
                        "email_page_blocked_hits": int(email_page_blocked_hits),
                    }
                except Exception:
                    pass
                return str(sso)

            # document.cookie fallback
            try:
                doc = page.run_js(
                    "return document.cookie || '';"
                ) or ""
                m = _re.search(r"(?:^|;\s*)sso=([^;]+)", str(doc))
                if m and len(m.group(1)) > 20:
                    self._lg(f"[*] UI fallback sso from document.cookie len={len(m.group(1))}")
                    try:
                        self.last_ui_fallback_result = {
                            "reason": "sso_ok_document_cookie",
                            "signup_confirmed": True,
                            "protocol_verified": bool(protocol_verified),
                            "submitted": bool(submitted),
                            "email_page_blocked_hits": int(email_page_blocked_hits),
                        }
                    except Exception:
                        pass
                    return m.group(1)
            except Exception:
                pass

            time.sleep(0.8)

        self._lg("[!] UI fallback timeout without sso")
        try:
            self.last_ui_fallback_result = {
                "reason": "timeout_no_sso",
                "signup_confirmed": bool(submitted),
                "protocol_verified": bool(protocol_verified),
                "submitted": bool(submitted),
                "email_page_blocked_hits": int(email_page_blocked_hits),
            }
        except Exception:
            pass
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
