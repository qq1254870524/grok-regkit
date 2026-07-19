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



Changelog:
- 2026-07-19r29: treat identity/confirm + error.aspx errcode=1078 as permanent identity_confirm_blocked;
  abort _follow_to_code immediately on error.aspx/errcode; delete bad mailbox from pool (no 120s cool).

- 2026-07-19r23: strict post-send code window (since_ts-20s, baseline skip pre-send xAI); fix action '#'/empty -> page URL/urlPost (fix MissingSchema on identity/confirm).
- 2026-07-19r21: early no-new-mail break — after actual send, if Graph shows zero post-send mails for 75s (seen_new_after_send=0), exit poll early with clear error so hybrid burns mailbox faster; still full 180s once any post-send mail appears; plaintext logs.

- 2026-07-18a: detailed mailbox login failure logs (provider/auth path/exception type/raw error, no masking); classify credential/MFA/network.

- 2026-07-17e: build_pool 文件优先；登录失败删除同步内存+文件+config；acquire 删除后继续 while 循环。

- 2026-07-17d: 登录失败/注册成功删除邮箱后同步写回 outlook_accounts 文件 + config 文本，避免重载复活。

- 2026-07-17c: login fail mark bad + next; Graph scan ALL mailFolders (not only inbox/junk).

- 2026-07-17b: preflight Graph login helper; poll top=50; each-round mail dump

  (folder/subject/from/received/id); explicit non-full-mailbox scan note;

  hybrid waits 3s after CreateEmail (caller side).

- 2026-07-17: fix false OTP from inbox noise (e.g. bank "855-730").

- 2026-07-18m: speed — Graph top 20, less preflight/poll dump; keep ALL folders + send+3s poll.

- 2026-07-18r15: Graph folder scan dedupe well-known vs displayName IDs (was double-scanning Inbox/Junk);

  adaptive poll: priority folders (inbox/junk/deleted) most rounds, full custom-folder scan every 3rd round;

  unredacted detailed logs kept.



  Only xAI/Grok related mails; baseline-skip existing inbox on poll start;

  reject bare XXX-XXX without xAI context.

2026-07-18r14: throttle remove-skip log spam; support timeout kw in get_oai_code.

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







def _is_proxy_error(exc: BaseException) -> bool:

    msg = str(exc or "").lower()

    keys = (

        "socks", "proxy", "0x01", "0x03", "0x04", "0x05", "0x06",

        "network unreachable", "general socks", "connection refused",

        "timed out", "timeout", "max retries exceeded",

        "failed to establish a new connection",

    )

    return any(k in msg for k in keys)









def classify_outlook_login_error(exc: BaseException, *, auth_path: str = '') -> dict:
    """Return structured Outlook login failure reason. Never masks upstream text."""
    msg = str(exc or '')
    msg_l = msg.lower()
    et = type(exc).__name__
    category = 'unknown'
    # Microsoft identity proof wall / account protection dead-end
    if (
        'errcode=1078' in msg_l
        or 'error.aspx' in msg_l
        or 'identity/confirm' in msg_l
        or 'identity_confirm' in msg_l
        or 'help us protect your account' in msg_l
        or 'protect your account' in msg_l
    ):
        category = 'identity_confirm_blocked'
    elif any(x in msg for x in ('password login failed', 'MFA/TOTP failed', 'refresh_token invalid', 'AADSTS', 'invalid_grant')) or 'authentication failed' in msg_l:
        if 'MFA/TOTP' in msg or 'totp' in msg_l:
            category = 'mfa_totp_failed'
        elif 'refresh_token' in msg_l or 'invalid_grant' in msg_l:
            category = 'refresh_token_invalid'
        else:
            category = 'credential_invalid'
    elif any(x in msg_l for x in ('proxy', 'timed out', 'timeout', 'connection', 'ssl', 'network', 'unreachable', 'name or service not known', 'max retries')):
        category = 'network_proxy_or_timeout'
    elif 'pool empty' in msg_l or 'no available account' in msg_l:
        category = 'pool_empty'
    permanent = category in (
        'credential_invalid',
        'mfa_totp_failed',
        'refresh_token_invalid',
        'identity_confirm_blocked',
    )


    return {

        'provider': 'outlook',

        'protocol': 'Microsoft Graph / OAuth',

        'auth_path': auth_path or 'unknown',

        'exception_type': et,

        'category': category,

        'permanent': permanent,

        'raw_error': msg,

    }





