# -*- coding: utf-8 -*-
"""
Public temporary-email providers for grok-regkit.

Changelog:
- 2026-07-17 v1: Integrate temp-mail.io / linshiyouxiang / boomlify / temp-mail.org
  into the existing email_provider switch. Each provider returns (address, token)
  from create, and poll helpers extract verification codes.
- 2026-07-17 v2: Add heartbeat logs every ~15s while waiting for verification codes
  so UI/Web does not look stuck; improve timeout errors with provider+email;
  support cancel during wait (already had cancel_callback, now more visible).
- 2026-07-17 v3: Survey + integrate more public temp mails that pass live smoke:
  mail.tm (mailtm), tempmail.lol v2, tempmail.plus (mailto.plus free inbox).
  Documented other candidates and live status in docs/public-temp-email-catalog.md.
"""

from __future__ import annotations

import json
import re
import secrets
import string
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote

import requests

LogCb = Optional[Callable[[str], None]]
CancelCb = Optional[Callable[[], bool]]

TEMPMAIL_IO_BASE = "https://api.internal.temp-mail.io/api/v3"
LINSHI_BASE = "https://www.linshiyouxiang.net"
BOOMLIFY_BASE = "https://v1.boomlify.com"
MAILTM_BASE = "https://api.mail.tm"
TEMPMAIL_LOL_BASE = "https://api.tempmail.lol"
TEMPMAIL_PLUS_BASE = "https://tempmail.plus/api"
TEMPMAIL_ORG_CANDIDATES = (
    "https://web2.temp-mail.org",
    "https://api2.temp-mail.org",
    "https://api.temp-mail.org",
)

# Boomlify transport XOR keyring (public frontend constants)
_BOOMLIFY_DEFAULT_KEY = "7a9b3c8d2e1f4g5h6i9j0k8l2m4n6o8p"
_BOOMLIFY_KEYRING = {
    "hgjfh": "rk4kA9fQm8v7W4d2TzX1Y",
    "hgjfhg": "t2PzKd9sQw1Lm3XyVbN6R",
    "hihji": "bV7nL2cMzR6eJ8QaHp39T",
    "guyg": "oP6yT1xHaE9qD4KsLi82M",
    "ojigh": "mQ3wN8sRcK5tY2VhUe74Z",
    "igug": "Za1sX9qWe3rT7yUiPl56K",
    "fyv": "Hv4kM2nBq8sR1tJcLz93F",
    "vy": "Qs7nF3bLk1pV8xTdRm64G",
    "gyvg": "Nc5wZ1tQe9yH2rLaKs78D",
    "gjbjb": "Lf8pC6sWd3vX1qTuMz40S",
    "zqplk": "Tx9vK3dRm5nP2sLaQw71E",
    "nmxas": "Rj6mV4qTe8yN1bLcPw53C",
    "rtuwq": "Uw2nZ7sQa4tK9pLeMr86B",
    "bchdk": "Ky3pT5nWv7rQ1mLaZx68A",
    "czmop": "De9fR2sXq5tM1nLbVw84P",
    "kqvtd": "Gk1nP8rTe3yL6mQaZw59J",
    "prxnl": "Bn7qL4tWe2rP9mXsVd61H",
    "svyud": "Hp5mN2qTs8yR1lKaVw73U",
    "tjbqw": "Lm6tQ3nWp9rV2sXeYk45I",
    "wmzlk": "Vb8rP4tQe1mS7nKxZa62O",
    "ydnfc": "Cf2mH7vQp6tN9sLxRw83Y",
    "aejru": "Jq4nT6zWe5rM8vPaLs71X",
    "bpvhs": "Rd3pK9sTe2yN7mQwVb64Z",
    "cltqg": "Wu5sL2nQe8rT1yPaMx93C",
    "pqlmn": "Ep7mV1qRs6tN4xLbYz82D",
    "vtycx": "Ha9tQ2mWe5rP8nXsLv61F",
    "wzufr": "Nk8rS3pTe1yM6wQvZa75G",
    "kdjsh": "Zt4mP7nQw3rS6xLeVy82H",
    "qwert": "Oy6nR5mTe2pL9qXsWa34J",
    "yuiop": "Px1vK8tQe4mN7sLaRw53K",
    "asdfg": "Sm2nL9qTe5rV8pXaZw61M",
    "hklop": "Yd3pM6tQw7nR2sLeVk84N",
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _log(cb: LogCb, msg: str) -> None:
    if cb:
        cb(msg)


def _raise_if_cancelled(cancel_callback: CancelCb) -> None:
    if cancel_callback and cancel_callback():
        raise Exception("操作已取消")


def _sleep(seconds: float, cancel_callback: CancelCb = None) -> None:
    end = time.time() + max(0.0, float(seconds))
    while time.time() < end:
        _raise_if_cancelled(cancel_callback)
        time.sleep(min(0.25, end - time.time()))




def _wait_heartbeat(
    log_callback: LogCb,
    provider: str,
    email: str,
    started: float,
    timeout: int,
    message_count: int,
    last_hb: list,
    interval: float = 15.0,
) -> None:
    """Emit progress every `interval` seconds while polling empty mailboxes."""
    now = time.time()
    if not last_hb:
        last_hb.append(started)
    if now - last_hb[0] < interval:
        return
    last_hb[0] = now
    elapsed = int(now - started)
    remaining = max(0, int(timeout - elapsed))
    _log(
        log_callback,
        f"[*] 等待验证码中 provider={provider} email={email} "
        f"elapsed={elapsed}s/{timeout}s remaining~{remaining}s message_count={message_count}",
    )


def _session(proxies: Optional[dict] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
        }
    )
    if proxies:
        s.proxies.update(proxies)
    return s


