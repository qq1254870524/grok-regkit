"""Pure-HTTP SSO cookie → OIDC tokens (device flow, no browser).

Uses curl_cffi (Chrome TLS fingerprint) + SSO cookie to:
  1. Validate session on accounts.x.ai
  2. Request device code (stdlib / oauth_device)
  3. GET verification_uri_complete
  4. POST /oauth2/device/verify
  5. POST /oauth2/device/approve
  6. Poll token endpoint

18r44: multi-proxy candidates + TRUE direct fallback on SOCKS reject (curl 97).

On any failure raise ProtocolMintError so callers can fall back to browser mint.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .oauth_device import (
    CLIENT_ID,
    ISSUER,
    OAuthDeviceError,
    SCOPE,
    poll_device_token,
    request_device_code,
)
from .proxyutil import (
    canonicalize_proxy_url,
    is_proxy_transport_error,
    normalize_proxy_candidates,
    proxy_log_label,
    resolve_proxy,
    set_runtime_proxy,
)

LogFn = Callable[[str], None]

VERIFY_URL = f"{ISSUER}/oauth2/device/verify"
APPROVE_URL = f"{ISSUER}/oauth2/device/approve"


class ProtocolMintError(RuntimeError):
    """Protocol path failed; caller may fall back to browser mint."""


def _noop_log(_: str) -> None:
    return None


def extract_sso_from_cookies(cookies: Any) -> str:
    """Pull sso / sso-rw value from a cookie list/dict."""
    if not cookies:
        return ""
    if isinstance(cookies, str):
        return cookies.strip()
    if isinstance(cookies, dict):
        for name in ("sso", "sso-rw"):
            v = cookies.get(name)
            if v:
                return str(v).strip()
        return ""
    if isinstance(cookies, (list, tuple)):
        # Prefer bare "sso" over "sso-rw"
        found_rw = ""
        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or c.get("Name") or "")
            value = c.get("value") if "value" in c else c.get("Value")
            if not value:
                continue
            if name == "sso":
                return str(value).strip()
            if name == "sso-rw" and not found_rw:
                found_rw = str(value).strip()
        return found_rw
    return ""


def _session(proxy: str | None, log: LogFn, *, force_direct: bool = False):
    try:
        from curl_cffi import requests as cf_requests
    except ImportError as e:
        raise ProtocolMintError(
            "curl_cffi not installed; cannot run protocol mint"
        ) from e

    s = cf_requests.Session()
    if force_direct:
        s.proxies = {"http": None, "https": None}
        log("protocol proxy=direct")
        return s
    resolved = canonicalize_proxy_url(resolve_proxy(proxy, force_direct=False) or proxy or "")
    if resolved:
        s.proxies = {"http": resolved, "https": resolved}
        log(f"protocol proxy={proxy_log_label(resolved)}")
    else:
        s.proxies = {"http": None, "https": None}
        log("protocol proxy=direct")
    return s


def _set_sso_cookie(session: Any, sso_cookie: str) -> None:
    sso_cookie = (sso_cookie or "").strip()
    if not sso_cookie:
        raise ProtocolMintError("empty sso cookie")
    for domain in (".x.ai", "accounts.x.ai", "auth.x.ai", ".accounts.x.ai"):
        try:
            session.cookies.set("sso", sso_cookie, domain=domain)
        except Exception:
            try:
                session.cookies.set("sso", sso_cookie, domain=domain, path="/")
            except Exception:
                pass
        try:
            session.cookies.set("sso-rw", sso_cookie, domain=domain)
        except Exception:
            pass


def _set_extra_cookies(session: Any, cookies: Any) -> int:
    """Inject full jar (cf_clearance etc.) — SSO alone often fails CF on device/verify."""
    n = 0
    if not cookies:
        return 0
    items = []
    if isinstance(cookies, dict):
        items = [{"name": k, "value": v} for k, v in cookies.items()]
    elif isinstance(cookies, (list, tuple)):
        items = [c for c in cookies if isinstance(c, dict)]
    for c in items:
        name = str(c.get("name") or c.get("Name") or "").strip()
        value = c.get("value") if "value" in c else c.get("Value")
        if not name or value is None:
            continue
        domain = str(c.get("domain") or c.get("Domain") or ".x.ai").strip() or ".x.ai"
        path = str(c.get("path") or c.get("Path") or "/").strip() or "/"
        for d in (domain, ".x.ai", "accounts.x.ai", "auth.x.ai"):
            try:
                session.cookies.set(name, str(value), domain=d, path=path)
                n += 1
                break
            except Exception:
                try:
                    session.cookies.set(name, str(value), domain=d)
                    n += 1
                    break
                except Exception:
                    continue
    return n


def _url_path(url: str) -> str:
    try:
        return urlparse(url or "").path or ""
    except Exception:
        return url or ""

def _route_label(proxy: str | None, force_direct: bool) -> str:
    if force_direct:
        return "direct"
    return proxy_log_label(proxy or "") or "direct"


def _mint_once(
    *,
    sso_cookie: str,
    email: str,
    proxy: str | None,
    force_direct: bool,
    proxy_candidates: list[str],
    cookies: Any | None,
    timeout: float,
    poll_timeout_sec: float,
    log: LogFn,
    cancel: Callable[[], bool] | None,
) -> dict[str, Any]:
    label = _route_label(proxy, force_direct)
    log(f"protocol route={label}")

    if force_direct:
        set_runtime_proxy(None)
        resolved = ""
    else:
        resolved = resolve_proxy(proxy)
        set_runtime_proxy(resolved or None)

    session = _session(resolved or None, log, force_direct=force_direct)
    n_extra = _set_extra_cookies(session, cookies)
    if n_extra:
        log(f"protocol extra cookies set={n_extra}")
    _set_sso_cookie(session, sso_cookie)

    imp = "chrome131"

    try:
        try:
            r = session.get(
                "https://accounts.x.ai/",
                impersonate=imp,
                timeout=timeout,
                allow_redirects=True,
            )
        except TypeError:
            r = session.get(
                "https://accounts.x.ai/",
                timeout=timeout,
                allow_redirects=True,
            )
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"accounts.x.ai network error: {e}") from e

    final_url = getattr(r, "url", "") or ""
    if "sign-in" in final_url or "sign-up" in final_url:
        raise ProtocolMintError(f"sso invalid (landed {final_url[:120]})")
    log(f"protocol sso valid url={final_url[:120]}")

    if cancel and cancel():
        raise ProtocolMintError("cancelled")

    try:
        sess = request_device_code(
            proxy=(None if force_direct else (resolved or None)),
            proxy_candidates=([] if force_direct else proxy_candidates),
            timeout=timeout,
            log=log,
            allow_direct_fallback=True,
            prefer_direct_first=True,
            network_attempts=2,
        )
    except OAuthDeviceError as e:
        raise ProtocolMintError(f"device code: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"device code: {e}") from e
    log(f"protocol user_code={sess.user_code}")

    if cancel and cancel():
        raise ProtocolMintError("cancelled")

    try:
        try:
            r = session.get(
                sess.verification_uri_complete,
                impersonate=imp,
                timeout=timeout,
                allow_redirects=True,
            )
        except TypeError:
            r = session.get(
                sess.verification_uri_complete,
                timeout=timeout,
                allow_redirects=True,
            )
        log(
            f"protocol verify-uri status={getattr(r, 'status_code', '?')} "
            f"url={getattr(r, 'url', '')[:140]}"
        )
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"verification_uri get failed: {e}") from e

    if cancel and cancel():
        raise ProtocolMintError("cancelled")

    try:
        try:
            r = session.post(
                VERIFY_URL,
                data={"user_code": sess.user_code},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                impersonate=imp,
                timeout=timeout,
                allow_redirects=True,
            )
        except TypeError:
            r = session.post(
                VERIFY_URL,
                data={"user_code": sess.user_code},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
                allow_redirects=True,
            )
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"device/verify exception: {e}") from e

    verify_url = getattr(r, "url", "") or ""
    status = getattr(r, "status_code", 0)
    path = _url_path(verify_url)
    body_snip = ""
    try:
        body_snip = (r.text or "")[:200]
    except Exception:
        pass

    if "consent" not in verify_url and "consent" not in path:
        soft_ok = (
            "consent" in (body_snip or "").lower()
            or "authorize grok build" in (body_snip or "").lower()
            or "\u6388\u6743 grok build" in (body_snip or "").lower()
        )
        if not soft_ok:
            raise ProtocolMintError(
                f"device/verify failed status={status} url={verify_url[:160]}"
            )
    log(f"protocol verify ok status={status} url={verify_url[:140]}")

    if cancel and cancel():
        raise ProtocolMintError("cancelled")

    try:
        try:
            r = session.post(
                APPROVE_URL,
                data={
                    "user_code": sess.user_code,
                    "action": "allow",
                    "principal_type": "User",
                    "principal_id": "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                impersonate=imp,
                timeout=timeout,
                allow_redirects=True,
            )
        except TypeError:
            r = session.post(
                APPROVE_URL,
                data={
                    "user_code": sess.user_code,
                    "action": "allow",
                    "principal_type": "User",
                    "principal_id": "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
                allow_redirects=True,
            )
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"device/approve exception: {e}") from e

    approve_url = getattr(r, "url", "") or ""
    status = getattr(r, "status_code", 0)
    if "done" not in approve_url and "device/done" not in _url_path(approve_url):
        try:
            text = r.text or ""
        except Exception:
            text = ""
        if (
            "\u8bbe\u5907\u5df2\u6388\u6743" not in text
            and "device authorized" not in text.lower()
            and "done" not in text.lower()
        ):
            raise ProtocolMintError(
                f"device/approve failed status={status} url={approve_url[:160]}"
            )
    log(f"protocol approve ok status={status} url={approve_url[:140]}")

    poll_expires = min(int(sess.expires_in), max(int(poll_timeout_sec), 30))
    try:
        tr = poll_device_token(
            sess.device_code,
            interval=max(int(sess.interval), 2),
            expires_in=poll_expires,
            timeout=timeout,
            log=log,
            cancel=cancel,
            proxy=(None if force_direct else (resolved or None)),
            proxy_candidates=([] if force_direct else proxy_candidates),
            allow_direct_fallback=True,
        )
    except OAuthDeviceError as e:
        raise ProtocolMintError(f"token poll: {e}") from e
    except Exception as e:  # noqa: BLE001
        raise ProtocolMintError(f"token poll: {e}") from e

    log(
        f"protocol token ok expires_in={tr.expires_in}"
        + (f" email={email}" if email else "")
        + f" route={label}"
    )
    return {
        "access_token": tr.access_token,
        "refresh_token": tr.refresh_token,
        "id_token": tr.id_token,
        "token_type": tr.token_type,
        "expires_in": tr.expires_in,
        "user_code": sess.user_code,
        "mint_method": "protocol",
        "proxy_route": label,
    }


def mint_with_sso_protocol(
    *,
    sso_cookie: str,
    email: str = "",
    proxy: str | None = None,
    proxy_candidates: Iterable[str] | list[str] | None = None,
    cookies: Any | None = None,
    timeout: float = 30.0,
    poll_timeout_sec: float = 90.0,
    log: LogFn | None = None,
    cancel: Callable[[], bool] | None = None,
    allow_direct_fallback: bool = True,
) -> dict[str, Any]:
    """SSO cookie to OIDC token dict. Multi-proxy + true direct on SOCKS reject."""
    log = log or _noop_log
    sso_cookie = (sso_cookie or "").strip() or extract_sso_from_cookies(cookies)
    if not sso_cookie:
        raise ProtocolMintError("missing sso cookie")

    candidates = normalize_proxy_candidates(proxy, proxy_candidates, max_n=8)
    # Prefer direct first: residential SOCKS often curl-97 on auth.x.ai
    routes: list[tuple[str | None, bool]] = []
    if allow_direct_fallback:
        routes.append((None, True))
    for p in candidates:
        routes.append((p, False))
    if not routes:
        resolved0 = canonicalize_proxy_url(resolve_proxy(proxy) or proxy or "")
        if resolved0:
            routes.append((resolved0, False))
        routes.append((None, True))

    last_err: BaseException | None = None
    for i, (route_proxy, force_direct) in enumerate(routes, 1):
        if cancel and cancel():
            raise ProtocolMintError("cancelled")
        label = _route_label(route_proxy, force_direct)
        log(f"protocol try route {i}/{len(routes)} {label}")
        try:
            return _mint_once(
                sso_cookie=sso_cookie,
                email=email,
                proxy=route_proxy,
                force_direct=force_direct,
                proxy_candidates=candidates,
                cookies=cookies,
                timeout=timeout,
                poll_timeout_sec=poll_timeout_sec,
                log=log,
                cancel=cancel,
            )
        except ProtocolMintError as e:
            last_err = e
            msg = str(e)
            if "sso invalid" in msg.lower() or "missing sso" in msg.lower():
                raise
            if is_proxy_transport_error(e) or "network error" in msg.lower() or "device code:" in msg.lower():
                log(f"protocol route={label} failed (retryable): {e}")
                continue
            if any(x in msg.lower() for x in ("failed", "exception", "timeout", "closed")):
                log(f"protocol route={label} failed (try next): {e}")
                continue
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if is_proxy_transport_error(e):
                log(f"protocol route={label} transport error: {e}")
                continue
            raise ProtocolMintError(str(e)) from e

    raise ProtocolMintError(
        f"protocol mint failed all routes ({len(routes)}): {last_err}"
    )