def format_outlook_login_error(email: str, exc: BaseException, *, stage: str = 'login', auth_path: str = '') -> str:

    info = classify_outlook_login_error(exc, auth_path=auth_path)

    return (

        f"[!] Outlook {stage} FAIL email={email or '-'} provider=outlook "

        f"auth={info['auth_path']} category={info['category']} permanent={int(bool(info['permanent']))} "

        f"exc={info['exception_type']} raw={info['raw_error']}"

    )



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

            raise Exception(f"Outlook did not reach MFA/consent title={self._title(r2.text)} url={getattr(r2, 'url', '')[:180]}")

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
            # permanent dead-ends: identity proof / Microsoft error pages
            ul = (url or '').lower()
            hl = (html or '')[:4000].lower()
            title_l = (self._title(html) or '').lower()
            m_err = re.search(r'errcode=(\d+)', ul) or re.search(r'errcode=(\d+)', hl)
            if 'error.aspx' in ul or m_err:
                code = m_err.group(1) if m_err else '?'
                raise Exception(
                    f"Outlook identity/error.aspx errcode={code} title={self._title(html)} url={url[:180]}"
                )
            if (
                'identity/confirm' in ul
                or 'help us protect your account' in title_l
                or 'protect your account' in title_l
            ) and step >= 1:
                # second hit on identity wall without OAuth code => unrecoverable for automation
                raise Exception(
                    f"Outlook identity_confirm blocked title={self._title(html)} url={url[:180]}"
                )


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

            action = (chosen.get("action") or "").replace("&amp;", "&").strip()
            # identity/confirm and some Continue pages use action="#" or empty
            if (not action) or action in {"#", "./", "javascript:void(0)", "javascript:;"}:
                dfix = self._esd(html)
                action = (dfix.get("urlPost") or "").strip() or url
                self._lg(
                    f"[*] Outlook form action empty/# resolved -> {str(action)[:140]} "
                    f"title={self._title(html)}"
                )
            if action.startswith("/"):
                p = urlparse(url)
                action = f"{p.scheme}://{p.netloc}{action}"
            elif action.startswith("?"):
                p = urlparse(url)
                action = f"{p.scheme}://{p.netloc}{p.path}{action}"
            # still non-absolute? fall back to current URL
            if not (action.startswith("http://") or action.startswith("https://")):
                self._lg(f"[!] Outlook form action still non-absolute: {action!r}; use page url")
                action = url

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



    def _graph_get_messages(

        self,

        access_token: str,

        folder: str,

        top: int = 10,

    ) -> List[dict]:

        """Fetch messages from one Graph mail folder (inbox/junkemail/...)."""

        folder_key = (folder or "inbox").strip().strip("/")

        url = (

            f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder_key}/messages"

            f"?$top={int(top)}&$orderby=receivedDateTime desc"

            "&$select=id,subject,bodyPreview,body,from,receivedDateTime,isRead"

        )

        headers = {"Authorization": f"Bearer {access_token}"}

        attempts = [(None, "direct")]

        if self.proxies:

            attempts.append((self.proxies, "proxy"))

        last_exc: Exception | None = None

        for px, label in attempts:

            try:

                sess = requests.Session()

                sess.headers.update(self.s.headers)

                if px:

                    sess.proxies.update(px)

                r = sess.get(url, headers=headers, timeout=self.timeout)

                if r.status_code == 401:

                    raise Exception("Graph 401: access_token expired")

                r.raise_for_status()

                items = list((r.json() or {}).get("value") or [])

                for m in items:

                    if isinstance(m, dict):

                        m["_folder"] = folder_key

                self._lg(

                    f"[*] Outlook Graph via {label} ok folder={folder_key} count={len(items)}"

                )

                return items

            except Exception as exc:

                last_exc = exc

                self._lg(f"[!] Outlook Graph via {label} fail folder={folder_key}: {exc}")

                if "401" in str(exc):

                    raise

                continue

        if last_exc:

            raise last_exc

        return []



    def _graph_list_all_folder_ids(self, access_token: str) -> List[tuple[str, str]]:

        """Return [(folder_key_or_id, display_name), ...] for all mailFolders incl. children."""

        headers = {"Authorization": f"Bearer {access_token}"}

        attempts = [(None, "direct")]

        if self.proxies:

            attempts.append((self.proxies, "proxy"))

        last_exc: Exception | None = None

        value: list = []

        for px, label in attempts:

            try:

                sess = requests.Session()

                sess.headers.update(self.s.headers)

                if px:

                    sess.proxies.update(px)

                url = (

                    "https://graph.microsoft.com/v1.0/me/mailFolders"

                    "?includeHiddenFolders=true&$top=100"

                    "&$select=id,displayName,parentFolderId,childFolderCount,totalItemCount"

                )

                r = sess.get(url, headers=headers, timeout=self.timeout)

                if r.status_code == 401:

                    raise Exception("Graph 401: access_token expired")

                r.raise_for_status()

                value = list((r.json() or {}).get("value") or [])

                self._lg(f"[*] Outlook Graph list mailFolders via {label} count={len(value)}")

                last_exc = None

                break

            except Exception as exc:

                last_exc = exc

                self._lg(f"[!] Outlook list mailFolders via {label} fail: {exc}")

                if "401" in str(exc):

                    raise

                continue

        if last_exc and not value:

            raise last_exc



        out: List[tuple[str, str]] = []

        seen: set[str] = set()

        seen_aliases: set[str] = set()

        # displayName (lower) -> well-known key already covered

        WELL_ALIAS = {

            "inbox": "inbox",

            "junk email": "junkemail",

            "junkemail": "junkemail",

            "deleted items": "deleteditems",

            "deleteditems": "deleteditems",

            "archive": "archive",

            "drafts": "drafts",

            "sent items": "sentitems",

            "sentitems": "sentitems",

            "outbox": "outbox",

            "conversation history": "conversation history",

        }



        def _add(fid: str, name: str) -> None:

            fid = str(fid or "").strip()

            name = str(name or fid or "").strip()

            if not fid or fid in seen:

                return

            alias = WELL_ALIAS.get(name.lower().strip())

            if alias and alias in seen_aliases:

                # already covered via well-known key; skip id duplicate

                return

            if alias:

                seen_aliases.add(alias)

            seen.add(fid)

            out.append((fid, name))



        # well-known first (single scan path; avoid later id-duplicate of same mailbox)

        for well in ("inbox", "junkemail", "deleteditems", "archive", "drafts", "sentitems"):

            _add(well, well)

            seen_aliases.add(well)



        # BFS remaining roots/children — skip well-known displayName duplicates

        queue = list(value)

        depth_guard = 0

        while queue and depth_guard < 500:

            depth_guard += 1

            folder = queue.pop(0) or {}

            fid = str(folder.get("id") or "")

            name = str(folder.get("displayName") or fid)

            alias = WELL_ALIAS.get(name.lower().strip())

            if not (alias and alias in seen_aliases):

                _add(fid, name)

            child_n = int(folder.get("childFolderCount") or 0)

            if child_n <= 0 or not fid:

                continue

            # fetch children

            for px, label in attempts:

                try:

                    sess = requests.Session()

                    sess.headers.update(self.s.headers)

                    if px:

                        sess.proxies.update(px)

                    curl = (

                        f"https://graph.microsoft.com/v1.0/me/mailFolders/{fid}/childFolders"

                        f"?$top=100&$select=id,displayName,childFolderCount,totalItemCount"

                    )

                    cr = sess.get(curl, headers=headers, timeout=self.timeout)

                    if cr.status_code == 401:

                        raise Exception("Graph 401: access_token expired")

                    if cr.status_code >= 400:

                        continue

                    kids = list((cr.json() or {}).get("value") or [])

                    queue.extend(kids)

                    break

                except Exception as exc:

                    if "401" in str(exc):

                        raise

                    continue

        self._lg(

            f"[*] Outlook Graph ALL folders resolved count={len(out)} "

            f"names={[n for _, n in out[:20]]}{'...' if len(out) > 20 else ''}"

        )

        return out



    def list_inbox(self, access_token: str, top: int = 10, mode: str = "all") -> List[dict]:

        """List recent mail from Graph mail folders (deduped by id).



        mode:

          - priority: inbox + junk + deleted only (fast path for code poll)

          - all: well-known + custom folders (deduped; no double Inbox/Junk)

        """

        merged: List[dict] = []

        seen_ids: set[str] = set()

        last_exc: Exception | None = None

        folder_counts: dict[str, int] = {}

        mode_l = (mode or "all").strip().lower()

        if mode_l in ("priority", "fast", "core"):

            folders = [

                ("inbox", "inbox"),

                ("junkemail", "junkemail"),

                ("deleteditems", "deleteditems"),

            ]

            self._lg(f"[*] Outlook Graph folder mode=priority keys={[k for k,_ in folders]}")

        else:

            try:

                folders = self._graph_list_all_folder_ids(access_token)

            except Exception as exc:

                # fallback to classic well-known set

                self._lg(f"[!] Outlook list all folders failed, fallback inbox+junk: {exc}")

                folders = [("inbox", "inbox"), ("junkemail", "junkemail"), ("deleteditems", "deleteditems")]



        for folder_key, display_name in folders:

            try:

                items = self._graph_get_messages(access_token, folder_key, top=top)

            except Exception as exc:

                last_exc = exc

                # well-known inbox failure is fatal only if nothing else worked

                self._lg(

                    f"[!] Outlook skip folder={display_name} key={folder_key[:24]}: {exc}"

                )

                continue

            label = display_name or folder_key

            folder_counts[label] = len(items)

            for msg in items:

                mid = str((msg or {}).get("id") or "")

                if mid and mid in seen_ids:

                    continue

                if mid:

                    seen_ids.add(mid)

                if isinstance(msg, dict):

                    msg["_folder"] = label

                    msg["_folder_key"] = folder_key

                merged.append(msg)



        def _recv_key(msg: dict) -> str:

            return str((msg or {}).get("receivedDateTime") or "")



        merged.sort(key=_recv_key, reverse=True)

        if not merged and last_exc:

            raise last_exc

        self._lg(

            f"[*] Outlook ALL-folders merged counts={folder_counts} total={len(merged)} "

            f"folder_n={len(folder_counts)}"

            + (f" last_err={last_exc}" if last_exc else "")

        )

        return merged