def _extract_code(text: str, subject: str = "", extract_fn=None) -> Optional[str]:
    if extract_fn:
        code = extract_fn(text, subject)
        if code:
            return code
    if subject:
        m = re.search(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI", subject, re.I)
        if m:
            return m.group(1)
    m = re.search(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", text or "", re.I)
    if m:
        return m.group(1)
    for pat in (
        r"verification\s+code[:\s]+(\d{4,8})",
        r"your\s+code[:\s]+(\d{4,8})",
        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",
        r"\b(\d{6})\b",
    ):
        m = re.search(pat, text or "", re.I)
        if m:
            return m.group(1)
    return None


def _flatten_message(item: Any) -> Tuple[str, str, str]:
    if not isinstance(item, dict):
        return "", "", str(item or "")
    msg_id = str(
        item.get("id")
        or item.get("_id")
        or item.get("Code")
        or item.get("code")
        or item.get("mail_id")
        or item.get("message_id")
        or ""
    )
    subject = str(
        item.get("subject")
        or item.get("Subject")
        or item.get("title")
        or item.get("mail_subject")
        or ""
    )
    parts = [
        subject,
        str(item.get("body_text") or item.get("bodyText") or item.get("text") or ""),
        str(item.get("body_html") or item.get("bodyHtml") or item.get("html") or ""),
        str(item.get("body") or item.get("content") or item.get("intro") or ""),
        str(item.get("textBody") or item.get("htmlBody") or ""),
        str(item.get("preview") or item.get("snippet") or ""),
        json.dumps(item, ensure_ascii=False),
    ]
    return msg_id, subject, "\n".join(p for p in parts if p)


def _token_pack(provider: str, **kwargs) -> str:
    payload = {"p": provider}
    payload.update(kwargs)
    return "json:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _token_unpack(token: str) -> Dict[str, Any]:
    raw = str(token or "")
    if raw.startswith("json:"):
        return json.loads(raw[5:])
    return {"raw": raw}


# ---------------- temp-mail.io ----------------


def tempmail_io_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://temp-mail.io",
            "Referer": "https://temp-mail.io/",
            "Content-Type": "application/json",
        }
    )
    resp = s.post(
        f"{TEMPMAIL_IO_BASE}/email/new",
        json={"min_name_length": 10, "max_name_length": 12},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise Exception(f"temp-mail.io 创建邮箱失败 HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    email = str(data.get("email") or "").strip()
    tok = str(data.get("token") or "").strip()
    if not email or not tok:
        raise Exception(f"temp-mail.io 返回异常: {data}")
    _log(log_callback, f"[*] 已创建 temp-mail.io 邮箱: {email}")
    return email, _token_pack("tempmail_io", email=email, token=tok)


def tempmail_io_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    info = _token_unpack(token)
    email = info.get("email") or ""
    api_token = info.get("token") or info.get("raw") or ""
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://temp-mail.io",
            "Referer": "https://temp-mail.io/",
            "Authorization": f"Bearer {api_token}",
        }
    )
    resp = s.get(f"{TEMPMAIL_IO_BASE}/email/{email}/messages", timeout=30)
    if resp.status_code >= 400:
        raise Exception(f"temp-mail.io 拉信失败 HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("messages", "mails", "data", "items"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def tempmail_io_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    deadline = started + timeout
    seen = set()
    last_hb: list = []
    _log(log_callback, f"[*] 开始轮询验证码 provider=tempmail_io email={email} timeout={timeout}s")
    while time.time() < deadline:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = tempmail_io_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[Debug] temp-mail.io 拉信失败: {exc}")
            messages = []
        for item in messages:
            msg_id, subject, combined = _flatten_message(item)
            key = msg_id or combined[:80]
            if key in seen:
                continue
            seen.add(key)
            _log(log_callback, f"[Debug] temp-mail.io 收到邮件: {subject or '(no subject)'}")
            code = _extract_code(combined, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[*] temp-mail.io 提取到验证码: {code}")
                return code
        _wait_heartbeat(log_callback, "tempmail_io", email, started, timeout, len(seen), last_hb)
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"temp-mail.io 在 {timeout}s 内未收到验证码邮件 email={email}（公共临时域可能被 xAI 拒投，可换 duckmail/yyds/cloudflare）")


# ---------------- linshiyouxiang.net ----------------


def linshi_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    s = _session(proxies)
    s.headers.update(
        {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{LINSHI_BASE}/",
        }
    )
    resp = s.get(f"{LINSHI_BASE}/", timeout=30)
    if resp.status_code >= 400:
        raise Exception(f"临时邮箱.net 打开首页失败 HTTP {resp.status_code}")
    html = resp.text or ""
    email = ""
    code = ""
    m = re.search(r"const\s+activeMail\s*=\s*'([^']+)'", html)
    if m:
        email = m.group(1).strip()
    m = re.search(r"const\s+activeMailCode\s*=\s*'([^']+)'", html)
    if m:
        code = m.group(1).strip()
    if not email:
        for c in s.cookies:
            if c.name == "temp_mail" and c.value:
                email = unquote(c.value)
                break
    if not email or not code:
        raise Exception("临时邮箱.net 未返回可用邮箱/校验码（可能触发人机验证）")
    cookies = requests.utils.dict_from_cookiejar(s.cookies)
    _log(log_callback, f"[*] 已创建 临时邮箱.net 邮箱: {email}")
    return email, _token_pack(
        "linshiyouxiang",
        email=email,
        code=code,
        cookies=cookies,
    )


def linshi_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    info = _token_unpack(token)
    email = info.get("email") or ""
    code = info.get("code") or ""
    cookies = info.get("cookies") or {}
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": LINSHI_BASE,
            "Referer": f"{LINSHI_BASE}/",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    if cookies:
        s.cookies.update(cookies)
    resp = s.post(
        f"{LINSHI_BASE}/get-messages",
        json={"email": email, "code": code},
        timeout=30,
    )
    if resp.status_code == 429:
        raise Exception("临时邮箱.net 触发频率限制/验证码，请稍后再试或换 provider")
    if resp.status_code >= 400:
        raise Exception(f"临时邮箱.net 拉信失败 HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"临时邮箱.net 拉信非 JSON: {resp.text[:200]}")
    if isinstance(data, dict) and data.get("need_captcha"):
        raise Exception("临时邮箱.net 需要完成人机验证后才能继续拉信")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "messages", "mails", "list", "items"):
            if isinstance(data.get(k), list):
                return data[k]
        if data.get("success") is False and not data.get("data"):
            return []
    return []


def linshi_get_message_body(
    token: str, message_code: str, proxies: Optional[dict] = None
) -> str:
    info = _token_unpack(token)
    cookies = info.get("cookies") or {}
    s = _session(proxies)
    s.headers.update({"Referer": f"{LINSHI_BASE}/", "Accept": "text/html,*/*"})
    if cookies:
        s.cookies.update(cookies)
    # common view paths
    for url in (
        f"{LINSHI_BASE}/mail/view/{message_code}",
        f"{LINSHI_BASE}/mail/view/{message_code}?lang=zh",
    ):
        try:
            resp = s.get(url, timeout=30)
            if resp.status_code < 400 and resp.text:
                return resp.text
        except Exception:
            continue
    return ""


def linshi_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    deadline = started + timeout
    seen = set()
    last_hb: list = []
    _log(log_callback, f"[*] 开始轮询验证码 provider=linshiyouxiang email={email} timeout={timeout}s")
    while time.time() < deadline:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = linshi_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[Debug] 临时邮箱.net 拉信失败: {exc}")
            messages = []
        for item in messages:
            msg_id, subject, combined = _flatten_message(item)
            code_key = str(
                item.get("Code")
                or item.get("code")
                or item.get("id")
                or msg_id
                or ""
            )
            key = code_key or combined[:80]
            if key in seen:
                continue
            seen.add(key)
            body = ""
            if code_key:
                try:
                    body = linshi_get_message_body(token, code_key, proxies=proxies)
                except Exception as exc:
                    _log(log_callback, f"[Debug] 临时邮箱.net 读信失败: {exc}")
            combined2 = combined + "\n" + body
            _log(log_callback, f"[Debug] 临时邮箱.net 收到邮件: {subject or '(no subject)'}")
            code = _extract_code(combined2, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[*] 临时邮箱.net 提取到验证码: {code}")
                return code
        _wait_heartbeat(log_callback, "linshiyouxiang", email, started, timeout, len(seen), last_hb)
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"临时邮箱.net 在 {timeout}s 内未收到验证码邮件 email={email}（公共临时域可能被 xAI 拒投，可换 duckmail/yyds/cloudflare）")


# ---------------- boomlify.com ----------------


def _boomlify_xor_decrypt(hex_cipher: str, key_string: str) -> str:
    raw = bytes.fromhex(hex_cipher)
    key = key_string.encode("utf-8")
    out = bytearray(len(raw))
    for i, b in enumerate(raw):
        out[i] = b ^ key[i % len(key)]
    return out.decode("utf-8", errors="replace")


def _boomlify_decode(resp: requests.Response) -> Any:
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"Boomlify 非 JSON 响应 HTTP {resp.status_code}: {resp.text[:200]}")
    if not isinstance(data, dict) or "encrypted" not in data:
        return data
    kid = resp.headers.get("x-enc-key-id") or resp.headers.get("X-Enc-Key-Id") or ""
    key = _BOOMLIFY_KEYRING.get(kid, _BOOMLIFY_DEFAULT_KEY)
    plain = _boomlify_xor_decrypt(str(data["encrypted"]), key)
    try:
        return json.loads(plain)
    except Exception:
        return plain


