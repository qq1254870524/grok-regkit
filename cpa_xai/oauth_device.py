"""xAI OAuth device-code grant (Grok CLI / CPA client).

18r44: TRUE direct fallback (ProxyHandler({})) ignores runtime/env proxy pin;
        multi-proxy candidates; SOCKS reject classified as transient.

Endpoints from https://auth.x.ai/.well-known/openid-configuration
"""

from __future__ import annotations

import json
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .proxyutil import (
    canonicalize_proxy_url,
    is_force_direct,
    is_proxy_transport_error,
    normalize_proxy_candidates,
    proxy_log_label,
    resolve_proxy,
)

# Keep in sync with CLIProxyAPI internal/auth/xai/types.go
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
ISSUER = "https://auth.x.ai"
DEVICE_CODE_URL = "https://auth.x.ai/oauth2/device/code"
TOKEN_URL = "https://auth.x.ai/oauth2/token"
SCOPE = "openid profile email offline_access grok-cli:access api:access"

LogFn = Callable[[str], None]


def _noop_log(_: str) -> None:
    return None


def _safe_proxy_label(proxy: str | None, *, force_direct: bool = False) -> str:
    if force_direct or is_force_direct(proxy):
        return "direct"
    lab = proxy_log_label(proxy or "")
    return lab or "direct"


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _opener(proxy: str | None = None, *, force_direct: bool = False) -> urllib.request.OpenerDirector:
    """Build opener. force_direct=True always disables all proxies (incl. env)."""
    handlers: list[Any] = []
    ctx = _ssl_context()
    if ctx is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    if force_direct or is_force_direct(proxy):
        handlers.append(urllib.request.ProxyHandler({}))
    else:
        p = (proxy or "").strip()
        if not p:
            p = resolve_proxy(None)
        if p and not is_force_direct(p):
            handlers.append(urllib.request.ProxyHandler({"http": p, "https": p}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _is_transient_net_error(exc: BaseException) -> bool:
    if is_proxy_transport_error(exc):
        return True
    if isinstance(
        exc,
        (
            TimeoutError,
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            ConnectionRefusedError,
        ),
    ):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, BaseException) and _is_transient_net_error(reason):
            return True
        msg = str(exc).lower()
        needles = (
            "broken pipe",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "network is unreachable",
            "name or service not known",
            "unexpected_eof",
            "eof occurred",
            "ssl",
            "handshake",
            "remote end closed",
            "bad gateway",
            "connection refused",
            "rejected by the socks",
            "socks5",
            "proxy",
        )
        return any(n in msg for n in needles)
    try:
        import ssl as _ssl

        if isinstance(exc, _ssl.SSLError):
            return True
    except Exception:
        pass
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) in {32, 104, 110, 111, 113, 101}:
            return True
        msg = str(exc).lower()
        return any(
            n in msg for n in ("broken pipe", "timed out", "connection reset", "ssl", "socks", "proxy")
        )
    return False


def _post_form_curl(
    url: str,
    form: dict[str, str],
    timeout: float,
    *,
    proxy: str | None,
    force_direct: bool,
) -> tuple[int, dict[str, Any] | str]:
    """POST via curl_cffi (real SOCKS5h + Chrome TLS)."""
    from curl_cffi import requests as cf_requests

    if force_direct or is_force_direct(proxy):
        proxies = {"http": None, "https": None}
    else:
        p = canonicalize_proxy_url(proxy) if proxy else ""
        if not p:
            p = canonicalize_proxy_url(resolve_proxy(None))
        proxies = {"http": p, "https": p} if p else {"http": None, "https": None}
    r = cf_requests.post(
        url,
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "grok-reg-cpa-xai-minter/1.1",
        },
        proxies=proxies,
        timeout=timeout,
        impersonate="chrome",
        verify=True,
    )
    body = r.text or ""
    try:
        return int(r.status_code), json.loads(body)
    except json.JSONDecodeError:
        return int(r.status_code), body


