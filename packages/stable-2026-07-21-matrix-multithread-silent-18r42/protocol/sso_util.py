"""Normalize xAI SSO cookies (set-cookie chain wrapper → session JWT).

Changelog:
- 2026-07-21r42d: normalize_sso_token + is_mail_token_blob + strict is_session_sso;
  reject Outlook mail_token / pending reason as SSO for import paths.
- 2026-07-18r10: staged materialize logs + tighter per-URL waits.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse


def _b64json(segment: str) -> Optional[dict]:
    try:
        pad = "=" * ((4 - len(segment) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(segment + pad))
    except Exception:
        return None


def normalize_sso_token(raw: str) -> str:
    """Strip sso=/sso: prefixes, quotes, and accidental leading dashes."""
    text = str(raw or "").strip()
    if not text:
        return ""
    low = text.lower()
    if low.startswith("sso="):
        text = text[4:].strip()
    elif low.startswith("sso:"):
        text = text[4:].strip()
    text = text.strip().strip('"').strip("'")
    # some hybrid dumps prefix session JWT with a single '-'
    while text.startswith("-") and text[1:].count(".") == 2:
        text = text[1:].strip()
    return text


def decode_jwt_payload(token: str) -> Optional[dict]:
    token = normalize_sso_token(token)
    parts = token.split(".")
    if len(parts) < 2:
        return None
    return _b64json(parts[1])


def _try_b64_json_blob(raw: str) -> Optional[dict]:
    """Decode pending-file mail_token blobs (optional b64: prefix)."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.lower().startswith("b64:"):
        text = text[4:].strip()
    # raw JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    # base64 / urlsafe base64 of JSON
    try:
        pad = "=" * ((4 - len(text) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(text + pad))
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    try:
        pad = "=" * ((4 - len(text) % 4) % 4)
        data = json.loads(base64.b64decode(text + pad))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_mail_token_blob(raw: str) -> bool:
    """True if value is Outlook/AOL mailbox token JSON, NOT xAI session SSO.

    Pending queue format:
      email----password----reason----b64:{email,access_token,refresh_token,...}
    Importing that 4th field (or a 3-field line that ends with it) as SSO must fail.
    """
    text = str(raw or "").strip()
    if not text:
        return False
    low = text.lower()
    if low.startswith("b64:"):
        return True
    if low.startswith("pending_sso") or low in {
        "pending_sso_no_sso",
        "pending_no_pw",
        "need_reregister",
    }:
        # reason field, not a token at all
        return False
    # decoded JSON with mailbox OAuth shape
    data = _try_b64_json_blob(text)
    if isinstance(data, dict):
        keys = {str(k).lower() for k in data.keys()}
        mailish = bool(
            ("access_token" in keys or "accesstoken" in keys)
            and ("refresh_token" in keys or "refreshtoken" in keys)
        )
        # Outlook Graph / device mail tokens
        if mailish and "session_id" not in keys and "config" not in keys:
            return True
        if "client_id" in keys and ("refresh_token" in keys or "access_token" in keys):
            if "session_id" not in keys:
                return True
    # raw JSON string
    if '"access_token"' in text and '"refresh_token"' in text and "session_id" not in text:
        return True
    return False


def is_wrapper_sso(token: str) -> bool:
    """True if token is set-cookie hop JWT (config.token + success_url), not session sso."""
    if is_mail_token_blob(token):
        return False
    payload = decode_jwt_payload(token)
    if not isinstance(payload, dict):
        return False
    cfg = payload.get("config")
    if not isinstance(cfg, dict):
        return False
    return bool(cfg.get("success_url") and (cfg.get("token") or cfg.get("success_url")))


def is_session_sso(token: str) -> bool:
    """Real xAI session SSO only — never mail_token / wrapper / reason strings."""
    token = normalize_sso_token(token)
    if not token or len(token) < 40:
        return False
    if is_mail_token_blob(token):
        return False
    if is_wrapper_sso(token):
        return False
    # pending reason strings
    low = token.lower()
    if low.startswith("pending_") or low.startswith("need_") or low.startswith("auth_error"):
        return False
    if token.count(".") != 2:
        return False
    payload = decode_jwt_payload(token)
    if not isinstance(payload, dict):
        return False
    if "session_id" in payload:
        return True
    # historical session tokens often ~150 chars and start with eyJ0eXAi
    if token.startswith("eyJ0eXAi") and ("session" in payload or "user" in payload or "user_id" in payload):
        return True
    # any non-wrapper JWT of moderate length without mail/oauth noise
    if 40 <= len(token) <= 800 and "config" not in payload:
        mail_keys = {"access_token", "refresh_token", "client_id", "email"}
        if mail_keys.intersection(payload.keys()) and "session_id" not in payload:
            return False
        return True
    return False


def classify_token_field(raw: str) -> str:
    """Return one of: empty | session_sso | wrapper_sso | mail_token | reason | other."""
    text = str(raw or "").strip()
    if not text:
        return "empty"
    if is_mail_token_blob(text):
        return "mail_token"
    low = text.lower()
    if low.startswith("pending_") or low.startswith("need_") or low in {
        "bad_password",
        "account_missing",
        "auth_error",
        "timeout_no_sso",
    }:
        return "reason"
    if is_wrapper_sso(text):
        return "wrapper_sso"
    if is_session_sso(text):
        return "session_sso"
    return "other"


def pick_session_sso_from_parts(parts: list[str]) -> str:
    """From email----password----... parts, return first field that is session SSO."""
    for part in parts[2:]:
        kind = classify_token_field(part)
        if kind == "session_sso":
            return normalize_sso_token(part)
    return ""


def pick_mail_token_from_parts(parts: list[str]) -> str:
    """From pending row parts, return mail_token blob if present."""
    for part in reversed(parts[2:]):
        if is_mail_token_blob(part):
            return str(part).strip()
    return ""


def unwrap_success_url(token: str) -> str:
    payload = decode_jwt_payload(token)
    if not isinstance(payload, dict):
        return ""
    cfg = payload.get("config") or {}
    return str(cfg.get("success_url") or "").strip()


def materialize_sso_via_browser(page: Any, wrapper_or_sso: str, log=None, timeout: float = 45.0) -> str:
    """Use live Chromium tab to follow set-cookie chain and return session sso."""
    import time

    log = log or (lambda _m: None)
    token = (wrapper_or_sso or "").strip()
    if not token:
        return ""
    if is_session_sso(token) and not is_wrapper_sso(token):
        return token

    success = unwrap_success_url(token) if is_wrapper_sso(token) else ""
    t0 = time.time()
    log(f"[sso] stage=inject wrapper_len={len(token)} has_success_url={bool(success)}")
    # inject cookie then open success or accounts
    try:
        page.run_js(
            """
const v = String(arguments[0] || '');
if (!v) return false;
document.cookie = 'sso=' + v + '; path=/; domain=.x.ai; Secure; SameSite=Lax';
document.cookie = 'sso-rw=' + v + '; path=/; domain=.x.ai; Secure; SameSite=Lax';
return true;
            """,
            token,
        )
        log(f"[sso] stage=inject_ok elapsed={time.time()-t0:.1f}s")
    except Exception as e:
        log(f"[sso] stage=inject_fail err={e}")

    urls = []
    if success:
        urls.append(success)
    urls.append("https://accounts.x.ai/")
    urls.append("https://grok.com/")

    deadline = time.time() + timeout
    for idx, url in enumerate(urls):
        if time.time() >= deadline:
            log(f"[sso] stage=deadline before url#{idx} elapsed={time.time()-t0:.1f}s")
            break
        log(f"[sso] stage=navigate#{idx} url={url[:80]} elapsed={time.time()-t0:.1f}s")
        try:
            try:
                page.get(url, timeout=min(20, max(8, int(deadline - time.time()))))
            except TypeError:
                page.get(url)
            time.sleep(0.8)
        except Exception as e:
            log(f"[sso] stage=navigate_fail#{idx} url={url[:60]} err={e}")
            continue
        # poll cookies
        for poll_i in range(8):
            if time.time() >= deadline:
                break
            try:
                cookies = page.cookies(all_domains=True, all_info=True) or page.cookies() or []
            except Exception:
                cookies = []
            for item in cookies:
                if isinstance(item, dict):
                    name = str(item.get("name") or "")
                    value = str(item.get("value") or "")
                else:
                    name = str(getattr(item, "name", "") or "")
                    value = str(getattr(item, "value", "") or "")
                if name == "sso" and value and is_session_sso(value):
                    log(
                        f"[sso] stage=session_ok len={len(value)} via=nav#{idx} "
                        f"poll={poll_i} elapsed={time.time()-t0:.1f}s"
                    )
                    return value
            time.sleep(0.4)
        log(f"[sso] stage=nav_done#{idx} no_session_yet elapsed={time.time()-t0:.1f}s")

    # last try: read any sso even if still wrapper
    try:
        cookies = page.cookies(all_domains=True, all_info=True) or []
        for item in cookies:
            if isinstance(item, dict) and item.get("name") == "sso" and item.get("value"):
                return str(item.get("value"))
    except Exception:
        pass
    return token if is_session_sso(token) else ""


def materialize_sso_via_http(
    wrapper: str,
    *,
    proxy: str = "",
    extra_cookies: Optional[dict] = None,
    log=None,
    timeout: float = 30.0,
) -> str:
    """Best-effort pure HTTP exchange (often needs fresh CF cookies)."""
    log = log or (lambda _m: None)
    if not is_wrapper_sso(wrapper):
        return wrapper if is_session_sso(wrapper) else ""
    try:
        from curl_cffi import requests as cf
    except Exception as e:
        log(f"[sso] curl_cffi missing: {e}")
        return ""

    success = unwrap_success_url(wrapper)
    if not success:
        return ""
    s = cf.Session()
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    for name, value in (extra_cookies or {}).items():
        if not name or value is None:
            continue
        for d in (".x.ai", "accounts.x.ai", "auth.x.ai", ".grok.com"):
            try:
                s.cookies.set(str(name), str(value), domain=d)
            except Exception:
                pass
    for d in (".x.ai", "accounts.x.ai"):
        try:
            s.cookies.set("sso", wrapper, domain=d)
            s.cookies.set("sso-rw", wrapper, domain=d)
        except Exception:
            pass

    url = success
    for hop in range(8):
        try:
            r = s.get(url, impersonate="chrome131", timeout=timeout, allow_redirects=True)
        except TypeError:
            r = s.get(url, timeout=timeout, allow_redirects=True)
        except Exception as e:
            log(f"[sso] hop {hop} fail: {e}")
            break
        # inspect jar for short session sso
        try:
            for c in s.cookies.jar:
                if c.name == "sso" and c.value and is_session_sso(c.value):
                    log(f"[sso] http materialize len={len(c.value)}")
                    return c.value
        except Exception:
            jar = {}
            try:
                jar = dict(s.cookies)
            except Exception:
                pass
            for name in ("sso", "sso-rw"):
                v = jar.get(name) or ""
                if is_session_sso(v):
                    return v
        final = getattr(r, "url", "") or ""
        if "sign-in" in final or "auth-error" in final:
            log(f"[sso] http landed {final[:100]}")
            break
        # follow nested success_url if still wrapper in location/body
        m = re.search(r"https://auth\.[^\s\"']+set-cookie\?q=[^\s\"']+", getattr(r, "text", "") or "")
        if m:
            url = m.group(0)
            continue
        break
    return ""