def boomlify_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://boomlify.com",
            "Referer": "https://boomlify.com/",
            "Content-Type": "application/json",
        }
    )
    init_resp = s.post(f"{BOOMLIFY_BASE}/guest/init", json={}, timeout=30)
    if init_resp.status_code >= 400:
        raise Exception(f"Boomlify guest/init 失败 HTTP {init_resp.status_code}: {init_resp.text[:200]}")
    init_data = _boomlify_decode(init_resp)
    if not isinstance(init_data, dict) or not init_data.get("token"):
        raise Exception(f"Boomlify guest/init 返回异常: {init_data}")
    jwt = str(init_data["token"])
    if init_data.get("guestFirstMailboxCaptchaEnabled"):
        _log(log_callback, "[!] Boomlify 要求首次建箱验证码，若创建失败请稍后再试")

    dom_resp = s.get(f"{BOOMLIFY_BASE}/domains/public", timeout=30)
    if dom_resp.status_code >= 400:
        raise Exception(f"Boomlify 获取域名失败 HTTP {dom_resp.status_code}")
    domains_raw = _boomlify_decode(dom_resp)
    domains: List[dict] = []
    if isinstance(domains_raw, list):
        domains = [d for d in domains_raw if isinstance(d, dict)]
    elif isinstance(domains_raw, dict):
        for k in ("data", "domains", "items"):
            if isinstance(domains_raw.get(k), list):
                domains = [d for d in domains_raw[k] if isinstance(d, dict)]
                break
    free = [
        d
        for d in domains
        if d.get("domain")
        and int(d.get("is_active", 1) or 0) == 1
        and int(d.get("is_premium", 0) or 0) == 0
    ]
    if not free and domains:
        free = domains
    if not free:
        raise Exception("Boomlify 没有可用公共域名")
    domain_obj = free[0]
    domain = str(domain_obj.get("domain"))
    domain_id = domain_obj.get("id")
    username = "u" + secrets.token_hex(4)
    email = f"{username}@{domain}"
    payload = {"email": email, "domainId": domain_id, "domain": domain, "isCustom": False}
    headers = {"Authorization": f"Bearer {jwt}"}
    create_resp = s.post(
        f"{BOOMLIFY_BASE}/emails/create",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if create_resp.status_code >= 400:
        # fallback public create
        create_resp = s.post(
            f"{BOOMLIFY_BASE}/emails/public/create",
            json={"email": email, "domain": domain, "domainId": domain_id},
            headers=headers,
            timeout=30,
        )
    if create_resp.status_code >= 400:
        try:
            err = _boomlify_decode(create_resp)
        except Exception:
            err = create_resp.text[:240]
        err_s = json.dumps(err, ensure_ascii=False) if not isinstance(err, str) else err
        if "CAPTCHA" in err_s.upper() or "captcha" in err_s:
            raise Exception(
                "Boomlify 触发人机验证/频率限制，请稍后再试，或改用 temp-mail.io"
            )
        raise Exception(f"Boomlify 创建邮箱失败 HTTP {create_resp.status_code}: {err_s[:240]}")
    created = _boomlify_decode(create_resp)
    if isinstance(created, dict):
        email = str(
            created.get("email")
            or created.get("address")
            or (created.get("data") or {}).get("email")
            or email
        )
        email_id = str(
            created.get("id")
            or (created.get("data") or {}).get("id")
            or ""
        )
    else:
        email_id = ""
    _log(log_callback, f"[*] 已创建 Boomlify 邮箱: {email}")
    return email, _token_pack(
        "boomlify",
        email=email,
        token=jwt,
        email_id=email_id,
    )


def boomlify_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    info = _token_unpack(token)
    jwt = info.get("token") or ""
    email_id = info.get("email_id") or ""
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://boomlify.com",
            "Referer": "https://boomlify.com/",
            "Authorization": f"Bearer {jwt}",
        }
    )
    urls = [f"{BOOMLIFY_BASE}/messages"]
    if email_id:
        urls.extend(
            [
                f"{BOOMLIFY_BASE}/emails/{email_id}/messages",
                f"{BOOMLIFY_BASE}/api/v1/emails/{email_id}/messages",
            ]
        )
    last_err = None
    for url in urls:
        try:
            resp = s.get(url, timeout=30)
            if resp.status_code >= 400:
                last_err = f"HTTP {resp.status_code}: {resp.text[:160]}"
                continue
            data = _boomlify_decode(resp)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                for k in ("messages", "data", "emails", "items"):
                    if isinstance(data.get(k), list):
                        return [x for x in data[k] if isinstance(x, dict)]
            return []
        except Exception as exc:
            last_err = str(exc)
            continue
    if last_err:
        raise Exception(f"Boomlify 拉信失败: {last_err}")
    return []


