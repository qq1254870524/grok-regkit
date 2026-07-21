"""Resolve outbound proxy for CPA mint HTTP + browser.

Priority (highest first):
  1. explicit argument (unless force_direct)
  2. thread-local runtime pin (set_runtime_proxy)
  3. environment https_proxy / HTTPS_PROXY / http_proxy / HTTP_PROXY

Thread-local pin avoids cross-talk when multiple mint workers run with
different proxies in the same process.

18r44 CPA fix:
  * FORCE_DIRECT / force_direct=True truly bypasses runtime + env proxies
  * is_proxy_transport_error detects SOCKS reject / curl 97 etc.
  * normalize_proxy_candidates builds rotate list for mint retries
"""

from __future__ import annotations

import os
import threading
from typing import Any, Iterable
from urllib.parse import urlparse

_thread = threading.local()

# Sentinel for true direct (no proxy, ignore runtime/env).
FORCE_DIRECT = "__direct__"


def set_runtime_proxy(proxy: str | None) -> None:
    """Pin proxy for the *current thread*. Empty clears pin."""
    p = (proxy or "").strip()
    if p in ("", FORCE_DIRECT, "direct", "none", "off", "false", "0"):
        _thread.proxy = None
        return
    _thread.proxy = p


def get_runtime_proxy() -> str | None:
    return getattr(_thread, "proxy", None)


def is_force_direct(value: Any) -> bool:
    if value is None:
        return False
    if value is FORCE_DIRECT:
        return True
    s = str(value).strip().lower()
    return s in (FORCE_DIRECT, "direct", "none", "off", "false", "0", "no-proxy", "noproxy")


def resolve_proxy(
    explicit: str | None = None,
    *,
    force_direct: bool = False,
    allow_runtime: bool = True,
    allow_env: bool = True,
) -> str:
    """Resolve proxy URL. force_direct=True always returns empty string."""
    if force_direct or is_force_direct(explicit):
        return ""
    cands: list[str] = []
    if explicit is not None:
        cands.append(str(explicit).strip())
    if allow_runtime:
        cands.append((get_runtime_proxy() or "").strip())
    if allow_env:
        cands.extend(
            [
                (os.environ.get("https_proxy") or "").strip(),
                (os.environ.get("HTTPS_PROXY") or "").strip(),
                (os.environ.get("http_proxy") or "").strip(),
                (os.environ.get("HTTP_PROXY") or "").strip(),
            ]
        )
    for cand in cands:
        if cand and not is_force_direct(cand):
            return cand
    return ""


def proxy_for_chromium(proxy: str) -> str:
    """Chromium --proxy-server cannot embed user:pass; host:port only."""
    p = (proxy or "").strip()
    if not p or is_force_direct(p):
        return ""
    u = urlparse(p if "://" in p else f"http://{p}")
    host = u.hostname or ""
    if not host:
        return ""
    port = u.port or (443 if (u.scheme or "http") == "https" else 80)
    scheme = u.scheme or "http"
    return f"{scheme}://{host}:{port}"


def proxy_log_label(proxy: str | None) -> str:
    """Redact userinfo for logs."""
    if proxy is None or is_force_direct(proxy):
        return "direct" if proxy is not None and is_force_direct(proxy) else ""
    p = (proxy or "").strip()
    if not p:
        return ""
    try:
        u = urlparse(p if "://" in p else f"http://{p}")
        host = u.hostname or "?"
        port = u.port or ""
        auth = "user:***@" if u.username else ""
        return f"{u.scheme or 'http'}://{auth}{host}{(':' + str(port)) if port else ''}"
    except Exception:
        return "(proxy)"


def is_proxy_transport_error(exc: BaseException | str | None) -> bool:
    """True for SOCKS reject / proxy tunnel / curl proxy failures."""
    if exc is None:
        return False
    msg = str(exc).lower()
    needles = (
        "rejected by the socks",
        "socks5 server",
        "socks server",
        "curl: (97)",
        "curl: (7)",
        "curl: (56)",
        "proxy error",
        "proxyerror",
        "tunnel connection failed",
        "cannot connect to proxy",
        "proxy connection",
        "407 proxy",
        "proxy authentication",
        "connection to proxy",
        "failed to connect to proxy",
        "host unreachable",
        "network is unreachable",
        "connection refused",
        "remote end closed",
        "timed out",
        "timeout",
        "temporarily unavailable",
    )
    return any(n in msg for n in needles)


def canonicalize_proxy_url(raw: str | None, *, default_scheme: str = "socks5h") -> str:
    """Normalize host:port:user:pass / URL into a single-quoted proxy URL.

    Ensures socks5h for SOCKS endpoints (curl rejects bare socks5 auth on some nodes)
    and quotes userinfo exactly once so passwords containing # work.
    """
    from urllib.parse import quote, unquote, urlparse

    s = (raw or "").strip()
    if not s or is_force_direct(s):
        return ""
    scheme = (default_scheme or "socks5h").strip() or "socks5h"

    if "://" not in s and "@" not in s and s.count(":") >= 3:
        parts = s.split(":")
        host = parts[0].strip()
        port = parts[1].strip()
        user = parts[2].strip()
        password = ":".join(parts[3:]).strip()
        if not host or not port:
            return ""
        auth = ""
        if user or password:
            auth = f"{quote(user, safe='')}:{quote(password, safe='')}@"
        return f"{scheme}://{auth}{host}:{port}"

    if "://" not in s:
        s = f"{scheme}://{s}"

    u = urlparse(s)
    host = u.hostname or ""
    if not host:
        return s
    port = u.port
    user = unquote(u.username or "") if u.username else ""
    # urlparse may leave %23 encoded in password on some builds — unquote fully
    pw_raw = u.password or ""
    password = unquote(pw_raw)
    if "%23" in password or "%40" in password or "%3A" in password.upper():
        password = unquote(password)
    sch = (u.scheme or scheme).lower()
    if sch in ("socks5", "socks", "socks5h"):
        sch = "socks5h"
    elif not sch:
        sch = scheme
    auth = ""
    if user or password:
        auth = f"{quote(user, safe='')}:{quote(password, safe='')}@"
    if port:
        return f"{sch}://{auth}{host}:{port}"
    return f"{sch}://{auth}{host}"


def normalize_proxy_candidates(
    primary: str | None = None,
    candidates: Iterable[str] | None = None,
    *,
    max_n: int = 8,
) -> list[str]:
    """Unique non-empty proxy list, primary first; URLs canonicalized."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in [primary, *(list(candidates or []))]:
        p = canonicalize_proxy_url(str(raw) if raw is not None else "")
        if not p or is_force_direct(p):
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= max(1, int(max_n)):
            break
    return out