def _post_form(
    url: str,
    form: dict[str, str],
    timeout: float = 30.0,
    *,
    proxy: str | None = None,
    force_direct: bool = False,
    retries: int = 0,
    retry_sleep: float = 1.5,
) -> tuple[int, dict[str, Any] | str]:
    """POST form-urlencoded.

    - force_direct / no proxy: curl direct first, urllib ProxyHandler({}) fallback
    - with proxy: curl with canonical socks5h URL (urllib cannot do SOCKS auth)
    """
    last: BaseException | None = None
    attempts = max(int(retries), 0) + 1
    want_direct = force_direct or is_force_direct(proxy) or not (proxy or "").strip()

    for i in range(attempts):
        try:
            try:
                return _post_form_curl(
                    url,
                    form,
                    timeout,
                    proxy=None if want_direct else proxy,
                    force_direct=want_direct,
                )
            except ImportError:
                pass
            except BaseException:
                if not want_direct:
                    # proxy route: do not hide behind urllib (SOCKS broken there)
                    raise
                # direct curl failed — fall urllib true-direct
            data = urllib.parse.urlencode(form).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "grok-reg-cpa-xai-minter/1.1",
                },
            )
            opener = _opener(None if want_direct else proxy, force_direct=want_direct)
            with opener.open(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                status = getattr(resp, "status", 200) or 200
                try:
                    return int(status), json.loads(body)
                except json.JSONDecodeError:
                    return int(status), body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return int(e.code), json.loads(body)
            except json.JSONDecodeError:
                return int(e.code), body
        except BaseException as e:  # noqa: BLE001
            last = e
            if not _is_transient_net_error(e) or i + 1 >= attempts:
                raise
            time.sleep(retry_sleep * (i + 1))
    assert last is not None
    raise last



@dataclass
class DeviceCodeSession:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int
    raw: dict[str, Any]


@dataclass
class TokenResult:
    access_token: str
    refresh_token: str
    id_token: str | None
    token_type: str
    expires_in: int
    raw: dict[str, Any]


class OAuthDeviceError(RuntimeError):
    pass


def request_device_code(
    *,
    client_id: str = CLIENT_ID,
    scope: str = SCOPE,
    timeout: float = 30.0,
    proxy: str | None = None,
    proxy_candidates: Iterable[str] | None = None,
    log: LogFn | None = None,
    network_attempts: int = 1,
    allow_direct_fallback: bool = True,
    prefer_direct_first: bool = True,
) -> DeviceCodeSession:
    """Request device code with multi-proxy rotation + true direct fallback.

    auth.x.ai often rejects residential SOCKS (curl 97). Default prefer_direct_first
    tries real direct first, then SOCKS candidates.
    """
    log = log or _noop_log
    proxies = normalize_proxy_candidates(proxy, proxy_candidates, max_n=8)
    routes: list[tuple[str, str | None, bool]] = []
    if prefer_direct_first and allow_direct_fallback:
        routes.append(("direct", None, True))
    for p in proxies:
        routes.append(("proxy", p, False))
    if allow_direct_fallback and not prefer_direct_first:
        routes.append(("direct", None, True))
    if not routes:
        routes.append(("direct", None, True))
    # de-dupe consecutive direct
    dedup: list[tuple[str, str | None, bool]] = []
    seen_direct = False
    for kind, route, fd in routes:
        if fd:
            if seen_direct:
                continue
            seen_direct = True
        dedup.append((kind, route, fd))
    routes = dedup

    status: int = 0
    body: dict[str, Any] | str = {}
    last_exc: BaseException | None = None
    rate_attempt = 0

    for route_i, (_kind, route, force_direct) in enumerate(routes, 1):
        label = _safe_proxy_label(route, force_direct=force_direct)
        for attempt in range(1, max(1, int(network_attempts)) + 1):
            started = time.monotonic()
            try:
                status, body = _post_form(
                    DEVICE_CODE_URL,
                    {"client_id": client_id, "scope": scope},
                    timeout=timeout,
                    proxy=route,
                    force_direct=force_direct,
                    retries=0,
                )
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                transient = _is_transient_net_error(exc)
                log(
                    f"device-code request endpoint=auth.x.ai/oauth2/device/code "
                    f"route={label} attempt={attempt}/{network_attempts} "
                    f"elapsed={time.monotonic()-started:.2f}s error={type(exc).__name__} "
                    f"transient={transient}"
                )
                if not transient:
                    raise OAuthDeviceError(
                        f"device code network error ({type(exc).__name__}): {exc}"
                    ) from exc
                if attempt >= max(1, int(network_attempts)):
                    break
                time.sleep(min(1.0 * (2 ** (attempt - 1)) + random.uniform(0.05, 0.35), 8.0))
                continue
            log(
                f"device-code response endpoint=auth.x.ai/oauth2/device/code "
                f"route={label} attempt={attempt}/{network_attempts} status={status} "
                f"elapsed={time.monotonic()-started:.2f}s"
            )
            if status == 200 and isinstance(body, dict):
                last_exc = None
                break
            err = (
                str(body.get("error") or body.get("error_description") or "")
                if isinstance(body, dict)
                else ""
            )
            if status == 429 or "slow_down" in err.lower() or "rate" in err.lower():
                rate_attempt += 1
                if rate_attempt >= 5:
                    raise OAuthDeviceError(
                        f"device code rate limit persisted after {rate_attempt} attempts"
                    )
                wait = min(15 * rate_attempt, 60)
                log(f"device code rate-limited (HTTP {status}), sleep {wait}s then retry")
                time.sleep(wait)
                continue
            last_exc = OAuthDeviceError(f"device code request failed HTTP {status}: {body!r}")
            break
        if status == 200 and isinstance(body, dict):
            break
        if route_i < len(routes):
            nxt = routes[route_i]
            nxt_label = _safe_proxy_label(nxt[1], force_direct=nxt[2])
            log(
                f"device-code route exhausted ({label}); try next route={nxt_label} "
                f"({route_i}/{len(routes)})"
            )

    if status != 200 or not isinstance(body, dict):
        if last_exc is not None:
            raise OAuthDeviceError(
                f"device code network retries exhausted: {type(last_exc).__name__}: {last_exc}"
            ) from last_exc
        raise OAuthDeviceError(f"device code request failed HTTP {status}: {body!r}")

    device_code = str(body.get("device_code") or "").strip()
    user_code = str(body.get("user_code") or "").strip()
    if not device_code or not user_code:
        raise OAuthDeviceError("device code response missing required fields")
    vuri = str(body.get("verification_uri") or "https://accounts.x.ai/oauth2/device").strip()
    vcomplete = str(
        body.get("verification_uri_complete") or f"{vuri}?user_code={user_code}"
    ).strip()
    return DeviceCodeSession(
        device_code,
        user_code,
        vuri,
        vcomplete,
        int(body.get("expires_in") or 1800),
        max(int(body.get("interval") or 5), 1),
        body,
    )


def poll_device_token(
    device_code: str,
    *,
    client_id: str = CLIENT_ID,
    interval: int = 5,
    expires_in: int = 1800,
    timeout: float = 30.0,
    log: LogFn | None = None,
    cancel: Callable[[], bool] | None = None,
    proxy: str | None = None,
    proxy_candidates: Iterable[str] | None = None,
    allow_direct_fallback: bool = True,
) -> TokenResult:
    """Poll token endpoint until authorized or expired."""
    log = log or _noop_log
    deadline = time.time() + max(expires_in - 5, 30)
    sleep_for = max(interval, 1)
    net_streak = 0
    max_net_streak = 20
    proxies = normalize_proxy_candidates(proxy, proxy_candidates, max_n=8)
    routes: list[tuple[str | None, bool]] = []
    # token poll: prefer direct first (same reason as device-code)
    if allow_direct_fallback:
        routes.append((None, True))
    for p in proxies:
        routes.append((p, False))
    if not routes:
        routes.append((None, True))
    route_i = 0

    while time.time() < deadline:
        if cancel and cancel():
            raise OAuthDeviceError("cancelled")
        route, force_direct = routes[min(route_i, len(routes) - 1)]
        label = _safe_proxy_label(route, force_direct=force_direct)
        try:
            status, body = _post_form(
                TOKEN_URL,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": client_id,
                },
                timeout=timeout,
                proxy=route,
                force_direct=force_direct,
                retries=1,
                retry_sleep=1.0,
            )
            net_streak = 0
        except BaseException as e:  # noqa: BLE001
            if not _is_transient_net_error(e):
                raise
            net_streak += 1
            if route_i + 1 < len(routes):
                route_i += 1
                nxt_label = _safe_proxy_label(routes[route_i][0], force_direct=routes[route_i][1])
                log(f"oauth poll transport error on {label}; rotate route -> {nxt_label}: {e}")
                continue
            wait = min(sleep_for + min(net_streak, 5), 20)
            log(
                f"oauth poll network blip ({net_streak}/{max_net_streak}) route={label}: {e} "
                f"— retry in {wait}s"
            )
            if net_streak >= max_net_streak:
                raise OAuthDeviceError(
                    f"device auth aborted after {net_streak} network errors: {e}"
                ) from e
            time.sleep(wait)
            continue

        if status == 200 and isinstance(body, dict) and body.get("access_token"):
            access = str(body["access_token"]).strip()
            refresh = str(body.get("refresh_token") or "").strip()
            if not refresh:
                raise OAuthDeviceError("token response missing refresh_token")
            return TokenResult(
                access_token=access,
                refresh_token=refresh,
                id_token=(str(body["id_token"]).strip() if body.get("id_token") else None),
                token_type=str(body.get("token_type") or "Bearer"),
                expires_in=int(body.get("expires_in") or 21600),
                raw=body,
            )

        err = ""
        desc = ""
        if isinstance(body, dict):
            err = str(body.get("error") or "")
            desc = str(body.get("error_description") or "")
        if err in ("authorization_pending", "slow_down"):
            if err == "slow_down":
                sleep_for = min(sleep_for + 5, 30)
            log(f"oauth poll: {err} (sleep {sleep_for}s)")
            time.sleep(sleep_for)
            continue
        if err in ("expired_token", "access_denied"):
            raise OAuthDeviceError(f"device auth failed: {err}: {desc}")
        if status == 400 and err:
            raise OAuthDeviceError(f"device auth token error: {err}: {desc or body}")
        if status >= 500 or status in (502, 503, 504) or not isinstance(body, dict):
            net_streak += 1
            if route_i + 1 < len(routes):
                route_i += 1
                log(f"oauth poll soft HTTP {status} on {label}; rotate route")
                continue
            wait = min(sleep_for + 2, 20)
            log(f"oauth poll soft HTTP {status}: {body!r} — retry in {wait}s")
            if net_streak >= max_net_streak:
                raise OAuthDeviceError(
                    f"device auth aborted after soft HTTP failures status={status}"
                )
            time.sleep(wait)
            continue
        log(f"oauth poll unexpected HTTP {status}: {body!r}")
        time.sleep(sleep_for)
    raise OAuthDeviceError("device auth timed out waiting for user approval")