def boomlify_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    deadline = started + timeout
    seen = set()
    last_hb: list = []
    _log(log_callback, f"[*] 开始轮询验证码 provider=boomlify email={email} timeout={timeout}s")
    while time.time() < deadline:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = boomlify_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[Debug] Boomlify 拉信失败: {exc}")
            messages = []
        for item in messages:
            msg_id, subject, combined = _flatten_message(item)
            key = msg_id or combined[:80]
            if key in seen:
                continue
            seen.add(key)
            _log(log_callback, f"[Debug] Boomlify 收到邮件: {subject or '(no subject)'}")
            code = _extract_code(combined, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[*] Boomlify 提取到验证码: {code}")
                return code
        _wait_heartbeat(log_callback, "boomlify", email, started, timeout, len(seen), last_hb)
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"Boomlify 在 {timeout}s 内未收到验证码邮件 email={email}（公共临时域可能被 xAI 拒投，可换 duckmail/yyds/cloudflare）")


# ---------------- temp-mail.org (best-effort) ----------------


def tempmail_org_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    """
    temp-mail.org 网页端常被 Cloudflare 拦截。
    优先尝试 web2/api2 建箱；失败时给出明确错误。
    """
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://temp-mail.org",
            "Referer": "https://temp-mail.org/",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    errors = []
    for base in TEMPMAIL_ORG_CANDIDATES:
        for path, method, body in (
            ("/mailbox", "POST", {}),
            ("/request/mailbox/create", "POST", {}),
            ("/request/domains/format/json", "GET", None),
        ):
            url = base.rstrip("/") + path
            try:
                if method == "POST":
                    resp = s.post(url, json=body, timeout=20)
                else:
                    resp = s.get(url, timeout=20)
                if resp.status_code >= 400:
                    errors.append(f"{url} HTTP {resp.status_code}")
                    continue
                # domain list only - then synthesize not possible without create
                ctype = (resp.headers.get("content-type") or "").lower()
                if "json" not in ctype and not resp.text.strip().startswith(("{", "[")):
                    errors.append(f"{url} non-json")
                    continue
                data = resp.json()
                email = ""
                tok = ""
                if isinstance(data, dict):
                    email = str(
                        data.get("email")
                        or data.get("mailbox")
                        or data.get("address")
                        or data.get("mail")
                        or ""
                    )
                    tok = str(
                        data.get("token")
                        or data.get("mailbox")
                        or data.get("email")
                        or data.get("secret")
                        or ""
                    )
                if email and "@" in email:
                    _log(log_callback, f"[*] 已创建 temp-mail.org 邮箱: {email}")
                    return email, _token_pack(
                        "tempmail_org",
                        email=email,
                        token=tok or email,
                        base=base,
                    )
                errors.append(f"{url} unexpected payload")
            except Exception as exc:
                errors.append(f"{url} {exc}")
                continue
    raise Exception(
        "temp-mail.org 当前无法直连建箱（多半被 Cloudflare/风控拦截）。"
        "建议改用 temp-mail.io / Boomlify / 临时邮箱.net。"
        f" 详情: {'; '.join(errors[:4])}"
    )