def _sync_engine_accounts_text(path: str, body: str) -> None:

    """Keep runtime config.outlook_accounts aligned with the live pool file."""

    try:

        import grok_register_ttk as engine

    except Exception:

        return

    try:

        text = (body or "").replace("\r\n", "\n").strip("\n")

        if hasattr(engine, "config") and isinstance(getattr(engine, "config", None), dict):

            engine.config["outlook_accounts"] = text

            name = str(engine.config.get("outlook_accounts_file") or "outlook_accounts.txt").strip() or "outlook_accounts.txt"

            try:

                p = Path(path)

                root = Path(getattr(engine, "__file__", Path.cwd())).resolve().parent

                if p.resolve() == (root / name).resolve() or not Path(name).is_absolute():

                    engine.config["outlook_accounts_file"] = name

            except Exception:

                pass

        save = getattr(engine, "save_config", None)

        if callable(save):

            try:

                save()

            except Exception:

                pass

    except Exception:

        return







class OutlookAccountPool:

    def __init__(self, accounts, cache=None, proxies=None, log_callback=None, client_id=DEFAULT_CLIENT_ID, source_file: str = ""):

        self.accounts = accounts

        self.cache = cache or TokenCache()

        self.proxies = proxies

        self.log_callback = log_callback

        self.client_id = client_id or DEFAULT_CLIENT_ID

        self.source_file = (source_file or "").strip()

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

            last_err = None

            # while: 登录失败会删除账号，列表长度变化，不能用固定 range(n)

            attempts = 0

            max_attempts = max(1, len(self.accounts) * 2)

            while attempts < max_attempts and self.accounts:

                attempts += 1

                n = len(self.accounts)

                if n <= 0:

                    break

                if self._idx >= n:

                    self._idx = 0

                acc = self.accounts[self._idx % n]

                if acc.status in ("bad", "registered") or acc.cooldown_until > _now() or acc.status == "in_use":

                    self._idx = (self._idx + 1) % n

                    continue

                try:

                    src = "refresh_token" if acc.refresh_token else "password+totp"

                    self._lg(f"[*] Outlook acquire: {acc.email} | pool={n} | auth={src}")

                    self.ensure_tokens(acc)

                    acc.status = "in_use"

                    acc.last_used_at = _now()

                    acc.last_error = ""

                    self._idx = (self._idx + 1) % max(1, len(self.accounts))

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

                    auth_path = "refresh_token" if acc.refresh_token else "password+totp"

                    info = classify_outlook_login_error(exc, auth_path=auth_path)

                    msg = str(exc)

                    auth_fail = bool(info.get('permanent')) or any(

                        x in msg

                        for x in (

                            "password login failed",
                            "MFA/TOTP failed",
                            "refresh_token invalid",
                            "401",
                            "AADSTS",
                            "invalid_grant",
                            "account has no refresh_token",
                            "errcode=1078",
                            "error.aspx",
                            "identity_confirm",
                            "identity/confirm",
                            "Help us protect your account",
                            "protect your account",
                        )

                    ) or "login failed" in msg.lower()

                    self._lg(format_outlook_login_error(acc.email, exc, stage='acquire', auth_path=auth_path))

                    if auth_fail:

                        self._lg(

                            f"[!] Outlook 登录失败(凭据/MFA类)，立即从账号池删除(内存+文件+配置)并换下一个 | "

                            f"email={acc.email} category={info.get('category')} "

                            f"auth={auth_path} exc={info.get('exception_type')} raw={info.get('raw_error')}"

                        )

                        self.accounts = [a for a in self.accounts if a.identity() != acc.identity()]

                        try:

                            self.persist_accounts_file()

                        except Exception as pe:

                            self._lg(f"[!] Outlook 删除后写回失败: {pe}")

                        # 删除后不推进 idx，下一轮从同位置取“下一个”

                        if self._idx >= len(self.accounts) and self.accounts:

                            self._idx = 0

                    else:

                        acc.cooldown_until = _now() + 120

                        self._lg(

                            f"[!] Outlook 临时失败(非凭据)，冷却 120s | email={acc.email} "

                            f"category={info.get('category')} auth={auth_path} "

                            f"exc={info.get('exception_type')} raw={info.get('raw_error')}"

                        )

                        self._idx = (self._idx + 1) % max(1, len(self.accounts))

                    self._lg(

                        f"[*] Outlook 继续尝试池内下一个账号 | tried={acc.email} | "

                        f"pool={len(self.accounts)} last_category={info.get('category')}"

                    )

            raise Exception(f"Outlook no available account (all login failed): {last_err}")



    def release(self, email: str, ok: bool = True, bad: bool = False) -> None:

        with _POOL_LOCK:

            em = (email or "").lower()

            if bad:

                before = len(self.accounts)

                self.accounts = [a for a in self.accounts if a.identity() != em]

                if before != len(self.accounts):

                    self._lg(

                        f"[*] Outlook release 登录失败删除 email={email} remaining={len(self.accounts)}"

                    )

                    try:

                        self.persist_accounts_file()

                    except Exception as pe:

                        self._lg(f"[!] Outlook release 写回失败: {pe}")

                return

            for acc in self.accounts:

                if acc.identity() == em:

                    if acc.status == "registered":

                        pass

                    else:

                        acc.status = "idle"

                        if not ok:

                            acc.cooldown_until = _now() + 60

                    break



    def _format_line(self, acc: OutlookAccount) -> str:

        if (acc.source_line or "").strip():

            return acc.source_line.strip()

        if acc.refresh_token and not acc.password:

            if acc.client_id and acc.client_id != DEFAULT_CLIENT_ID:

                return f"{acc.email}----{acc.client_id}----{acc.refresh_token}"

            return f"{acc.email}----{acc.refresh_token}"

        if acc.password and acc.totp_secret:

            if acc.client_id and acc.client_id != DEFAULT_CLIENT_ID:

                return f"{acc.email}----{acc.password}----{acc.totp_secret}----{acc.client_id}"

            return f"{acc.email}----{acc.password}----{acc.totp_secret}"

        if acc.password:

            return f"{acc.email}----{acc.password}"

        return (acc.email or "").strip()



    def persist_accounts_file(self) -> None:

        """Rewrite source accounts file and keep config.outlook_accounts in sync."""

        path = (self.source_file or "").strip()

        lines = [self._format_line(a) for a in self.accounts if (a.email or "").strip()]

        body = "\n".join(lines)

        if body:

            body += "\n"

        if not path:

            self._lg("[!] Outlook persist skip: no source_file")

            _sync_engine_accounts_text("", body)

            return

        pth = Path(path)

        pth.parent.mkdir(parents=True, exist_ok=True)

        pth.write_text(body, encoding="utf-8")

        _sync_engine_accounts_text(str(pth), body)

        self._lg(

            f"[*] Outlook 账号池已实时更新 file={pth} remaining={len(self.accounts)} "

            f"config_synced=1"

        )



    def remove_account(self, email: str, reason: str = "removed") -> bool:

        """Permanently remove email from memory pool and accounts file."""

        em = (email or "").strip().lower()

        if not em:

            return False

        with _POOL_LOCK:

            before = len(self.accounts)

            self.accounts = [a for a in self.accounts if a.identity() != em]

            removed = before - len(self.accounts)

            if removed:

                self._lg(

                    f"[*] Outlook 从账号池删除 email={email} reason={reason} "

                    f"removed={removed} remaining={len(self.accounts)}"

                )

                try:

                    self.persist_accounts_file()

                except Exception as exc:

                    self._lg(f"[!] Outlook 写回账号池失败: {exc}")

                return True

            n = int(getattr(self, "_remove_skip_count", 0) or 0) + 1

            self._remove_skip_count = n

            if n <= 3 or n % 200 == 0:

                self._lg(

                    f"[*] Outlook 删除跳过(池中无此号) email={email} reason={reason} "

                    f"(count={n}; further skips suppressed)"

                )

            return False



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

    """Load Outlook pool with live file as source of truth.



    Priority:

    1) outlook_accounts.txt (or configured file) if present

    2) config.outlook_accounts text only when file is missing

    After load, mirror the live account list into config.outlook_accounts.

    """

    path = (config.get("outlook_accounts_file") or "outlook_accounts.txt").strip() or "outlook_accounts.txt"

    file_path = Path(path)

    if not file_path.is_absolute():

        file_path = _root_dir() / path

    accounts = []

    source = "empty"

    if file_path.is_file():

        accounts = load_accounts_from_file(str(file_path))

        source = f"file:{file_path}"

    else:

        text = (config.get("outlook_accounts") or "").strip()

        if text:

            accounts = load_accounts_from_text(text)

            source = "config.outlook_accounts"

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

    _log(log_callback, f"[*] Outlook pool loaded accounts={len(uniq)} source={source} file={file_path}")

    pool = OutlookAccountPool(

        uniq,

        cache=TokenCache(cp),

        proxies=proxies,

        log_callback=log_callback,

        client_id=client_id,

        source_file=str(file_path),

    )

    try:

        lines = [pool._format_line(a) for a in pool.accounts if (a.email or "").strip()]

        body = "\n".join(lines)

        if body:

            body += "\n"

        _sync_engine_accounts_text(str(file_path), body)

    except Exception:

        pass

    return pool





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





