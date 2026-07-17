# -*- coding: utf-8 -*-
"""Outlook / Microsoft personal mailbox provider (password+TOTP or refresh_token).

Account line formats:
1) email----password----totp_secret
2) email----password----totp_secret----client_id
3) email----client_id----refresh_token
4) email----refresh_token
Separators also accept | , or tab.

create/acquire: rent mailbox from pool, ensure access_token
poll_code: Microsoft Graph inbox, extract xAI/Grok code
token cache: outlook_token_cache.json (local, gitignored)
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

import requests

try:
    import pyotp
except Exception:  # pragma: no cover
    pyotp = None  # type: ignore

DEFAULT_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
DEFAULT_REDIRECT = "https://login.microsoftonline.com/common/oauth2/nativeclient"
DEFAULT_SCOPE = "https://graph.microsoft.com/Mail.Read offline_access openid profile"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_POOL_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_POOL = None
_POOL_SIG = ""


def _log(cb, msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _root_dir() -> Path:
    return Path(__file__).resolve().parent


def _now() -> float:
    return time.time()


def _split_account_line(line: str) -> List[str]:
    s = (line or "").strip()
    if not s or s.startswith("#"):
        return []
    for sep in ("----", "|", "\t", ","):
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip() != ""]
    return s.split()


@dataclass
class OutlookAccount:
    email: str
    password: str = ""
    totp_secret: str = ""
    client_id: str = DEFAULT_CLIENT_ID
    refresh_token: str = ""
    access_token: str = ""
    access_expires_at: float = 0.0
    status: str = "idle"
    last_error: str = ""
    last_used_at: float = 0.0
    cooldown_until: float = 0.0
    source_line: str = ""

    def identity(self) -> str:
        return self.email.lower().strip()


def parse_account_line(line: str) -> Optional[OutlookAccount]:
    parts = _split_account_line(line)
    if len(parts) < 2 or "@" not in parts[0]:
        return None
    email = parts[0]
    uuid_re = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    if len(parts) >= 3 and uuid_re.match(parts[1]) and len(parts[2]) > 40:
        return OutlookAccount(email=email, client_id=parts[1], refresh_token=parts[2], source_line=line.strip())
    if len(parts) == 2 and len(parts[1]) > 40 and not uuid_re.match(parts[1]):
        return OutlookAccount(email=email, refresh_token=parts[1], source_line=line.strip())
    if len(parts) >= 3:
        acc = OutlookAccount(
            email=email, password=parts[1], totp_secret=parts[2].replace(" ", ""), source_line=line.strip()
        )
        if len(parts) >= 4 and uuid_re.match(parts[3]):
            acc.client_id = parts[3]
        return acc
    if len(parts) == 2:
        return OutlookAccount(email=email, password=parts[1], source_line=line.strip())
    return None


def load_accounts_from_text(text: str) -> List[OutlookAccount]:
    out, seen = [], set()
    for raw in (text or "").splitlines():
        acc = parse_account_line(raw)
        if not acc or acc.identity() in seen:
            continue
        seen.add(acc.identity())
        out.append(acc)
    return out


def load_accounts_from_file(path: str) -> List[OutlookAccount]:
    p = Path(path)
    if not p.is_file():
        return []
    return load_accounts_from_text(p.read_text(encoding="utf-8", errors="ignore"))


class TokenCache:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or (_root_dir() / "outlook_token_cache.json")
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        with _CACHE_LOCK:
            if self.path.is_file():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}
            else:
                self._data = {}

    def save(self) -> None:
        with _CACHE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, email: str) -> Dict[str, Any]:
        return dict(self._data.get(email.lower(), {}) or {})

    def put(self, email: str, payload: Dict[str, Any]) -> None:
        key = email.lower()
        cur = self._data.get(key, {})
        cur.update(payload)
        cur["updated_at"] = int(_now())
        self._data[key] = cur
        self.save()


class OutlookSession:
    def __init__(self, client_id=DEFAULT_CLIENT_ID, redirect_uri=DEFAULT_REDIRECT, scope=DEFAULT_SCOPE,
                 proxies=None, timeout=30, log_callback=None):
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT
        self.scope = scope or DEFAULT_SCOPE
        self.proxies = proxies
        self.timeout = timeout
        self.log_callback = log_callback
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9",
                               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        if proxies:
            self.s.proxies.update(proxies)

    def _lg(self, msg: str) -> None:
        _log(self.log_callback, msg)

    def _esd(self, html: str) -> dict:
        m = re.search(r"var ServerData = (\{.*?\});", html, re.S)
        if not m:
            m = re.search(r"ServerData\s*=\s*(\{.*?\});", html, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

    def _sft(self, html: str, data: dict) -> str:
        v = data.get("sFT")
        if isinstance(v, str) and v and not v.startswith("<"):
            return v
        tag = data.get("sFTTag") or ""
        m = re.search(r'value="([^"]+)"', tag)
        if m:
            return m.group(1)
        m = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html)
        return m.group(1) if m else ""

    def _title(self, html: str):
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    def _extract_forms(self, html: str) -> List[dict]:
        forms = []
        for fm in re.finditer(r"<form\b([^>]*)>(.*?)</form>", html, re.I | re.S):
            attrs, body = fm.group(1), fm.group(2)
            action_m = re.search(r'action=["\']([^"\']+)["\']', attrs, re.I)
            method_m = re.search(r'method=["\']([^"\']+)["\']', attrs, re.I)
            inputs = {}
            for inp in re.finditer(r"<input\b([^>]*)/?>", body, re.I):
                a = inp.group(1)
                n = re.search(r'name=["\']([^"\']+)["\']', a, re.I)
                v = re.search(r'value=["\']([^"\']*)["\']', a, re.I)
                if n:
                    inputs[n.group(1)] = v.group(1) if v else ""
            forms.append({"action": action_m.group(1) if action_m else "",
                          "method": (method_m.group(1) if method_m else "post").lower(),
                          "inputs": inputs})
        return forms

    def _post_form(self, url: str, data: dict, referer: str):
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "Origin": "https://login.live.com", "Referer": referer}
        return self.s.post(url, data=data, headers=headers, timeout=self.timeout, allow_redirects=True)

    def refresh_access_token(self, refresh_token: str) -> dict:
        self._lg("[*] Outlook OAuth: refresh_token -> access_token")
        r = self.s.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data={
            "client_id": self.client_id, "scope": self.scope, "refresh_token": refresh_token,
            "grant_type": "refresh_token", "redirect_uri": self.redirect_uri,
        }, timeout=self.timeout)
        self._lg(f"[*] Outlook token refresh HTTP {r.status_code}")
        r.raise_for_status()
        data = r.json()
        if not data.get("access_token"):
            raise Exception(f"refresh_token invalid: {data}")
        return data

    def exchange_code(self, code: str) -> dict:
        self._lg("[*] Outlook OAuth: authorization_code -> token")
        r = self.s.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data={
            "client_id": self.client_id, "scope": self.scope, "code": code,
            "redirect_uri": self.redirect_uri, "grant_type": "authorization_code",
        }, timeout=self.timeout)
        self._lg(f"[*] Outlook code exchange HTTP {r.status_code}")
        r.raise_for_status()
        data = r.json()
        if not data.get("access_token"):
            raise Exception(f"code exchange failed: {data}")
        return data

    def login_password_totp(self, email: str, password: str, totp_secret: str) -> dict:
        if not pyotp:
            raise Exception("missing pyotp, run: pip install pyotp")
        if not password:
            raise Exception("Outlook account missing password")
        if not totp_secret:
            raise Exception("Outlook account missing TOTP secret")
        self._lg(f"[*] Outlook form login: {email}")
        self._lg("[*] step1: OAuth authorize -> login.live.com")
        auth = (
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
            f"?client_id={self.client_id}&response_type=code"
            f"&redirect_uri={quote(self.redirect_uri, safe='')}"
            f"&response_mode=query&scope={quote(self.scope, safe='')}"
            f"&login_hint={quote(email)}"
        )
        r = self.s.get(auth, timeout=self.timeout, allow_redirects=True)
        d = self._esd(r.text)
        url_post = d.get("urlPost") or d.get("urlPostMsa") or ""
        sft = self._sft(r.text, d)
        if not url_post or not sft:
            raise Exception("Outlook login page parse failed (urlPost/PPFT)")
        base = {
            "i13": "0", "login": email, "loginfmt": email, "type": "11", "LoginOptions": "3",
            "lrt": "", "lrtPartition": "", "hisRegion": "", "hisScaleUnit": "", "passwd": "",
            "ps": "2", "psRNGCDefaultType": "", "psRNGCEntropy": "", "psRNGCSLK": "",
            "canary": "", "ctx": "", "hpgrequestid": "", "PPFT": sft, "PPSX": "PassportRN",
            "NewUser": "1", "FoundMSAs": "", "fspost": "0", "i21": "0", "CookieDisclosure": "0",
            "IsFidoSupported": "1", "isSignupPost": "0", "isRecoveryAttemptPost": "0", "i19": "241232",
        }
        self._lg("[*] step2: submit email")
        r1 = self._post_form(url_post, base, r.url)
        d1 = self._esd(r1.text)
        if "code=" in r1.url:
            return self.exchange_code(parse_qs(urlparse(r1.url).query)["code"][0])
        self._lg("[*] step3: submit password")
        pl2 = dict(base)
        pl2.update({"passwd": password, "PPFT": self._sft(r1.text, d1) or sft, "i19": "278938"})
        r2 = self._post_form(d1.get("urlPost") or url_post, pl2, r1.url)
        d2 = self._esd(r2.text)
        if "code=" in r2.url:
            return self.exchange_code(parse_qs(urlparse(r2.url).query)["code"][0])
        err = d2.get("sErrTxt") or d2.get("sErrorCode")
        if err and not d2.get("arrUserProofs"):
            raise Exception(f"Outlook password login failed: {err}")
        if not d2.get("arrUserProofs"):
            code = self._follow_to_code(r2)
            if code:
                return self.exchange_code(code)
            raise Exception(f"Outlook did not reach MFA/consent title={self._title(r2.text)}")
        proofs = d2.get("arrUserProofs") or []
        ap = next((p for p in proofs if p.get("type") in (10, 14)), None)
        if not ap:
            ap = next((p for p in proofs if p.get("otcEnabled")), proofs[0])
        field = d2.get("sAuthMethodInputFieldName") or "SentProofIDE"
        totp = pyotp.TOTP(totp_secret.replace(" ", ""))
        otc = totp.now()
        self._lg(f"[*] step4: MFA/TOTP type=19 proof={ap.get('display')} code={otc}")
        pl3 = {
            "login": email, "loginfmt": email, "type": "19", "PPFT": self._sft(r2.text, d2),
            "otc": otc, "AddTD": "true", "i19": "278938", "ProofConfirmation": "",
            field: ap.get("data") or "",
        }
        r3 = self._post_form(d2.get("urlPost") or url_post, pl3, r2.url)
        if "code=" in r3.url:
            return self.exchange_code(parse_qs(urlparse(r3.url).query)["code"][0])
        d3 = self._esd(r3.text)
        if d3.get("sErrTxt"):
            time.sleep(1.2)
            otc2 = totp.now()
            self._lg(f"[*] MFA retry TOTP code={otc2}")
            pl3["otc"] = otc2
            pl3["PPFT"] = self._sft(r3.text, d3) or pl3["PPFT"]
            r3 = self._post_form(d3.get("urlPost") or d2.get("urlPost") or url_post, pl3, r3.url)
            if "code=" in r3.url:
                return self.exchange_code(parse_qs(urlparse(r3.url).query)["code"][0])
            d3 = self._esd(r3.text)
            if d3.get("sErrTxt"):
                raise Exception(f"Outlook MFA/TOTP failed: {d3.get('sErrTxt')}")
        self._lg("[*] step5: follow Continue/Consent to authorization code")
        code = self._follow_to_code(r3)
        if not code:
            raise Exception(f"Outlook login ok but no OAuth code title={self._title(r3.text)}")
        return self.exchange_code(code)

    def _follow_to_code(self, resp, max_steps: int = 12):
        for step in range(max_steps):
            url, html = resp.url, resp.text
            self._lg(f"[*] Outlook redirect step={step} title={self._title(html)} url={url[:140]}")
            qs = parse_qs(urlparse(url).query)
            if qs.get("code"):
                return qs["code"][0]
            forms = self._extract_forms(html)
            chosen = None
            for f in forms:
                if f.get("action") and ("Consent" in f["action"] or "fmHF" in html or "ipt" in f.get("inputs", {}) or "pprid" in f.get("inputs", {})):
                    chosen = f
                    break
            if not chosen and forms:
                chosen = forms[0]
            if not chosen or not chosen.get("action"):
                d = self._esd(html)
                if d.get("urlPost"):
                    pl = {"PPFT": self._sft(html, d), "ucaction": "Yes", "ucaccept": "Yes", "i19": "10000"}
                    resp = self._post_form(d["urlPost"], pl, url)
                    continue
                return None
            action = chosen["action"].replace("&amp;", "&")
            if action.startswith("/"):
                p = urlparse(url)
                action = f"{p.scheme}://{p.netloc}{action}"
            data = dict(chosen.get("inputs") or {})
            if "consent" in action.lower() or "Consent" in action or "Update" in action:
                data.setdefault("ucaction", "Yes")
                data.setdefault("ucaccept", "Yes")
            headers = {"Content-Type": "application/x-www-form-urlencoded", "Referer": url}
            if chosen.get("method") == "get":
                resp = self.s.get(action, params=data, headers=headers, timeout=self.timeout, allow_redirects=True)
            else:
                resp = self.s.post(action, data=data, headers=headers, timeout=self.timeout, allow_redirects=True)
        return None

    def list_inbox(self, access_token: str, top: int = 15) -> List[dict]:
        url = (
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            f"?$top={int(top)}&$orderby=receivedDateTime desc"
            "&$select=id,subject,bodyPreview,body,from,receivedDateTime,isRead"
        )
        r = self.s.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=self.timeout)
        if r.status_code == 401:
            raise Exception("Graph 401: access_token expired")
        r.raise_for_status()
        return list((r.json() or {}).get("value") or [])


class OutlookAccountPool:
    def __init__(self, accounts, cache=None, proxies=None, log_callback=None, client_id=DEFAULT_CLIENT_ID):
        self.accounts = accounts
        self.cache = cache or TokenCache()
        self.proxies = proxies
        self.log_callback = log_callback
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self._idx = 0
        for acc in self.accounts:
            c = self.cache.get(acc.email)
            if c.get("refresh_token") and not acc.refresh_token:
                acc.refresh_token = c.get("refresh_token") or ""
            if c.get("access_token"):
                acc.access_token = c.get("access_token") or ""
                acc.access_expires_at = float(c.get("access_expires_at") or 0)
            if c.get("client_id"):
                acc.client_id = c.get("client_id") or acc.client_id

    def _lg(self, msg: str) -> None:
        _log(self.log_callback, msg)

    def _session(self, acc: OutlookAccount) -> OutlookSession:
        return OutlookSession(client_id=acc.client_id or self.client_id, proxies=self.proxies,
                              log_callback=self.log_callback)

    def ensure_tokens(self, acc: OutlookAccount) -> OutlookAccount:
        if acc.access_token and acc.access_expires_at > _now() + 60:
            self._lg(f"[*] Outlook reuse access_token: {acc.email}")
            return acc
        sess = self._session(acc)
        if acc.refresh_token:
            try:
                data = sess.refresh_access_token(acc.refresh_token)
                acc.access_token = data["access_token"]
                acc.refresh_token = data.get("refresh_token") or acc.refresh_token
                acc.access_expires_at = _now() + int(data.get("expires_in") or 3600)
                self.cache.put(acc.email, {
                    "access_token": acc.access_token, "refresh_token": acc.refresh_token,
                    "access_expires_at": acc.access_expires_at, "client_id": acc.client_id,
                })
                self._lg(f"[+] Outlook refresh ok: {acc.email}")
                return acc
            except Exception as exc:
                self._lg(f"[!] Outlook refresh failed, try password+TOTP: {exc}")
        if acc.password and acc.totp_secret:
            data = sess.login_password_totp(acc.email, acc.password, acc.totp_secret)
            acc.access_token = data["access_token"]
            acc.refresh_token = data.get("refresh_token") or acc.refresh_token
            acc.access_expires_at = _now() + int(data.get("expires_in") or 3600)
            self.cache.put(acc.email, {
                "access_token": acc.access_token, "refresh_token": acc.refresh_token,
                "access_expires_at": acc.access_expires_at, "client_id": acc.client_id,
            })
            self._lg(f"[+] Outlook password+TOTP login ok: {acc.email}")
            return acc
        raise Exception(f"Outlook account {acc.email} has no refresh_token and missing password+totp")

    def acquire(self) -> Tuple[str, str]:
        with _POOL_LOCK:
            if not self.accounts:
                raise Exception("Outlook account pool empty; configure outlook_accounts or file")
            n = len(self.accounts)
            last_err = None
            for i in range(n):
                acc = self.accounts[(self._idx + i) % n]
                if acc.status in ("bad",) or acc.cooldown_until > _now() or acc.status == "in_use":
                    continue
                try:
                    src = "refresh_token" if acc.refresh_token else "password+totp"
                    self._lg(f"[*] Outlook acquire: {acc.email} | pool={n} | auth={src}")
                    self.ensure_tokens(acc)
                    acc.status = "in_use"
                    acc.last_used_at = _now()
                    acc.last_error = ""
                    self._idx = (self._idx + i + 1) % n
                    token_blob = json.dumps({
                        "email": acc.email, "access_token": acc.access_token,
                        "refresh_token": acc.refresh_token, "access_expires_at": acc.access_expires_at,
                        "client_id": acc.client_id, "password": acc.password, "totp_secret": acc.totp_secret,
                    }, ensure_ascii=False)
                    self._lg(f"[+] Outlook ready: {acc.email} | fetch=Microsoft Graph Mail.Read")
                    return acc.email, token_blob
                except Exception as exc:
                    last_err = exc
                    acc.last_error = str(exc)
                    acc.cooldown_until = _now() + 120
                    self._lg(f"[!] Outlook account failed {acc.email}: {exc}")
            raise Exception(f"Outlook no available account: {last_err}")

    def release(self, email: str, ok: bool = True, bad: bool = False) -> None:
        with _POOL_LOCK:
            for acc in self.accounts:
                if acc.identity() == email.lower():
                    if bad:
                        acc.status = "bad"
                    else:
                        acc.status = "idle"
                        if not ok:
                            acc.cooldown_until = _now() + 60
                    break

    def resolve_access_token(self, email: str, token_blob: str) -> str:
        data = {}
        try:
            data = json.loads(token_blob) if token_blob else {}
        except Exception:
            if token_blob and token_blob.count(".") >= 2:
                return token_blob
            data = {}
        acc = None
        with _POOL_LOCK:
            for a in self.accounts:
                if a.identity() == (email or data.get("email") or "").lower():
                    acc = a
                    break
        if acc is None:
            acc = OutlookAccount(
                email=email or data.get("email") or "",
                password=data.get("password") or "",
                totp_secret=data.get("totp_secret") or "",
                client_id=data.get("client_id") or self.client_id,
                refresh_token=data.get("refresh_token") or "",
                access_token=data.get("access_token") or "",
                access_expires_at=float(data.get("access_expires_at") or 0),
            )
        else:
            if data.get("access_token"):
                acc.access_token = data.get("access_token") or acc.access_token
            if data.get("refresh_token"):
                acc.refresh_token = data.get("refresh_token") or acc.refresh_token
            if data.get("access_expires_at"):
                acc.access_expires_at = float(data.get("access_expires_at") or 0)
        self.ensure_tokens(acc)
        return acc.access_token


def build_pool_from_config(config: dict, proxies=None, log_callback=None) -> OutlookAccountPool:
    text = (config.get("outlook_accounts") or "").strip()
    path = (config.get("outlook_accounts_file") or "outlook_accounts.txt").strip()
    accounts = []
    if text:
        accounts.extend(load_accounts_from_text(text))
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = _root_dir() / path
    accounts.extend(load_accounts_from_file(str(file_path)))
    seen, uniq = set(), []
    for a in accounts:
        if a.identity() in seen:
            continue
        seen.add(a.identity())
        uniq.append(a)
    client_id = (config.get("outlook_client_id") or DEFAULT_CLIENT_ID).strip()
    cache_path = config.get("outlook_token_cache") or "outlook_token_cache.json"
    cp = Path(cache_path)
    if not cp.is_absolute():
        cp = _root_dir() / cache_path
    return OutlookAccountPool(uniq, cache=TokenCache(cp), proxies=proxies,
                              log_callback=log_callback, client_id=client_id)


def get_pool(config: dict, proxies=None, log_callback=None, force_reload: bool = False) -> OutlookAccountPool:
    global _POOL, _POOL_SIG
    sig = json.dumps({
        "accounts": config.get("outlook_accounts") or "",
        "file": config.get("outlook_accounts_file") or "",
        "client_id": config.get("outlook_client_id") or "",
    }, ensure_ascii=False, sort_keys=True)
    with _POOL_LOCK:
        if _POOL is None or force_reload or sig != _POOL_SIG:
            _POOL = build_pool_from_config(config, proxies=proxies, log_callback=log_callback)
            _POOL_SIG = sig
        else:
            _POOL.log_callback = log_callback
            _POOL.proxies = proxies
        return _POOL


def get_email_and_token(config: dict, proxies=None, log_callback=None) -> Tuple[str, str]:
    return get_pool(config, proxies=proxies, log_callback=log_callback).acquire()


def message_text(msg: dict) -> str:
    parts = []
    if msg.get("subject"):
        parts.append(str(msg.get("subject")))
    if msg.get("bodyPreview"):
        parts.append(str(msg.get("bodyPreview")))
    body = msg.get("body") or {}
    content = body.get("content") or ""
    if content:
        if (body.get("contentType") or "").lower() == "html":
            content = re.sub(r"<[^>]+>", " ", content)
        parts.append(content)
    return "\n".join(parts)


def _default_extract(text: str, subject: str = ""):
    if subject:
        m = re.search(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI", subject, re.I)
        if m:
            return m.group(1)
    m = re.search(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", text or "", re.I)
    if m:
        return m.group(1)
    for pattern in (
        r"verification\s+code[:\s]+(\d{4,8})",
        r"your\s+code[:\s]+(\d{4,8})",
        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",
        r"\b(\d{6})\b",
    ):
        m = re.search(pattern, text or "", re.I)
        if m:
            return m.group(1)
    return None


def get_oai_code(config, token_blob, email, timeout=180, poll_interval=3.0,
                 log_callback=None, cancel_callback=None, extract_fn=None, proxies=None) -> str:
    def cancelled():
        if not cancel_callback:
            return False
        try:
            return bool(cancel_callback())
        except Exception:
            return False

    pool = get_pool(config, proxies=proxies, log_callback=log_callback)
    _log(log_callback, f"[*] Outlook poll code | email={email} | API=Microsoft Graph inbox")
    deadline = _now() + timeout
    seen = set()
    last_err = None
    while _now() < deadline:
        if cancelled():
            raise Exception("cancelled")
        try:
            access = pool.resolve_access_token(email, token_blob)
            cid = DEFAULT_CLIENT_ID
            try:
                cid = json.loads(token_blob).get("client_id") or cid
            except Exception:
                pass
            sess = OutlookSession(client_id=cid, proxies=proxies, log_callback=log_callback)
            msgs = sess.list_inbox(access, top=15)
            _log(log_callback, f"[*] Outlook Graph inbox count={len(msgs)} email={email}")
            for msg in msgs:
                mid = msg.get("id") or ""
                if mid in seen:
                    continue
                seen.add(mid)
                subject = msg.get("subject") or ""
                text = message_text(msg)
                frm = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "")
                _log(log_callback, f"[*] Outlook check mail subject={subject[:80]} from={frm}")
                code = extract_fn(text, subject) if extract_fn else None
                if not code:
                    code = _default_extract(text, subject)
                if code:
                    _log(log_callback, f"[+] Outlook code ok email={email} code={code} subject={subject[:60]}")
                    pool.release(email, ok=True)
                    return code
        except Exception as exc:
            last_err = exc
            _log(log_callback, f"[!] Outlook poll error: {exc}")
        time.sleep(max(1.0, float(poll_interval)))
    pool.release(email, ok=False)
    raise Exception(f"Outlook code timeout email={email} last_error={last_err}")


def is_outlook_provider(name: str) -> bool:
    return str(name or "").strip().lower() in {"outlook", "microsoft", "hotmail", "ms_outlook"}