def tempmail_org_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    info = _token_unpack(token)
    email = info.get("email") or ""
    base = info.get("base") or TEMPMAIL_ORG_CANDIDATES[0]
    api_token = info.get("token") or email
    s = _session(proxies)
    s.headers.update(
        {
            "Origin": "https://temp-mail.org",
            "Referer": "https://temp-mail.org/",
            "Accept": "application/json",
        }
    )
    candidates = [
        f"{base}/messages",
        f"{base}/mailbox/{api_token}",
        f"{base}/request/mail/id/{api_token}/format/json",
        f"{base}/request/mail/id/{email}/format/json",
    ]
    for url in candidates:
        try:
            resp = s.get(url, timeout=20)
            if resp.status_code >= 400:
                continue
            data = resp.json()
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                for k in ("messages", "mail", "mails", "data"):
                    if isinstance(data.get(k), list):
                        return [x for x in data[k] if isinstance(x, dict)]
        except Exception:
            continue
    return []


def tempmail_org_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    deadline = started + timeout
    seen = set()
    last_hb: list = []
    _log(log_callback, f"[*] 开始轮询验证码 provider=tempmail_org email={email} timeout={timeout}s")
    while time.time() < deadline:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = tempmail_org_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[Debug] temp-mail.org 拉信失败: {exc}")
            messages = []
        for item in messages:
            msg_id, subject, combined = _flatten_message(item)
            key = msg_id or combined[:80]
            if key in seen:
                continue
            seen.add(key)
            _log(log_callback, f"[Debug] temp-mail.org 收到邮件: {subject or '(no subject)'}")
            code = _extract_code(combined, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[*] temp-mail.org 提取到验证码: {code}")
                return code
        _wait_heartbeat(log_callback, "tempmail_org", email, started, timeout, len(seen), last_hb)
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"temp-mail.org 在 {timeout}s 内未收到验证码邮件 email={email}（公共临时域可能被 xAI 拒投，可换 duckmail/yyds/cloudflare）")


# ---------------- dispatcher ----------------


# ---------------------------------------------------------------------------
# mail.tm  (public, no key)
# docs: GET /domains, POST /accounts, POST /token, GET /messages
# ---------------------------------------------------------------------------