# xAI / Grok verification mail markers (sender + subject/body)

_XAI_FROM_HINTS = (

    "x.ai",

    "xai.com",

    "mail.x.ai",

    "grok",

)

_XAI_TEXT_HINTS = re.compile(

    r"\b(xai|x\.ai|grok|verify(?:\s+your)?\s+email|email\s+verification|"

    r"confirmation\s+code|verification\s+code)\b",

    re.I,

)

_XAI_SUBJECT_CODE = re.compile(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI\b", re.I)

_DASH_CODE = re.compile(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", re.I)





def message_from_address(msg: dict) -> str:

    try:

        return str(((msg.get("from") or {}).get("emailAddress") or {}).get("address") or "").strip()

    except Exception:

        return ""





def is_xai_related_message(msg: dict, text: str = "", subject: str = "") -> bool:

    """Only accept mails that look like xAI/Grok verification, never bank/statement noise."""

    subject = subject or (msg.get("subject") or "")

    text = text or ""

    frm = message_from_address(msg).lower()

    if frm:

        for hint in _XAI_FROM_HINTS:

            if hint in frm:

                return True

    if _XAI_SUBJECT_CODE.search(subject or ""):

        return True

    blob = f"{subject}\n{text}"

    if _XAI_TEXT_HINTS.search(blob):

        return True

    return False





def _default_extract(text: str, subject: str = ""):

    """Extract verification code only with xAI/Grok context.



    Bare XXX-XXX (e.g. bank '855-730') is rejected so Outlook inbox noise

    cannot fake a successful email confirmation step.

    """

    subject = subject or ""

    text = text or ""

    m = _XAI_SUBJECT_CODE.search(subject)

    if m:

        return m.group(1)

    blob = f"{subject}\n{text}"

    has_xai = bool(_XAI_TEXT_HINTS.search(blob))

    if has_xai:

        m = _DASH_CODE.search(blob)

        if m:

            return m.group(1)

    for pattern in (

        r"verification\s+code[:\s]+(\d{4,8})",

        r"your\s+code[:\s]+(\d{4,8})",

        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",

    ):

        m = re.search(pattern, blob, re.I)

        if m and has_xai:

            return m.group(1)

    return None







def preflight_mailbox(

    config,

    token_blob: str,

    email: str,

    *,

    log_callback=None,

    proxies=None,

    top: int = 10,

) -> dict:

    """Validate Graph login BEFORE CreateEmail. Returns summary dict or raises.



    Does NOT scan the whole mailbox — only inbox + junkemail top=N recent mails.

    """

    pool = get_pool(config, proxies=proxies, log_callback=log_callback)

    _log(

        log_callback,

        f"[*] Outlook preflight start email={email} provider=outlook "

        f"protocol=Graph scanned_folders=ALL mailFolders top={int(top)}",

    )

    try:

        access = pool.resolve_access_token(email, token_blob)

    except Exception as token_exc:

        auth_hint_tmp = 'token_resolve'

        try:

            data0 = json.loads(token_blob) if token_blob else {}

            if data0.get('refresh_token'):

                auth_hint_tmp = 'refresh_token'

            elif data0.get('password') and data0.get('totp_secret'):

                auth_hint_tmp = 'password+TOTP'

            elif data0.get('access_token'):

                auth_hint_tmp = 'access_token'

        except Exception:

            pass

        _log(log_callback, format_outlook_login_error(email, token_exc, stage='preflight-token', auth_path=auth_hint_tmp))

        raise

    if not access:

        raise Exception(f"Outlook preflight: empty access_token email={email}")

    auth_hint = "token_blob"

    try:

        data = json.loads(token_blob) if token_blob else {}

        if data.get("access_token"):

            auth_hint = "reuse_access_token_or_refresh"

        elif data.get("refresh_token"):

            auth_hint = "refresh_token"

        elif data.get("password") and data.get("totp_secret"):

            auth_hint = "password+TOTP"

    except Exception:

        pass

    cid = DEFAULT_CLIENT_ID

    try:

        cid = json.loads(token_blob).get("client_id") or cid

    except Exception:

        pass

    sess = OutlookSession(client_id=cid, proxies=proxies, log_callback=log_callback)

    try:

        msgs = sess.list_inbox(access, top=int(top))

    except Exception as graph_exc:

        if proxies and _is_proxy_error(graph_exc):

            _log(log_callback, f"[!] Outlook preflight proxy fail, force direct: {graph_exc}")

            sess = OutlookSession(client_id=cid, proxies=None, log_callback=log_callback)

            msgs = sess.list_inbox(access, top=int(top))

        else:

            _log(log_callback, format_outlook_login_error(email, graph_exc, stage='preflight-graph', auth_path=auth_hint))

            raise

    folder_counts: dict[str, int] = {}

    for msg in msgs:

        f = str((msg or {}).get("_folder") or "inbox")

        folder_counts[f] = folder_counts.get(f, 0) + 1

    # dump recent few for diagnosis

    for i, msg in enumerate(msgs[:4]):  # 2026-07-18m speed

        mid = str((msg or {}).get("id") or "")

        mid_short = (mid[:16] + "...") if len(mid) > 16 else mid

        subj = str((msg or {}).get("subject") or "")[:100]

        frm = message_from_address(msg)

        recv = str((msg or {}).get("receivedDateTime") or "")

        folder = str((msg or {}).get("_folder") or "inbox")

        xai = is_xai_related_message(msg, text=message_text(msg), subject=subj)

        _log(

            log_callback,

            f"[*] Outlook preflight mail[{i}] folder={folder} xai={xai} "

            f"received={recv} from={frm} subject={subj} id={mid_short}",

        )

    summary = {

        "email": email,

        "auth": auth_hint,

        "ok": True,

        "total": len(msgs),

        "folder_counts": folder_counts,

        "scanned_folders": "ALL",

        "top": int(top),

        "full_mailbox": False,

    }

    _log(

        log_callback,

        f"[+] Outlook preflight OK email={email} auth={auth_hint} "

        f"inbox={folder_counts.get('inbox', 0)} junkemail={folder_counts.get('junkemail', 0)} "

        f"total={len(msgs)} scanned_folders=ALL top={int(top)}",

    )

    return summary





def get_oai_code(config, token_blob, email, timeout=180, poll_interval=3.0,

                 log_callback=None, cancel_callback=None, extract_fn=None, proxies=None,

                 ignore_existing: bool = True, since_ts: Optional[float] = None) -> str:

    def cancelled():

        if not cancel_callback:

            return False

        try:

            return bool(cancel_callback())

        except Exception:

            return False



    GRAPH_TOP = 5  # 18r30: ALL folders, newest 5 only (faster; still full folder scan)

    pool = get_pool(config, proxies=proxies, log_callback=log_callback)

    poll_started = _now()

    # Prefer caller-provided since_ts (email submit time); else poll start.

    baseline_ts = float(since_ts) if since_ts else poll_started

    _log(

        log_callback,

        f"[*] Outlook poll code | email={email} | API=Microsoft Graph "

        f"scanned_folders=ALL mailFolders top={GRAPH_TOP}"

        f" | ignore_existing={ignore_existing} | since_ts={baseline_ts:.3f} "

        f"cutoff={baseline_ts - 120:.3f}",

    )

    deadline = poll_started + timeout

    seen = set()

    baseline_done = not ignore_existing

    last_err = None

    poll_round = 0

    login_method = "unknown"

    seen_new_after_send = False  # 18r21 init (must exist before probe log)

    early_no_new_s = 110.0

    while _now() < deadline:

        if cancelled():

            raise Exception("cancelled")

        poll_round += 1

        try:

            access = pool.resolve_access_token(email, token_blob)

            if not access:

                raise Exception(f"empty access_token after resolve email={email}")

            # Infer login path from pool account / token blob

            login_method = "resolve_access_token"

            try:

                data0 = json.loads(token_blob) if token_blob else {}

                with _POOL_LOCK:

                    for a in pool.accounts:

                        if a.identity() == (email or "").lower():

                            if a.access_token and a.access_expires_at > _now() + 30:

                                login_method = "reuse_access_token"

                            elif a.refresh_token:

                                login_method = "refresh_token_or_reuse"

                            elif a.password and a.totp_secret:

                                login_method = "password+TOTP"

                            break

                if login_method == "resolve_access_token" and data0.get("access_token"):

                    login_method = "token_blob_access_token"

            except Exception:

                pass

            _log(

                log_callback,

                f"[*] Outlook poll round={poll_round} email={email} "

                f"login={login_method} access_token_len={len(access)} "

                f"remain={max(0, deadline - _now()):.0f}s",

            )

            cid = DEFAULT_CLIENT_ID

            try:

                cid = json.loads(token_blob).get("client_id") or cid

            except Exception:

                pass

            sess = OutlookSession(client_id=cid, proxies=proxies, log_callback=log_callback)

            # r15: most rounds priority (inbox/junk/deleted ~3 folders);

            # every 3rd round full deduped ALL for spam-edge cases.

            folder_mode = "all" if (poll_round % 3 == 0) else "priority"

            try:

                _log(

                    log_callback,

                    f"[*] Outlook Graph list mode={folder_mode} round={poll_round} "

                    f"email={email}",

                )

                msgs = sess.list_inbox(access, top=GRAPH_TOP, mode=folder_mode)

            except Exception as graph_exc:

                if proxies and _is_proxy_error(graph_exc):

                    _log(log_callback, f"[!] Outlook Graph all-proxy failed, force direct: {graph_exc}")

                    sess_direct = OutlookSession(client_id=cid, proxies=None, log_callback=log_callback)

                    msgs = sess_direct.list_inbox(access, top=GRAPH_TOP, mode=folder_mode)

                else:

                    raise

            folder_counts: dict[str, int] = {}

            for m0 in msgs:

                f0 = str((m0 or {}).get("_folder") or "inbox")

                folder_counts[f0] = folder_counts.get(f0, 0) + 1

            _log(

                log_callback,

                f"[*] Outlook Graph messages count={len(msgs)} email={email} "

                f"folders=ALL top={GRAPH_TOP} "

                f"counts={folder_counts} login={login_method}",

            )

            # 18r21 post-send new-mail probe (any folder, any sender)

            post_send_n = 0

            for m0 in msgs:

                rcv = str((m0 or {}).get("receivedDateTime") or "")

                if not rcv:

                    continue

                try:

                    from datetime import datetime as _dt

                    ts = _dt.fromisoformat(rcv.replace("Z", "+00:00")).timestamp()

                    # allow 15s clock skew after send baseline

                    if ts + 15.0 >= float(baseline_ts):

                        post_send_n += 1

                        seen_new_after_send = True

                except Exception:

                    pass

            if post_send_n or (poll_round <= 2) or (poll_round % 5 == 0):

                _log(

                    log_callback,

                    f"[*] Outlook post-send new-mail probe round={poll_round} "

                    f"post_send_n={post_send_n} seen_new_after_send={int(bool(seen_new_after_send))} "

                    f"email={email} baseline_ts={baseline_ts:.3f}",

                )

            # Always dump recent mails each round for diagnosis (no redaction)

            dump_n = min(len(msgs), 4 if poll_round <= 2 else 2)  # 2026-07-18m speed

            for i, msg in enumerate(msgs[:dump_n]):

                mid = str((msg or {}).get("id") or "")

                mid_short = (mid[:18] + "...") if len(mid) > 18 else mid

                subject0 = str((msg or {}).get("subject") or "")[:100]

                frm0 = message_from_address(msg)

                recv0 = str((msg or {}).get("receivedDateTime") or "")

                folder0 = str((msg or {}).get("_folder") or "inbox")

                body0 = message_text(msg)

                xai0 = is_xai_related_message(msg, text=body0, subject=subject0)

                _log(

                    log_callback,

                    f"[*] Outlook dump r{poll_round}[{i}] folder={folder0} xai={xai0} "

                    f"received={recv0} from={frm0} subject={subject0} id={mid_short}",

                )

            if len(msgs) > dump_n:

                _log(

                    log_callback,

                    f"[*] Outlook dump r{poll_round} ... and {len(msgs) - dump_n} more "

                    f"(only top recent listed)",

                )



            # First poll: baseline-skip noise AND pre-send xAI mails.
            # 18r23: never accept prior registration codes (same mailbox reused).
            if not baseline_done:
                skipped = 0
                skipped_old_xai = 0
                hard_cut = float(baseline_ts) - 20.0
                for msg in msgs:
                    mid = msg.get("id") or ""
                    if not mid:
                        continue
                    subj0 = msg.get("subject") or ""
                    body0 = message_text(msg)
                    recv_b = str(msg.get("receivedDateTime") or "")
                    is_xai = is_xai_related_message(msg, text=body0, subject=subj0)
                    pre_send = False
                    if recv_b:
                        try:
                            from datetime import datetime as _dtb
                            ts_b = _dtb.fromisoformat(recv_b.replace("Z", "+00:00")).timestamp()
                            pre_send = ts_b < hard_cut
                        except Exception:
                            pre_send = False
                    if is_xai and not pre_send:
                        # keep only post-send (or near-send) xAI candidates
                        continue
                    seen.add(mid)
                    skipped += 1
                    if is_xai and pre_send:
                        skipped_old_xai += 1
                        _log(
                            log_callback,
                            f"[*] Outlook baseline skip pre-send xAI received={recv_b} "
                            f"subject={str(subj0)[:60]} hard_cut_skew=20s",
                        )
                _log(
                    log_callback,
                    f"[*] Outlook baseline skip existing={skipped} pre_send_xai={skipped_old_xai} "
                    f"(only post-send xAI kept; bare XXX-XXX rejected)",
                )
                baseline_done = True



            for msg in msgs:

                mid = msg.get("id") or ""

                if mid and mid in seen:

                    continue

                if mid:

                    seen.add(mid)



                subject = msg.get("subject") or ""

                text_body = message_text(msg)

                frm = message_from_address(msg)

                received = str(msg.get("receivedDateTime") or "")



                # 18r23: when since_ts (actual send) known, only allow ~20s pre-send skew.
                # Without since_ts keep 120s skew for cold poll / secondary SSO.
                if since_ts:
                    cutoff = float(since_ts) - 20.0
                else:
                    cutoff = float(baseline_ts) - 120.0
                if received:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(received.replace("Z", "+00:00"))
                        if dt.timestamp() < cutoff:
                            _log(
                                log_callback,
                                f"[*] Outlook skip old mail received={received} "
                                f"cutoff={cutoff:.3f} since_ts={since_ts} subject={subject[:60]}",
                            )
                            continue
                    except Exception:
                        pass



                if not is_xai_related_message(msg, text=text_body, subject=subject):

                    _log(

                        log_callback,

                        f"[*] Outlook skip non-xAI mail subject={subject[:80]} from={frm}",

                    )

                    continue



                folder = msg.get("_folder") or "inbox"

                _log(

                    log_callback,

                    f"[*] Outlook check xAI mail folder={folder} subject={subject[:80]} "

                    f"from={frm} received={received}",

                )

                code = None

                if extract_fn:

                    try:

                        code = extract_fn(text_body, subject)

                    except TypeError:

                        code = extract_fn(text_body)

                if not code:

                    code = _default_extract(text_body, subject)

                if code:

                    folder = msg.get("_folder") or "inbox"

                    _log(

                        log_callback,

                        f"[+] Outlook code ok email={email} code={code} "

                        f"subject={subject[:60]} from={frm} source=Graph/{folder}",

                    )

                    pool.release(email, ok=True)

                    return code

                _log(

                    log_callback,

                    f"[*] Outlook xAI mail has no parseable code yet subject={subject[:60]}",

                )

        except Exception as exc:

            last_err = exc

            _log(log_callback, f"[!] Outlook poll error: {exc}")

        # 18r21: if mailbox silent after send for early_no_new_s, stop waiting full timeout

        elapsed_poll = _now() - poll_started

        if (not seen_new_after_send) and elapsed_poll >= float(early_no_new_s):

            _log(

                log_callback,

                f"[!] Outlook early_no_new_mail email={email} elapsed={elapsed_poll:.1f}s "

                f"threshold={early_no_new_s:.0f}s rounds={poll_round} "

                f"seen_new_after_send=0 (Graph no post-send mail; burn/switch)",

            )

            pool.release(email, ok=False)

            raise Exception(

                f"Outlook early_no_new_mail email={email} elapsed={elapsed_poll:.1f}s "

                f"threshold={early_no_new_s:.0f}s rounds={poll_round} "

                f"login={login_method} seen_new_after_send=0"

            )

        time.sleep(max(1.0, float(poll_interval)))

    pool.release(email, ok=False)

    raise Exception(

        f"Outlook code timeout email={email} last_error={last_err} "

        f"rounds={poll_round} login={login_method} "

        f"scanned_folders=ALL mailFolders top={GRAPH_TOP}"

    )





def is_outlook_provider(name: str) -> bool:

    return str(name or "").strip().lower() in {"outlook", "microsoft", "hotmail", "ms_outlook"}