def mailtm_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    s = _session(proxies)
    r = s.get(f"{MAILTM_BASE}/domains", timeout=25)
    if r.status_code >= 400:
        raise Exception(f"mail.tm domains HTTP {r.status_code}: {r.text[:200]}")
    data = r.json() if r.content else {}
    members = data.get("hydra:member") or data.get("member") or []
    if not members:
        raise Exception("mail.tm 无可用域名")
    domain = str(members[0].get("domain") or "").strip()
    if not domain:
        raise Exception("mail.tm 域名字段为空")
    local = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
    address = f"{local}@{domain}"
    password = secrets.token_urlsafe(12)
    r2 = s.post(
        f"{MAILTM_BASE}/accounts",
        json={"address": address, "password": password},
        timeout=25,
    )
    if r2.status_code not in (200, 201):
        raise Exception(f"mail.tm create account HTTP {r2.status_code}: {r2.text[:200]}")
    r3 = s.post(
        f"{MAILTM_BASE}/token",
        json={"address": address, "password": password},
        timeout=25,
    )
    if r3.status_code >= 400:
        raise Exception(f"mail.tm token HTTP {r3.status_code}: {r3.text[:200]}")
    token_jwt = str((r3.json() or {}).get("token") or "").strip()
    if not token_jwt:
        raise Exception("mail.tm token 为空")
    _log(log_callback, f"[+] mail.tm 建箱成功: {address}")
    return address, _token_pack("mailtm", jwt=token_jwt, password=password, address=address)


def mailtm_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    pack = _token_unpack(token)
    jwt = pack.get("jwt") or token
    s = _session(proxies)
    s.headers["Authorization"] = f"Bearer {jwt}"
    r = s.get(f"{MAILTM_BASE}/messages", timeout=25)
    if r.status_code >= 400:
        raise Exception(f"mail.tm messages HTTP {r.status_code}: {r.text[:200]}")
    data = r.json() if r.content else {}
    return list(data.get("hydra:member") or data.get("member") or [])


def mailtm_message_body(msg_id: str, token: str, proxies: Optional[dict] = None) -> str:
    pack = _token_unpack(token)
    jwt = pack.get("jwt") or token
    s = _session(proxies)
    s.headers["Authorization"] = f"Bearer {jwt}"
    r = s.get(f"{MAILTM_BASE}/messages/{msg_id}", timeout=25)
    if r.status_code >= 400:
        return ""
    item = r.json() if r.content else {}
    _, subject, blob = _flatten_message(item)
    return f"{subject}\n{blob}"


def mailtm_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    last_hb: list = []
    seen = set()
    while time.time() - started < timeout:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = mailtm_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[!] mail.tm 拉信失败: {exc}")
            messages = []
        _wait_heartbeat(log_callback, "mailtm", email, started, timeout, len(messages), last_hb)
        for item in messages:
            msg_id, subject, blob = _flatten_message(item)
            if msg_id and msg_id in seen:
                continue
            if msg_id:
                seen.add(msg_id)
            body = blob
            if msg_id:
                extra = mailtm_message_body(msg_id, token, proxies=proxies)
                if extra:
                    body = body + "\n" + extra
            code = _extract_code(body, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[+] mail.tm 取到验证码: {code}")
                return code
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"等待验证码超时 provider=mailtm email={email} timeout={timeout}s")


# ---------------------------------------------------------------------------
# tempmail.lol v2  (public, no key)
# POST /v2/inbox/create -> {address, token}
# GET  /v2/inbox?token=...
# ---------------------------------------------------------------------------


def tempmail_lol_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    s = _session(proxies)
    r = s.post(f"{TEMPMAIL_LOL_BASE}/v2/inbox/create", json={}, timeout=25)
    if r.status_code not in (200, 201):
        # fallback v1 generate
        r = s.get(f"{TEMPMAIL_LOL_BASE}/generate", timeout=25)
        if r.status_code >= 400:
            raise Exception(f"tempmail.lol create HTTP {r.status_code}: {r.text[:200]}")
    data = r.json() if r.content else {}
    address = str(data.get("address") or data.get("email") or "").strip()
    tok = str(data.get("token") or "").strip()
    if not address or not tok:
        raise Exception(f"tempmail.lol 响应缺字段: {str(data)[:200]}")
    _log(log_callback, f"[+] tempmail.lol 建箱成功: {address}")
    return address, _token_pack("tempmail_lol", token=tok, address=address)


def tempmail_lol_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    pack = _token_unpack(token)
    tok = pack.get("token") or token
    s = _session(proxies)
    r = s.get(f"{TEMPMAIL_LOL_BASE}/v2/inbox", params={"token": tok}, timeout=25)
    if r.status_code >= 400:
        # v1 style
        r = s.get(f"{TEMPMAIL_LOL_BASE}/auth/{tok}", timeout=25)
        if r.status_code >= 400:
            raise Exception(f"tempmail.lol inbox HTTP {r.status_code}: {r.text[:200]}")
        data = r.json() if r.content else {}
        emails = data.get("email") or data.get("emails") or data.get("messages") or []
        return list(emails) if isinstance(emails, list) else []
    data = r.json() if r.content else {}
    emails = data.get("emails") or data.get("email") or data.get("messages") or []
    return list(emails) if isinstance(emails, list) else []


def tempmail_lol_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    started = time.time()
    last_hb: list = []
    seen = set()
    while time.time() - started < timeout:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = tempmail_lol_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[!] tempmail.lol 拉信失败: {exc}")
            messages = []
        _wait_heartbeat(log_callback, "tempmail_lol", email, started, timeout, len(messages), last_hb)
        for item in messages:
            msg_id, subject, blob = _flatten_message(item)
            # lol may use body / html / text differently
            if isinstance(item, dict):
                blob = "\n".join(
                    [
                        blob,
                        str(item.get("body") or ""),
                        str(item.get("html") or ""),
                        str(item.get("text") or ""),
                        str(item.get("content") or ""),
                    ]
                )
            key = msg_id or (subject + blob[:80])
            if key in seen:
                continue
            seen.add(key)
            code = _extract_code(blob, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[+] tempmail.lol 取到验证码: {code}")
                return code
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"等待验证码超时 provider=tempmail_lol email={email} timeout={timeout}s")


# ---------------------------------------------------------------------------
# tempmail.plus  (public free inbox, no create API; random local@mailto.plus)
# GET /api/mails?email=...&limit=20
# GET /api/mails/{id}?email=...
# ---------------------------------------------------------------------------


def tempmail_plus_create(proxies: Optional[dict] = None, log_callback: LogCb = None) -> Tuple[str, str]:
    local = "g" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    # common free domains observed: mailto.plus, fexpost.com, fexbox.org, mailbox.in.ua, rover.info, chitthi.in
    domains = [
        "mailto.plus",
        "fexpost.com",
        "fexbox.org",
        "mailbox.in.ua",
        "rover.info",
        "chitthi.in",
        "fextemp.com",
        "any.pink",
    ]
    domain = secrets.choice(domains)
    address = f"{local}@{domain}"
    # probe list endpoint once
    s = _session(proxies)
    r = s.get(f"{TEMPMAIL_PLUS_BASE}/mails", params={"email": address, "limit": 1}, timeout=25)
    if r.status_code >= 400:
        # fallback primary domain
        address = f"{local}@mailto.plus"
        r = s.get(f"{TEMPMAIL_PLUS_BASE}/mails", params={"email": address, "limit": 1}, timeout=25)
        if r.status_code >= 400:
            raise Exception(f"tempmail.plus 建箱探测 HTTP {r.status_code}: {r.text[:200]}")
    _log(log_callback, f"[+] tempmail.plus 建箱成功: {address}")
    return address, _token_pack("tempmail_plus", address=address)


def tempmail_plus_messages(token: str, proxies: Optional[dict] = None) -> List[dict]:
    pack = _token_unpack(token)
    address = pack.get("address") or ""
    if not address:
        raise Exception("tempmail.plus token 缺少 address")
    s = _session(proxies)
    r = s.get(f"{TEMPMAIL_PLUS_BASE}/mails", params={"email": address, "limit": 50}, timeout=25)
    if r.status_code >= 400:
        raise Exception(f"tempmail.plus list HTTP {r.status_code}: {r.text[:200]}")
    data = r.json() if r.content else {}
    return list(data.get("mail_list") or data.get("mails") or [])


def tempmail_plus_message_body(mail_id: str, address: str, proxies: Optional[dict] = None) -> str:
    s = _session(proxies)
    r = s.get(f"{TEMPMAIL_PLUS_BASE}/mails/{mail_id}", params={"email": address}, timeout=25)
    if r.status_code >= 400:
        return ""
    item = r.json() if r.content else {}
    if isinstance(item, dict) and "data" in item and isinstance(item["data"], dict):
        item = item["data"]
    _, subject, blob = _flatten_message(item if isinstance(item, dict) else {})
    return f"{subject}\n{blob}"


def tempmail_plus_get_code(
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    pack = _token_unpack(token)
    address = pack.get("address") or email
    started = time.time()
    last_hb: list = []
    seen = set()
    while time.time() - started < timeout:
        _raise_if_cancelled(cancel_callback)
        try:
            messages = tempmail_plus_messages(token, proxies=proxies)
        except Exception as exc:
            _log(log_callback, f"[!] tempmail.plus 拉信失败: {exc}")
            messages = []
        _wait_heartbeat(log_callback, "tempmail_plus", address, started, timeout, len(messages), last_hb)
        for item in messages:
            msg_id = str(
                item.get("mail_id")
                or item.get("id")
                or item.get("first_id")
                or item.get("message_id")
                or ""
            )
            subject = str(item.get("subject") or item.get("Subject") or "")
            blob = "\n".join(
                [
                    subject,
                    str(item.get("from_mail") or ""),
                    str(item.get("from_name") or ""),
                    str(item.get("summary") or item.get("text") or item.get("preview") or ""),
                ]
            )
            if msg_id and msg_id not in seen:
                seen.add(msg_id)
                extra = tempmail_plus_message_body(msg_id, address, proxies=proxies)
                if extra:
                    blob = blob + "\n" + extra
            elif not msg_id:
                key = subject + blob[:60]
                if key in seen:
                    continue
                seen.add(key)
            code = _extract_code(blob, subject, extract_fn=extract_fn)
            if code:
                _log(log_callback, f"[+] tempmail.plus 取到验证码: {code}")
                return code
        _sleep(poll_interval, cancel_callback)
    raise Exception(f"等待验证码超时 provider=tempmail_plus email={address} timeout={timeout}s")


PUBLIC_PROVIDERS = {
    "tempmail_io": {
        "label": "TempMail.io",
        "create": tempmail_io_create,
        "get_code": tempmail_io_get_code,
    },
    "temp-mail.io": {
        "label": "TempMail.io",
        "create": tempmail_io_create,
        "get_code": tempmail_io_get_code,
    },
    "linshiyouxiang": {
        "label": "临时邮箱.net",
        "create": linshi_create,
        "get_code": linshi_get_code,
    },
    "linshi": {
        "label": "临时邮箱.net",
        "create": linshi_create,
        "get_code": linshi_get_code,
    },
    "boomlify": {
        "label": "Boomlify",
        "create": boomlify_create,
        "get_code": boomlify_get_code,
    },
    "tempmail_org": {
        "label": "TempMail.org",
        "create": tempmail_org_create,
        "get_code": tempmail_org_get_code,
    },
    "temp-mail.org": {
        "label": "TempMail.org",
        "create": tempmail_org_create,
        "get_code": tempmail_org_get_code,
    },
    "mailtm": {
        "label": "Mail.tm",
        "create": mailtm_create,
        "get_code": mailtm_get_code,
    },
    "mail.tm": {
        "label": "Mail.tm",
        "create": mailtm_create,
        "get_code": mailtm_get_code,
    },
    "tempmail_lol": {
        "label": "TempMail.lol",
        "create": tempmail_lol_create,
        "get_code": tempmail_lol_get_code,
    },
    "tempmail.lol": {
        "label": "TempMail.lol",
        "create": tempmail_lol_create,
        "get_code": tempmail_lol_get_code,
    },
    "tempmail_plus": {
        "label": "TempMail.plus",
        "create": tempmail_plus_create,
        "get_code": tempmail_plus_get_code,
    },
    "tempmail.plus": {
        "label": "TempMail.plus",
        "create": tempmail_plus_create,
        "get_code": tempmail_plus_get_code,
    },
}


def is_public_provider(name: str) -> bool:
    return str(name or "").strip().lower() in PUBLIC_PROVIDERS


def create_public_email(
    provider: str,
    proxies: Optional[dict] = None,
    log_callback: LogCb = None,
) -> Tuple[str, str]:
    key = str(provider or "").strip().lower()
    if key not in PUBLIC_PROVIDERS:
        raise Exception(f"未知公共邮箱 provider: {provider}")
    return PUBLIC_PROVIDERS[key]["create"](proxies=proxies, log_callback=log_callback)


def get_public_code(
    provider: str,
    token: str,
    email: str,
    timeout: int = 180,
    poll_interval: int = 3,
    log_callback: LogCb = None,
    cancel_callback: CancelCb = None,
    extract_fn=None,
    proxies: Optional[dict] = None,
) -> str:
    key = str(provider or "").strip().lower()
    if key not in PUBLIC_PROVIDERS:
        raise Exception(f"未知公共邮箱 provider: {provider}")
    return PUBLIC_PROVIDERS[key]["get_code"](
        token,
        email,
        timeout=timeout,
        poll_interval=poll_interval,
        log_callback=log_callback,
        cancel_callback=cancel_callback,
        extract_fn=extract_fn,
        proxies=proxies,
    )


def smoke_test_provider(provider: str, proxies: Optional[dict] = None) -> dict:
    """Create one mailbox and list messages once. Does not register accounts."""
    email, token = create_public_email(provider, proxies=proxies)
    key = str(provider or "").strip().lower()
    messages = []
    try:
        if key in ("tempmail_io", "temp-mail.io"):
            messages = tempmail_io_messages(token, proxies=proxies)
        elif key in ("linshiyouxiang", "linshi"):
            messages = linshi_messages(token, proxies=proxies)
        elif key == "boomlify":
            messages = boomlify_messages(token, proxies=proxies)
        elif key in ("tempmail_org", "temp-mail.org"):
            messages = tempmail_org_messages(token, proxies=proxies)
        elif key in ("mailtm", "mail.tm"):
            messages = mailtm_messages(token, proxies=proxies)
        elif key in ("tempmail_lol", "tempmail.lol"):
            messages = tempmail_lol_messages(token, proxies=proxies)
        elif key in ("tempmail_plus", "tempmail.plus"):
            messages = tempmail_plus_messages(token, proxies=proxies)
    except Exception as exc:
        return {
            "ok": True,
            "provider": key,
            "email": email,
            "messages_error": str(exc),
            "message_count": 0,
        }
    return {
        "ok": True,
        "provider": key,
        "email": email,
        "message_count": len(messages),
    }
