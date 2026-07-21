# 18r43n: _resolve_runtime_config auto-load admin creds when config empty
# 18r43f: Sub2API verify fail-fast on permanent permission-denied (drain awaiting_pool)
# 18r42d: reject mail_token/wrapper as SSO; collect only session SSO from account files
# 18r35f: treat Sub2API 'SSO already exists; not overwritten' as idempotent success
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sub2API Grok importer: SSO->OAuth and CPA OAuth JSON direct import.
2026-07-19r29k: prefer CPA OAuth after mint; failure queue; pool count log; backfill helper.

2026-07-19r29c: SSO->OAuth 对上游 429/rate-limit 做客户端退避重试（不丢注册结果）。
2026-07-18d: list_accounts returns total; optional native /import/grok-cpa path.

Changelog:
- 2026-07-19r30-lossfixb: dead SSO (GROK_SSO_UNAUTHORIZED) 进 dead 队列，对账不再死循环；
- 2026-07-19r30-lossfix: end-of-job reconcile G2A+hybrid+CPA vs Sub2; pending drain; import retries; prevent pool drift.
- 2026-07-19r29c: import_grok_sso retries up to 5 times on 429 / Too Many Requests /
  GROK_SSO_UPSTREAM_FAILED device-flow rate limits with 5/12/25/40/60s backoff.
- 2026-07-18c: add CPA/CLIProxy OAuth JSON import via POST /api/v1/admin/accounts.
  Accepts Desktop/Grok/cpa style xai-*.json (type=xai, auth_kind=oauth) and maps
  access/refresh/id tokens + JWT claims into Sub2API grok oauth credentials.
  Supports single-file/dir import, email/sub dedupe update, optional SSO fallback
  when JSON includes sso, and never logs token/password plaintext.
- 2026-07-18b: wait briefly before first post-import verify to reduce transient
  permission-denied/forbidden false negatives on brand-new Grok accounts; keep
  create-success as import success by default.
- 2026-07-18a: treat SSO->OAuth account creation as import success. Availability
  testing still runs by default for diagnostics, but verify failure only warns
  and keeps the created account. Optional ``sub2api_require_verify_success``
  restores the old hard-fail gate. Also normalize ``sso=`` prefixes and log
  SSO kind metadata without printing full credentials.
- 2026-07-17b: align with the current Sub2API contract (``sso_tokens`` array),
  accept wrapped and unwrapped import responses, and verify every newly created
  Grok account through the account-test SSE endpoint before reporting it usable.
- 2026-07-17: initial integration for grok-regkit. Logs endpoint/status/account id,
  never logs the admin password, access token, or full SSO credential. A failed
  import is reported to the post-success worker and does not change registration
  success state.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests


_CLIENTS: Dict[str, "Sub2APIClient"] = {}
_CLIENTS_LOCK = threading.Lock()


def _log(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        callback(message)


def _parse_group_ids(value: Any) -> List[int]:
    if isinstance(value, str):
        items: Iterable[Any] = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        items = value
    elif value is None:
        items = []
    else:
        items = [value]
    result: List[int] = []
    for item in items:
        try:
            group_id = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if group_id > 0 and group_id not in result:
            result.append(group_id)
    return result or [3]


def _jwt_exp(token: str) -> float:
    """Read JWT exp without validating the signature; only used as a cache TTL hint."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return float(data.get("exp") or 0)
    except Exception:
        return 0.0


def _jwt_payload_keys(token: str) -> List[str]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        if isinstance(data, dict):
            return sorted(str(k) for k in data.keys())
    except Exception:
        return []
    return []


def _jwt_payload(token: str) -> Dict[str, Any]:
    try:
        payload = str(token or "").split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


DEFAULT_GROK_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
DEFAULT_GROK_BASE_URL = "https://cli-chat-proxy.grok.com/v1"
DEFAULT_GROK_SCOPE = (
    "openid profile email offline_access grok-cli:access api:access "
    "conversations:read conversations:write"
)


def _iso_from_epoch(ts: Any) -> str:
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def parse_cpa_auth_payload(payload: Any, *, source: str = "") -> Dict[str, Any]:
    """Normalize CLIProxy/CPA xai OAuth JSON into Sub2API credentials + meta.

    Expected input shape (Desktop/Grok/cpa or cpa_auths):
      type=xai, auth_kind=oauth, email/sub, access_token/refresh_token/id_token,
      base_url/token_type/expired, optional sso.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError(f"CPA JSON 不是对象 source={source or '-'}")

    access_token = str(payload.get("access_token") or payload.get("accessToken") or "").strip()
    refresh_token = str(payload.get("refresh_token") or payload.get("refreshToken") or "").strip()
    id_token = str(payload.get("id_token") or payload.get("idToken") or "").strip()
    sso = _normalize_sso_token(payload.get("sso") or payload.get("sso_token") or "")
    if not access_token and not refresh_token and not sso:
        raise ValueError(f"CPA JSON 缺少 access_token/refresh_token/sso source={source or '-'}")

    jwt_claims = _jwt_payload(access_token) or _jwt_payload(id_token)
    email = str(payload.get("email") or payload.get("name") or jwt_claims.get("email") or "").strip()
    sub = str(payload.get("sub") or jwt_claims.get("sub") or jwt_claims.get("principal_id") or "").strip()
    client_id = str(
        payload.get("client_id")
        or jwt_claims.get("client_id")
        or jwt_claims.get("aud")
        or DEFAULT_GROK_CLIENT_ID
    ).strip()
    team_id = str(payload.get("team_id") or jwt_claims.get("team_id") or "").strip()
    scope = str(payload.get("scope") or jwt_claims.get("scope") or DEFAULT_GROK_SCOPE).strip()
    token_type = str(payload.get("token_type") or "Bearer").strip() or "Bearer"
    base_url = str(payload.get("base_url") or payload.get("baseUrl") or DEFAULT_GROK_BASE_URL).strip()
    expires_at = str(payload.get("expired") or payload.get("expires_at") or payload.get("expiresAt") or "").strip()
    if not expires_at:
        expires_at = _iso_from_epoch(jwt_claims.get("exp"))

    credentials: Dict[str, Any] = {
        "base_url": base_url or DEFAULT_GROK_BASE_URL,
        "client_id": client_id or DEFAULT_GROK_CLIENT_ID,
        "token_type": token_type,
        "scope": scope or DEFAULT_GROK_SCOPE,
    }
    if email:
        credentials["email"] = email
    if sub:
        credentials["sub"] = sub
    if team_id:
        credentials["team_id"] = team_id
    if expires_at:
        credentials["expires_at"] = expires_at
    if access_token:
        credentials["access_token"] = access_token
    if refresh_token:
        credentials["refresh_token"] = refresh_token
    if id_token:
        credentials["id_token"] = id_token

    if not refresh_token and not sso:
        raise ValueError(f"CPA JSON 缺少 refresh_token，无法创建长期 OAuth 账号 source={source or '-'}")

    auth_kind = str(payload.get("auth_kind") or payload.get("type") or "oauth").strip().lower()
    return {
        "email": email,
        "sub": sub,
        "name": email or (f"grok-{sub[:10]}" if sub else "grok-cpa"),
        "credentials": credentials,
        "sso": sso,
        "auth_kind": auth_kind,
        "source": source,
        "has_access_token": bool(access_token),
        "has_refresh_token": bool(refresh_token),
        "has_id_token": bool(id_token),
        "has_sso": bool(sso),
        "client_id": credentials.get("client_id"),
        "team_id": team_id,
        "expires_at": expires_at,
        "base_url": credentials.get("base_url"),
    }


def parse_cpa_auth_file(path: str | Path) -> Dict[str, Any]:
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8-sig")
    payload = json.loads(raw)
    return parse_cpa_auth_payload(payload, source=str(file_path))


def iter_cpa_auth_files(directory: str | Path) -> List[Path]:
    root_dir = Path(directory)
    if not root_dir.exists():
        raise FileNotFoundError(f"CPA 目录不存在: {root_dir}")
    if root_dir.is_file():
        return [root_dir]
    files = sorted(
        [
            p
            for p in root_dir.rglob("*.json")
            if p.is_file() and not p.name.startswith(".")
        ],
        key=lambda p: p.name.lower(),
    )
    return files


def _normalize_sso_token(raw: str) -> str:
    try:
        from protocol.sso_util import normalize_sso_token

        return normalize_sso_token(raw)
    except Exception:
        text = str(raw or "").strip()
        if not text:
            return ""
        if text.lower().startswith("sso="):
            text = text[4:].strip()
        if text.lower().startswith("sso:"):
            text = text[4:].strip()
        text = text.strip().strip('"').strip("'")
        while text.startswith("-") and text[1:].count(".") == 2:
            text = text[1:].strip()
        return text


def _is_mail_token_blob(raw: str) -> bool:
    try:
        from protocol.sso_util import is_mail_token_blob

        return bool(is_mail_token_blob(raw))
    except Exception:
        s = str(raw or "").strip().lower()
        return s.startswith("b64:") or ('"access_token"' in s and '"refresh_token"' in s)


def _is_session_sso_token(raw: str) -> bool:
    try:
        from protocol.sso_util import is_session_sso

        return bool(is_session_sso(raw))
    except Exception:
        sso = _normalize_sso_token(raw)
        if not sso or _is_mail_token_blob(sso):
            return False
        keys = _jwt_payload_keys(sso)
        return ("session_id" in keys) or (len(sso) < 400 and sso.count(".") == 2)


def _sso_kind_meta(raw: str) -> Dict[str, Any]:
    sso = _normalize_sso_token(raw)
    is_mail = _is_mail_token_blob(sso) or _is_mail_token_blob(raw)
    looks_wrapper = (not is_mail) and (
        ("set-cookie" in sso.lower()) or ("sso=" in sso.lower() and len(sso) > 200)
    )
    keys = [] if is_mail else _jwt_payload_keys(sso)
    is_session = (not is_mail) and (
        ("session_id" in keys) or _is_session_sso_token(sso)
    )
    if looks_wrapper:
        is_session = False
    session_id_prefix = ""
    if is_session:
        try:
            payload = sso.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            sid = str((data or {}).get("session_id") or "").strip()
            if sid:
                session_id_prefix = sid[:12]
        except Exception:
            session_id_prefix = ""
    return {
        "sso_len": len(sso),
        "is_session": bool(is_session),
        "is_wrapper": bool(looks_wrapper),
        "is_mail_token": bool(is_mail),
        "payload_keys": keys,
        "session_id_prefix": session_id_prefix,
    }


def _body_summary(response: requests.Response, limit: int = 500) -> str:
    text = str(response.text or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return bool(default)


class Sub2APIClient:
    def __init__(
        self,
        *,
        base_url: str,
        admin_email: str,
        admin_password: str,
        timeout_sec: float = 60,
        session: Optional[requests.Session] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.admin_email = str(admin_email or "").strip()
        self.admin_password = str(admin_password or "")
        self.timeout_sec = max(10.0, float(timeout_sec or 60))
        self.session = session or requests.Session()
        self.log_callback = log_callback
        self._access_token = ""
        self._token_expires_at = 0.0
        self._ensure_stable_session_headers()
        self._validate_config()

    def _validate_config(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Sub2API 地址无效，必须是 http(s) URL")
        if not self.admin_email:
            raise ValueError("Sub2API 管理员邮箱未配置")
        if not self.admin_password:
            raise ValueError("Sub2API 管理员密码未配置")

    def _request_json(self, method: str, path: str, **kwargs: Any) -> tuple[requests.Response, Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout_sec)
        response = self.session.request(method, url, **kwargs)
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"Sub2API 返回非 JSON status={response.status_code} body={_body_summary(response)}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Sub2API JSON 结构无效 status={response.status_code}")
        return response, payload


    def _ensure_stable_session_headers(self) -> None:
        """Keep a stable browser-like UA so Sub2API session binding does not thrash."""
        headers = getattr(self.session, "headers", None)
        if headers is None:
            return
        ua = str(headers.get("User-Agent") or headers.get("user-agent") or "").strip()
        if not ua or ua.lower().startswith("python-requests"):
            headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36 grok-regkit-sub2api"
            )
        headers.setdefault("Accept", "application/json, text/plain, */*")
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")

    def invalidate_auth(self, *, reset_session: bool = False, reason: str = "") -> None:
        """Drop cached token; optionally rebuild Session after fingerprint mismatch."""
        self._access_token = ""
        self._token_expires_at = 0.0
        if reset_session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = requests.Session()
            self._ensure_stable_session_headers()
        if reason:
            _log(self.log_callback, f"[*] Sub2API invalidate_auth reason={reason} reset_session={int(bool(reset_session))}")

    @staticmethod
    def _is_auth_failure(status_code: int, detail: Any = None) -> bool:
        if int(status_code or 0) == 401:
            return True
        text = str(detail or "").lower()
        return (
            "fingerprint" in text
            or "please login again" in text
            or "unauthorized" in text
            or "token is invalid" in text
            or "token expired" in text
        )

    def login(self, *, force: bool = False) -> str:
        now = time.time()
        if not force and self._access_token and self._token_expires_at > now + 30:
            return self._access_token
        _log(self.log_callback, f"[*] Sub2API 登录开始 base={self.base_url} email={self.admin_email}")
        response, payload = self._request_json(
            "POST",
            "/api/v1/auth/login",
            json={"email": self.admin_email, "password": self.admin_password},
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        token = str(data.get("access_token") or "").strip()
        if response.status_code >= 400 or int(payload.get("code", -1)) != 0 or not token:
            detail = payload.get("message") or payload.get("msg") or payload.get("error") or _body_summary(response)
            if self._is_auth_failure(response.status_code, detail):
                self.invalidate_auth(reset_session=True, reason=f"login_fail status={response.status_code}")
            raise RuntimeError(f"Sub2API 登录失败 status={response.status_code} detail={detail}")
        exp = _jwt_exp(token)
        self._access_token = token
        self._token_expires_at = exp if exp > now else now + 600
        ttl = max(0, int(self._token_expires_at - now))
        _log(self.log_callback, f"[+] Sub2API 登录成功 status={response.status_code} token_ttl≈{ttl}s")
        return token

    @staticmethod
    def _payload_data(payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _payload_ok(payload: Dict[str, Any]) -> bool:
        if "code" not in payload:
            return True
        code = payload.get("code")
        return str(code).strip().lower() in {"0", "200", "success"}

    def verify_grok_account(
        self,
        account_id: Any,
        *,
        attempts: int = 2,
        timeout_sec: float = 105,
        retry_delay_sec: float = 3,
    ) -> Dict[str, Any]:
        account_id_text = str(account_id or "").strip()
        if not account_id_text:
            return {"ok": False, "account_id": "", "error": "missing account id", "attempts": 0}

        max_attempts = max(1, int(attempts or 1))
        read_timeout = max(15.0, float(timeout_sec or 105))
        retry_delay = max(0.0, float(retry_delay_sec or 0))
        last_error = "account test returned no final result"
        for attempt in range(1, max_attempts + 1):
            token = self.login(force=False)
            response = None
            saw_start = False
            saw_content = False
            model = ""
            try:
                _log(
                    self.log_callback,
                    f"[*] Sub2API 可用性验证开始 account_id={account_id_text} "
                    f"attempt={attempt}/{max_attempts} timeout={int(read_timeout)}s",
                )
                response = self.session.request(
                    "POST",
                    f"{self.base_url}/api/v1/admin/accounts/{account_id_text}/test",
                    headers={"Authorization": f"Bearer {token}"},
                    json={},
                    stream=True,
                    timeout=(min(15.0, read_timeout), read_timeout),
                )
                if response.status_code == 401:
                    self._access_token = ""
                    self._token_expires_at = 0.0
                    last_error = "admin access token expired during account test"
                    continue
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {_body_summary(response)}"
                    continue

                for raw_line in response.iter_lines(decode_unicode=True):
                    if isinstance(raw_line, bytes):
                        line = raw_line.decode("utf-8", errors="replace")
                    else:
                        line = str(raw_line or "")
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    raw_event = line[5:].strip()
                    if not raw_event or raw_event == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw_event)
                    except Exception:
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("type") or "").strip().lower()
                    if event.get("model"):
                        model = str(event.get("model"))
                    if event_type == "test_start":
                        saw_start = True
                    elif event_type == "content":
                        saw_content = saw_content or bool(event.get("text") or event.get("content"))
                    elif event_type in {"error", "test_error"}:
                        last_error = str(event.get("error") or event.get("message") or "Unknown error")[:500]
                        break
                    elif event_type in {"test_complete", "test_end", "success"}:
                        success = event.get("success", True)
                        if success is True or str(success).strip().lower() in {"1", "true", "yes", "ok"}:
                            _log(
                                self.log_callback,
                                f"[+] Sub2API 可用性验证通过 account_id={account_id_text} "
                                f"model={model or '-'} attempt={attempt}/{max_attempts}",
                            )
                            return {
                                "ok": True,
                                "account_id": account_id,
                                "attempts": attempt,
                                "model": model,
                                "saw_start": saw_start,
                                "saw_content": saw_content,
                            }
                        last_error = str(event.get("error") or event.get("message") or "test_complete success=false")[:500]
                        break
                else:
                    last_error = "account test stream ended without test_complete"
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
                _low = last_error.lower()
                if any(x in _low for x in ("timed out", "timeout", "connection aborted", "connection reset", "remotedisconnected", "read timed out")):
                    # give one more attempt beyond configured max for pure transport blips
                    if attempt >= max_attempts and max_attempts < 5:
                        max_attempts = attempt + 1
                        retry_delay = max(retry_delay, 5.0)
                        read_timeout = min(180.0, read_timeout + 30.0)
                        _log(
                            self.log_callback,
                            f"[*] Sub2API 可用性验证网络超时，延长重试 account_id={account_id_text} "
                            f"next_timeout={int(read_timeout)}s",
                        )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

            hint = ""
            low = str(last_error or "").lower()
            if any(x in low for x in ("forbidden", "permission", "access to the chat endpoint is denied", "denied")):
                hint = "（常见于新号刚入池时上游瞬时拒绝，不等于导入失败；账号通常已创建）"
            _log(
                self.log_callback,
                f"[!] Sub2API 可用性验证未通过 account_id={account_id_text} "
                f"attempt={attempt}/{max_attempts} detail={last_error}{hint}",
            )
            # 18r43f: permanent Grok chat/permission denials never become ok by retry;
            # fail-fast so multi post-success workers are not blocked 105s*N each.
            _err_l = str(last_error or "").lower()
            if any(
                x in _err_l
                for x in (
                    "permission-denied",
                    "access to the chat endpoint is denied",
                    "chat endpoint is denied",
                    "not allowed to use",
                    "account disabled",
                    "account suspended",
                    "invalid_sso",
                    "sso invalid",
                )
            ):
                return {
                    "ok": False,
                    "account_id": account_id,
                    "attempts": attempt,
                    "error": last_error,
                    "permanent": True,
                }
            if attempt < max_attempts and retry_delay > 0:
                time.sleep(retry_delay)

        return {
            "ok": False,
            "account_id": account_id,
            "attempts": max_attempts,
            "error": last_error,
        }

    def list_accounts(
        self,
        *,
        platform: str = "grok",
        search: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "page": max(1, int(page or 1)),
            "page_size": max(1, min(200, int(page_size or 50))),
            "lite": "true",
        }
        if platform:
            params["platform"] = platform
        if search:
            params["search"] = str(search).strip()[:100]
        last_error = "list_accounts failed"
        for attempt in (1, 2):
            token = self.login(force=(attempt == 2))
            response, payload = self._request_json(
                "GET",
                "/api/v1/admin/accounts",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if response.status_code >= 400 or not self._payload_ok(payload):
                detail = payload.get("message") or payload.get("msg") or payload.get("error") or _body_summary(response)
                last_error = f"Sub2API 列表账号失败 status={response.status_code} detail={detail}"
                if attempt == 1 and self._is_auth_failure(response.status_code, detail):
                    self.invalidate_auth(
                        reset_session=True,
                        reason=f"list_accounts 401/fingerprint detail={str(detail)[:160]}",
                    )
                    continue
                raise RuntimeError(last_error)
            data = self._payload_data(payload)
            items = data.get("items") if isinstance(data.get("items"), list) else []
            total = data.get("total")
            if total is None and isinstance(data.get("pagination"), dict):
                total = data.get("pagination", {}).get("total")
            try:
                total_i = int(total) if total is not None else len(items)
            except Exception:
                total_i = len(items)
            return {"items": items, "total": total_i, "raw": data}
        raise RuntimeError(last_error)

    def find_account_by_email_or_sub(
        self,
        *,
        email: str = "",
        sub: str = "",
    ) -> Optional[Dict[str, Any]]:
        email_l = str(email or "").strip().lower()
        sub_l = str(sub or "").strip().lower()
        # One search is enough: prefer email, then sub. Avoid double list calls.
        query = email_l or sub_l
        if not query:
            return None
        try:
            listed = self.list_accounts(platform="grok", search=query, page=1, page_size=50)
        except Exception:
            return None
        for item in listed.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            creds = item.get("credentials") if isinstance(item.get("credentials"), dict) else {}
            item_email = str(creds.get("email") or name or "").strip().lower()
            item_sub = str(creds.get("sub") or "").strip().lower()
            if email_l and item_email == email_l:
                return item
            if sub_l and item_sub == sub_l:
                return item
            if email_l and name == email_l:
                return item
        return None

    def create_or_update_grok_oauth_account(
        self,
        *,
        name: str,
        credentials: Dict[str, Any],
        group_ids: Any = None,
        concurrency: int = 1,
        priority: int = 1,
        update_existing: bool = True,
        existing_account: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        groups = _parse_group_ids(group_ids)
        account_name = str(name or "").strip() or str(credentials.get("email") or credentials.get("sub") or "grok-oauth")
        body_create = {
            "name": account_name,
            "platform": "grok",
            "type": "oauth",
            "credentials": credentials,
            "group_ids": groups,
            "concurrency": max(1, int(concurrency or 1)),
            "priority": int(priority or 1),
            "confirm_mixed_channel_risk": True,
            "auto_pause_on_expired": True,
        }
        for attempt in (1, 2):
            token = self.login(force=(attempt == 2))
            if existing_account and update_existing:
                account_id = existing_account.get("id")
                body_update = {
                    "name": account_name,
                    "type": "oauth",
                    "credentials": credentials,
                    "group_ids": groups,
                    "concurrency": max(1, int(concurrency or 1)),
                    "priority": int(priority or 1),
                    "status": "active",
                    "confirm_mixed_channel_risk": True,
                }
                response, payload = self._request_json(
                    "PUT",
                    f"/api/v1/admin/accounts/{account_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json=body_update,
                )
                action = "update"
            else:
                response, payload = self._request_json(
                    "POST",
                    "/api/v1/admin/accounts",
                    headers={"Authorization": f"Bearer {token}"},
                    json=body_create,
                )
                action = "create"
            if response.status_code == 401 and attempt == 1:
                self._access_token = ""
                self._token_expires_at = 0.0
                continue
            if response.status_code >= 400 or not self._payload_ok(payload):
                detail = payload.get("message") or payload.get("msg") or payload.get("error") or _body_summary(response)
                raise RuntimeError(
                    f"Sub2API OAuth {action} 失败 status={response.status_code} detail={detail}"
                )
            data = self._payload_data(payload)
            account = data if isinstance(data, dict) else {}
            if isinstance(account.get("account"), dict):
                account = account["account"]
            account_id = (
                account.get("id")
                or account.get("account_id")
                or (data.get("id") if isinstance(data, dict) else None)
                or (payload.get("id") if isinstance(payload, dict) else None)
                or (existing_account or {}).get("id")
                or ""
            )
            return {
                "ok": True,
                "action": action,
                "account_id": account_id,
                "account": account,
                "name": account.get("name") or account_name,
            }
        raise RuntimeError("Sub2API OAuth create/update 认证重试失败")

    def import_grok_oauth_credentials(
        self,
        credentials: Dict[str, Any],
        *,
        email: str = "",
        name: str = "",
        group_ids: Any = None,
        concurrency: int = 1,
        priority: int = 1,
        update_existing: bool = True,
        verify_after_import: bool = True,
        require_verify_success: bool = False,
        verify_attempts: int = 2,
        verify_timeout_sec: float = 105,
        verify_retry_delay_sec: float = 3,
    ) -> Dict[str, Any]:
        if not isinstance(credentials, dict) or not credentials:
            raise ValueError("Sub2API OAuth 入池缺少 credentials")
        email_text = str(email or credentials.get("email") or "").strip()
        sub_text = str(credentials.get("sub") or "").strip()
        account_name = str(name or email_text or (f"grok-{sub_text[:10]}" if sub_text else "grok-oauth")).strip()
        existing = None
        if update_existing:
            existing = self.find_account_by_email_or_sub(email=email_text, sub=sub_text)
            if existing:
                _log(
                    self.log_callback,
                    f"[*] Sub2API 发现已存在账号，将更新 credentials "
                    f"email={email_text or '-'} account_id={existing.get('id') or '-'}",
                )
        _log(
            self.log_callback,
            f"[*] Sub2API OAuth 入池开始 email={email_text or account_name} "
            f"endpoint=/api/v1/admin/accounts has_access={int(bool(credentials.get('access_token')))} "
            f"has_refresh={int(bool(credentials.get('refresh_token')))} "
            f"has_id={int(bool(credentials.get('id_token')))} "
            f"client_id={(str(credentials.get('client_id') or '')[:12] + '...') if credentials.get('client_id') else '-'} "
            f"team_id={(str(credentials.get('team_id') or '')[:12] + '...') if credentials.get('team_id') else '-'}",
        )
        created = self.create_or_update_grok_oauth_account(
            name=account_name,
            credentials=credentials,
            group_ids=group_ids,
            concurrency=concurrency,
            priority=priority,
            update_existing=update_existing,
            existing_account=existing,
        )
        account_id = created.get("account_id")
        _log(
            self.log_callback,
            f"[+] Sub2API OAuth 账号已{created.get('action')} account_id={account_id or '-'} "
            f"name={created.get('name') or account_name}",
        )
        verification: Dict[str, Any]
        if verify_after_import:
            settle_sec = max(0.0, min(8.0, float(verify_retry_delay_sec or 0) + 2.0))
            if settle_sec > 0:
                _log(
                    self.log_callback,
                    f"[*] Sub2API OAuth 入池后等待 {settle_sec:.1f}s 再做可用性验证 "
                    f"account_id={account_id or '-'}",
                )
                time.sleep(settle_sec)
            verification = self.verify_grok_account(
                account_id,
                attempts=verify_attempts,
                timeout_sec=verify_timeout_sec,
                retry_delay_sec=verify_retry_delay_sec,
            )
            if not verification.get("ok"):
                warn = (
                    f"[!] Sub2API OAuth 账号已{created.get('action')}，可用性验证未通过(账号已入池,仅观察) "
                    f"account_id={account_id or '-'} detail={verification.get('error') or 'unknown error'} "
                    f"(账号已保留；仅 require_verify_success=true 才算入池失败)"
                )
                _log(self.log_callback, warn)
                if require_verify_success:
                    raise RuntimeError(
                        f"Sub2API 已{created.get('action')} account_id={account_id or '-'}，但可用性验证失败: "
                        f"{verification.get('error') or 'unknown error'}"
                    )
        else:
            verification = {"ok": None, "skipped": True, "account_id": account_id}
            _log(
                self.log_callback,
                f"[!] Sub2API account_id={account_id or '-'} 已{created.get('action')}，但配置为跳过可用性验证",
            )
        usable = verification.get("ok")
        if usable is True:
            _log(
                self.log_callback,
                f"[+] Sub2API OAuth 入池可用 email={email_text or account_name} account_id={account_id or '-'}",
            )
        elif usable is False:
            _log(
                self.log_callback,
                f"[+] Sub2API OAuth 入池成功(创建/更新完成/可用性待观察) email={email_text or account_name} "
                f"account_id={account_id or '-'}",
            )
        else:
            _log(
                self.log_callback,
                f"[+] Sub2API OAuth 入池成功(已{created.get('action')}/未验证) email={email_text or account_name} "
                f"account_id={account_id or '-'}",
            )
        return {
            "ok": True,
            "usable": usable,
            "action": created.get("action"),
            "account_id": account_id,
            "verification": verification,
            "email": email_text,
            "sub": sub_text,
            "name": created.get("name") or account_name,
        }

    def import_cpa_file(
        self,
        path: str | Path,
        *,
        group_ids: Any = None,
        concurrency: int = 1,
        priority: int = 1,
        update_existing: bool = True,
        allow_sso_fallback: bool = True,
        verify_after_import: bool = True,
        require_verify_success: bool = False,
        verify_attempts: int = 2,
        verify_timeout_sec: float = 105,
        verify_retry_delay_sec: float = 3,
    ) -> Dict[str, Any]:
        parsed = parse_cpa_auth_file(path)
        source = parsed.get("source") or str(path)
        _log(
            self.log_callback,
            f"[*] CPA 文件解析完成 file={Path(source).name} email={parsed.get('email') or '-'} "
            f"sub={(str(parsed.get('sub') or '')[:12] + '...') if parsed.get('sub') else '-'} "
            f"has_access={int(bool(parsed.get('has_access_token')))} "
            f"has_refresh={int(bool(parsed.get('has_refresh_token')))} "
            f"has_sso={int(bool(parsed.get('has_sso')))}",
        )
        if parsed.get("has_refresh_token") or parsed.get("has_access_token"):
            result = self.import_grok_oauth_credentials(
                parsed["credentials"],
                email=str(parsed.get("email") or ""),
                name=str(parsed.get("name") or ""),
                group_ids=group_ids,
                concurrency=concurrency,
                priority=priority,
                update_existing=update_existing,
                verify_after_import=verify_after_import,
                require_verify_success=require_verify_success,
                verify_attempts=verify_attempts,
                verify_timeout_sec=verify_timeout_sec,
                verify_retry_delay_sec=verify_retry_delay_sec,
            )
            result["source"] = source
            result["mode"] = "oauth_credentials"
            return result
        if allow_sso_fallback and parsed.get("sso"):
            result = self.import_grok_sso(
                str(parsed.get("sso") or ""),
                email=str(parsed.get("email") or ""),
                group_ids=group_ids,
                concurrency=concurrency,
                priority=priority,
                verify_after_import=verify_after_import,
                require_verify_success=require_verify_success,
                verify_attempts=verify_attempts,
                verify_timeout_sec=verify_timeout_sec,
                verify_retry_delay_sec=verify_retry_delay_sec,
            )
            result["source"] = source
            result["mode"] = "sso_fallback"
            return result
        raise ValueError(f"CPA 文件无法导入（无 OAuth token 且无 sso）: {Path(source).name}")

    def import_cpa_dir(
        self,
        directory: str | Path,
        *,
        group_ids: Any = None,
        concurrency: int = 1,
        priority: int = 1,
        update_existing: bool = True,
        allow_sso_fallback: bool = True,
        verify_after_import: bool = False,
        require_verify_success: bool = False,
        verify_attempts: int = 1,
        verify_timeout_sec: float = 105,
        verify_retry_delay_sec: float = 3,
        limit: int = 0,
        stop_on_error: bool = False,
    ) -> Dict[str, Any]:
        files = iter_cpa_auth_files(directory)
        if limit and int(limit) > 0:
            files = files[: int(limit)]
        summary = {
            "ok": True,
            "directory": str(directory),
            "total": len(files),
            "imported": 0,
            "updated": 0,
            "created": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "errors": [],
        }
        _log(
            self.log_callback,
            f"[*] Sub2API CPA 目录导入开始 dir={directory} files={len(files)} "
            f"verify={int(bool(verify_after_import))} update_existing={int(bool(update_existing))}",
        )
        for idx, file_path in enumerate(files, 1):
            try:
                result = self.import_cpa_file(
                    file_path,
                    group_ids=group_ids,
                    concurrency=concurrency,
                    priority=priority,
                    update_existing=update_existing,
                    allow_sso_fallback=allow_sso_fallback,
                    verify_after_import=verify_after_import,
                    require_verify_success=require_verify_success,
                    verify_attempts=verify_attempts,
                    verify_timeout_sec=verify_timeout_sec,
                    verify_retry_delay_sec=verify_retry_delay_sec,
                )
                action = str(result.get("action") or "")
                if action == "update":
                    summary["updated"] += 1
                else:
                    summary["created"] += 1
                summary["imported"] += 1
                summary["results"].append(
                    {
                        "file": file_path.name,
                        "ok": True,
                        "action": action or result.get("mode"),
                        "account_id": result.get("account_id"),
                        "email": result.get("email") or "",
                        "usable": result.get("usable"),
                    }
                )
                _log(
                    self.log_callback,
                    f"[+] CPA 导入进度 {idx}/{len(files)} file={file_path.name} "
                    f"account_id={result.get('account_id') or '-'} action={action or result.get('mode')}",
                )
            except Exception as exc:
                summary["failed"] += 1
                err = f"{type(exc).__name__}: {str(exc)[:300]}"
                summary["errors"].append({"file": file_path.name, "error": err})
                summary["results"].append({"file": file_path.name, "ok": False, "error": err})
                _log(
                    self.log_callback,
                    f"[!] CPA 导入失败 {idx}/{len(files)} file={file_path.name} detail={err}",
                )
                if stop_on_error:
                    summary["ok"] = False
                    break
        _log(
            self.log_callback,
            f"[*] Sub2API CPA 目录导入结束 total={summary['total']} imported={summary['imported']} "
            f"created={summary['created']} updated={summary['updated']} failed={summary['failed']}",
        )
        if summary["total"] > 0 and summary["imported"] == 0:
            summary["ok"] = False
        elif summary["imported"] > 0:
            summary["ok"] = True
        return summary

    def import_grok_sso(
        self,
        sso_token: str,
        *,
        email: str = "",
        group_ids: Any = None,
        concurrency: int = 1,
        priority: int = 1,
        verify_after_import: bool = True,
        require_verify_success: bool = False,
        verify_attempts: int = 2,
        verify_timeout_sec: float = 105,
        verify_retry_delay_sec: float = 3,
    ) -> Dict[str, Any]:
        sso = _normalize_sso_token(sso_token)
        if not sso:
            raise ValueError("Sub2API 入池缺少 Grok SSO")
        sso_meta = _sso_kind_meta(sso)
        if sso_meta.get("is_mail_token") or _is_mail_token_blob(sso_token):
            raise ValueError(
                "拒绝导入邮箱 mail_token（Outlook/AOL access/refresh）作为 Grok SSO；"
                "请使用 accounts_reregistered_*/accounts_pending_sso_recovered_* 中的 session SSO，"
                "或先跑「二次补 SSO」产出 email----password----session_sso"
            )
        if not sso_meta.get("is_session") and sso_meta.get("is_wrapper"):
            raise ValueError(
                "拒绝导入 wrapper SSO（config.token/success_url）；需要 materialize 后的 session SSO"
            )
        if not sso_meta.get("is_session"):
            raise ValueError(
                f"拒绝导入非 session SSO sso_len={sso_meta.get('sso_len')} "
                f"keys={sso_meta.get('payload_keys')}"
            )
        groups = _parse_group_ids(group_ids)
        name = str(email or "").strip() or f"grok-{hashlib.sha256(sso.encode()).hexdigest()[:10]}"
        body = {
            # Current Sub2API contract is plural even for one credential.
            "sso_tokens": [sso],
            "name": name,
            "group_ids": groups,
            "concurrency": max(1, int(concurrency or 1)),
            "priority": int(priority or 1),
        }
        _log(
            self.log_callback,
            f"[*] Sub2API 入池开始 email={name} endpoint=/api/v1/admin/grok/sso-to-oauth "
            f"groups={groups} sso_len={sso_meta['sso_len']} is_session={int(bool(sso_meta['is_session']))} "
            f"is_wrapper={int(bool(sso_meta['is_wrapper']))} payload_keys={sso_meta['payload_keys']} "
            f"session_id_prefix={sso_meta['session_id_prefix'] or '-'}",
        )
        max_attempts = 5
        rate_backoff = (5.0, 12.0, 25.0, 40.0, 60.0)
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            token = self.login(force=(attempt > 1 and "401" in last_error))
            response, payload = self._request_json(
                "POST",
                "/api/v1/admin/grok/sso-to-oauth",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            payload_code = payload.get("code")
            payload_message = payload.get("message") or payload.get("msg") or payload.get("error") or ""
            if response.status_code == 401 and attempt < max_attempts:
                last_error = "401"
                _log(self.log_callback, f"[!] Sub2API access token 已失效，重新登录后重试 attempt={attempt}/{max_attempts}")
                self._access_token = ""
                self._token_expires_at = 0.0
                continue
            if response.status_code >= 400 or not self._payload_ok(payload):
                detail = str(payload_message or _body_summary(response) or "")
                last_error = detail
                rate_hit = (
                    response.status_code == 429
                    or "429" in detail
                    or "too many" in detail.lower()
                    or "rate" in detail.lower()
                )
                if rate_hit and attempt < max_attempts:
                    delay = rate_backoff[min(attempt - 1, len(rate_backoff) - 1)]
                    _log(
                        self.log_callback,
                        f"[!] Sub2API 入池上游限流/HTTP失败，{delay:.0f}s 后重试 "
                        f"attempt={attempt}/{max_attempts} status={response.status_code} detail={detail[:220]}",
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Sub2API 入池请求失败 status={response.status_code} code={payload_code!r} "
                    f"detail={detail}"
                )
            data = self._payload_data(payload)
            created = data.get("created") if isinstance(data.get("created"), list) else []
            failed = data.get("failed") if isinstance(data.get("failed"), list) else []
            if created:
                item = created[0] if isinstance(created[0], dict) else {}
                account = item.get("account") if isinstance(item.get("account"), dict) else {}
                account_id = account.get("id") or item.get("id") or ""
                account_name = account.get("name") or item.get("name") or name
                _log(
                    self.log_callback,
                    f"[+] Sub2API 账号记录已创建 email={name} account_id={account_id or '-'} "
                    f"name={account_name} status={response.status_code} code={payload_code!r}",
                )
                verification: Dict[str, Any]
                if verify_after_import:
                    # Newly created Grok OAuth accounts can briefly reject chat
                    # with permission-denied/forbidden right after SSO convert.
                    # A short settle delay materially reduces false "unusable".
                    settle_sec = max(0.0, min(8.0, float(verify_retry_delay_sec or 0) + 2.0))
                    if settle_sec > 0:
                        _log(
                            self.log_callback,
                            f"[*] Sub2API 入池后等待 {settle_sec:.1f}s 再做可用性验证 "
                            f"account_id={account_id or '-'}",
                        )
                        time.sleep(settle_sec)
                    verification = self.verify_grok_account(
                        account_id,
                        attempts=verify_attempts,
                        timeout_sec=verify_timeout_sec,
                        retry_delay_sec=verify_retry_delay_sec,
                    )
                    if not verification.get("ok"):
                        warn = (
                            f"[!] Sub2API 账号已创建，可用性验证未通过(账号已入池,仅观察) account_id={account_id or '-'} "
                            f"detail={verification.get('error') or 'unknown error'} "
                            f"(账号已保留；仅 require_verify_success=true 才算入池失败)"
                        )
                        _log(self.log_callback, warn)
                        if require_verify_success:
                            raise RuntimeError(
                                f"Sub2API 已创建 account_id={account_id or '-'}，但可用性验证失败: "
                                f"{verification.get('error') or 'unknown error'}"
                            )
                else:
                    verification = {"ok": None, "skipped": True, "account_id": account_id}
                    _log(
                        self.log_callback,
                        f"[!] Sub2API account_id={account_id or '-'} 已创建，但配置为跳过可用性验证",
                    )
                usable = verification.get("ok")
                if usable is True:
                    _log(
                        self.log_callback,
                        f"[+] Sub2API 入池可用 email={name} account_id={account_id or '-'} name={account_name}",
                    )
                elif usable is False:
                    _log(
                        self.log_callback,
                        f"[+] Sub2API 入池成功(创建完成/可用性待观察) email={name} "
                        f"account_id={account_id or '-'} name={account_name}",
                    )
                else:
                    _log(
                        self.log_callback,
                        f"[+] Sub2API 入池成功(已创建/未验证) email={name} "
                        f"account_id={account_id or '-'} name={account_name}",
                    )
                return {
                    "ok": True,
                    "usable": usable,
                    "created": created,
                    "failed": failed,
                    "account_id": account_id,
                    "verification": verification,
                    "sso_meta": sso_meta,
                }
            if failed:
                item = failed[0] if isinstance(failed[0], dict) else {}
                detail = str(item.get("error") or item.get("message") or "unknown conversion/import failure")
                last_error = detail
                detail_l = detail.lower()
                # 18r35f: upstream returns failed[] with "SSO already exists; not overwritten"
                # when the account is already in Sub2API — treat as success (idempotent import).
                if (
                    "already exists" in detail_l
                    or "not overwritten" in detail_l
                    or "sso already" in detail_l
                    or "duplicate" in detail_l
                ):
                    _log(
                        self.log_callback,
                        f"[+] Sub2API SSO 已在号池(幂等成功) email={name} "
                        f"detail={detail[:220]} status={response.status_code}",
                    )
                    return {
                        "ok": True,
                        "usable": True,
                        "created": [],
                        "failed": failed,
                        "account_id": "",
                        "verification": {"already_exists": True, "detail": detail[:300]},
                        "sso_meta": sso_meta,
                        "already_exists": True,
                    }
                if ("429" in detail or "too many requests" in detail_l) and attempt < max_attempts:
                    delay = rate_backoff[min(attempt - 1, len(rate_backoff) - 1)]
                    _log(
                        self.log_callback,
                        f"[!] Sub2API SSO→OAuth 上游 429/限流，{delay:.0f}s 后重试 "
                        f"attempt={attempt}/{max_attempts} failed.error={detail[:260]}",
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Sub2API SSO→OAuth 转换失败: status={response.status_code} "
                    f"code={payload_code!r} message={payload_message!r} failed.error={detail}"
                )
            last_error = "empty created/failed"
            if attempt < max_attempts:
                delay = rate_backoff[min(attempt - 1, len(rate_backoff) - 1)]
                _log(
                    self.log_callback,
                    f"[!] Sub2API 入池返回空 created/failed，{delay:.0f}s 后重试 "
                    f"attempt={attempt}/{max_attempts} code={payload_code!r} message={payload_message!r}",
                )
                time.sleep(delay)
                continue
            raise RuntimeError(
                f"Sub2API 入池返回 created/failed 均为空 status={response.status_code} "
                f"code={payload_code!r} message={payload_message!r}"
            )
        raise RuntimeError(f"Sub2API 入池重试耗尽 last_error={last_error[:300]}")


def _resolve_runtime_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """18r43n: never run Sub2 import with empty config (admin email missing)."""
    cfg: Dict[str, Any] = dict(config or {})
    if str(cfg.get("sub2api_admin_email") or "").strip() and str(cfg.get("sub2api_admin_password") or ""):
        return cfg
    try:
        import grok_register_ttk as _engine
        try:
            _engine.load_config()
        except Exception:
            pass
        eng = getattr(_engine, "config", None)
        if isinstance(eng, dict):
            merged = {**eng, **{k: v for k, v in cfg.items() if v not in (None, "")}}
            if str(merged.get("sub2api_admin_email") or "").strip():
                return merged
            cfg = merged
    except Exception:
        pass
    for path in (Path(__file__).resolve().parent / "config.json", _project_root() / "config.json"):
        try:
            if path.is_file():
                disk = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(disk, dict):
                    merged = {**disk, **{k: v for k, v in cfg.items() if v not in (None, "")}}
                    if str(merged.get("sub2api_admin_email") or "").strip():
                        return merged
                    cfg = merged
        except Exception:
            continue
    return cfg


def _client_cache_key(config: Dict[str, Any]) -> str:
    raw = "\0".join(
        [
            str(config.get("sub2api_base_url") or "http://127.0.0.1:8080").strip().rstrip("/"),
            str(config.get("sub2api_admin_email") or "").strip(),
            str(config.get("sub2api_admin_password") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_client(
    config: Dict[str, Any],
    log_callback: Optional[Callable[[str], None]] = None,
    *,
    force_new: bool = False,
) -> Sub2APIClient:
    config = _resolve_runtime_config(config)
    key = _client_cache_key(config)
    with _CLIENTS_LOCK:
        client = None if force_new else _CLIENTS.get(key)
        if client is None:
            client = Sub2APIClient(
                base_url=str(config.get("sub2api_base_url") or "http://127.0.0.1:8080"),
                admin_email=str(config.get("sub2api_admin_email") or ""),
                admin_password=str(config.get("sub2api_admin_password") or ""),
                timeout_sec=float(config.get("sub2api_timeout_sec") or 60),
                log_callback=log_callback,
            )
            _CLIENTS[key] = client
        else:
            client.log_callback = log_callback
            try:
                client._ensure_stable_session_headers()
            except Exception:
                pass
    return client


def invalidate_client_cache(config: Optional[Dict[str, Any]] = None) -> None:
    """Drop cached Sub2API client(s). Useful after fingerprint/session revoke."""
    with _CLIENTS_LOCK:
        if not config:
            for c in list(_CLIENTS.values()):
                try:
                    c.invalidate_auth(reset_session=True, reason="cache_clear_all")
                except Exception:
                    pass
            _CLIENTS.clear()
            return
        key = _client_cache_key(config)
        client = _CLIENTS.pop(key, None)
        if client is not None:
            try:
                client.invalidate_auth(reset_session=True, reason="cache_clear_one")
            except Exception:
                pass


def import_grok_sso_to_sub2api(
    sso_token: str,
    *,
    email: str = "",
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    cfg = config or {}
    client = get_client(cfg, log_callback=log_callback)
    return client.import_grok_sso(
        sso_token,
        email=email,
        group_ids=cfg.get("sub2api_group_ids", [3]),
        concurrency=int(cfg.get("sub2api_concurrency") or 1),
        priority=int(cfg.get("sub2api_priority") or 1),
        verify_after_import=_truthy(cfg.get("sub2api_verify_after_add"), default=True),
        require_verify_success=_truthy(cfg.get("sub2api_require_verify_success"), default=False),
        verify_attempts=int(cfg.get("sub2api_verify_attempts") or 2),
        verify_timeout_sec=float(cfg.get("sub2api_verify_timeout_sec") or 105),
        verify_retry_delay_sec=float(cfg.get("sub2api_verify_retry_delay_sec") or 3),
    )


def import_grok_oauth_to_sub2api(
    credentials: Dict[str, Any],
    *,
    email: str = "",
    name: str = "",
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    update_existing: bool = True,
) -> Dict[str, Any]:
    cfg = config or {}
    client = get_client(cfg, log_callback=log_callback)
    return client.import_grok_oauth_credentials(
        credentials,
        email=email,
        name=name,
        group_ids=cfg.get("sub2api_group_ids", [3]),
        concurrency=int(cfg.get("sub2api_concurrency") or 1),
        priority=int(cfg.get("sub2api_priority") or 1),
        update_existing=update_existing,
        verify_after_import=_truthy(cfg.get("sub2api_verify_after_add"), default=True),
        require_verify_success=_truthy(cfg.get("sub2api_require_verify_success"), default=False),
        verify_attempts=int(cfg.get("sub2api_verify_attempts") or 2),
        verify_timeout_sec=float(cfg.get("sub2api_verify_timeout_sec") or 105),
        verify_retry_delay_sec=float(cfg.get("sub2api_verify_retry_delay_sec") or 3),
    )


def import_cpa_file_to_sub2api(
    path: str | Path,
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    update_existing: bool = True,
    allow_sso_fallback: bool = True,
    verify_after_import: Optional[bool] = None,
) -> Dict[str, Any]:
    cfg = config or {}
    client = get_client(cfg, log_callback=log_callback)
    verify = (
        _truthy(cfg.get("sub2api_verify_after_add"), default=True)
        if verify_after_import is None
        else bool(verify_after_import)
    )
    return client.import_cpa_file(
        path,
        group_ids=cfg.get("sub2api_group_ids", [3]),
        concurrency=int(cfg.get("sub2api_concurrency") or 1),
        priority=int(cfg.get("sub2api_priority") or 1),
        update_existing=update_existing,
        allow_sso_fallback=allow_sso_fallback,
        verify_after_import=verify,
        require_verify_success=_truthy(cfg.get("sub2api_require_verify_success"), default=False),
        verify_attempts=int(cfg.get("sub2api_verify_attempts") or 2),
        verify_timeout_sec=float(cfg.get("sub2api_verify_timeout_sec") or 105),
        verify_retry_delay_sec=float(cfg.get("sub2api_verify_retry_delay_sec") or 3),
    )


def import_cpa_dir_to_sub2api(
    directory: str | Path,
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    update_existing: bool = True,
    allow_sso_fallback: bool = True,
    verify_after_import: bool = False,
    limit: int = 0,
    stop_on_error: bool = False,
) -> Dict[str, Any]:
    cfg = config or {}
    client = get_client(cfg, log_callback=log_callback)
    return client.import_cpa_dir(
        directory,
        group_ids=cfg.get("sub2api_group_ids", [3]),
        concurrency=int(cfg.get("sub2api_concurrency") or 1),
        priority=int(cfg.get("sub2api_priority") or 1),
        update_existing=update_existing,
        allow_sso_fallback=allow_sso_fallback,
        verify_after_import=verify_after_import,
        require_verify_success=_truthy(cfg.get("sub2api_require_verify_success"), default=False),
        verify_attempts=int(cfg.get("sub2api_verify_attempts") or 1),
        verify_timeout_sec=float(cfg.get("sub2api_verify_timeout_sec") or 105),
        verify_retry_delay_sec=float(cfg.get("sub2api_verify_retry_delay_sec") or 3),
        limit=limit,
        stop_on_error=stop_on_error,
    )


# ---------------------------------------------------------------------------
# 18r29k: post-success Sub2API prefer CPA OAuth; failure queue; pool counts
# ---------------------------------------------------------------------------

_PENDING_FILE_NAME = "sub2api_import_pending.jsonl"


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _pending_path(config: Optional[Dict[str, Any]] = None) -> Path:
    cfg = config or {}
    raw = str(cfg.get("sub2api_pending_file") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (_project_root() / p)
    return _project_root() / _PENDING_FILE_NAME


def _find_cpa_file_for_email(email: str, config: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    cfg = config or {}
    em = str(email or "").strip().lower()
    if not em:
        return None
    dirs: list[Path] = []
    for key in ("cpa_auth_dir", "sub2api_cpa_import_dir"):
        raw = str(cfg.get(key) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = _project_root() / p
        if p.is_dir():
            dirs.append(p)
    default = _project_root() / "cpa_auths"
    if default.is_dir() and default not in dirs:
        dirs.append(default)
    # common filename patterns
    safe = em.replace("@", "@")  # keep @ for xai-email.json patterns used in this project
    candidates = [
        f"xai-{em}.json",
        f"xai-{em}.cd.json",
        f"{em}.json",
        f"xai-{em.replace('@', '_')}.json",
    ]
    for d in dirs:
        for name in candidates:
            fp = d / name
            if fp.is_file():
                return fp
        # fuzzy: any file containing email
        try:
            for fp in d.glob("*.json"):
                if em in fp.name.lower():
                    return fp
        except Exception:
            pass
    return None


def record_sub2api_import_failure(
    *,
    email: str = "",
    sso: str = "",
    password: str = "",
    error: str = "",
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Append one failed Sub2API import for later backfill (no secrets truncated for local ops)."""
    path = _pending_path(config)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "email": str(email or "").strip(),
        "sso": str(sso or "").strip(),
        "password": str(password or ""),
        "error": str(error or "")[:800],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _log(log_callback, f"[!] Sub2API 失败已写入回填队列: {path.name} email={rec['email']}")


def import_after_success_prefer_cpa(
    sso_token: str,
    *,
    email: str = "",
    password: str = "",
    cpa_result: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Prefer CPA OAuth JSON (just minted) then fall back to SSO->OAuth conversion.

    Retries each path to close races where G2A already has the SSO but Sub2 briefly
    fails (429 / transient / CPA file not flushed yet).
    """
    cfg = config or {}
    em = str(email or "").strip()
    try:
        max_tries = max(1, int(cfg.get("sub2api_import_max_tries") or 3))
    except (TypeError, ValueError):
        max_tries = 3
    try:
        gap = float(cfg.get("sub2api_import_retry_gap_sec") or 2.5)
    except (TypeError, ValueError):
        gap = 2.5

    def _resolve_cpa_path() -> Optional[Path]:
        if isinstance(cpa_result, dict):
            for k in ("path", "auth_path", "file", "out_path"):
                v = cpa_result.get(k)
                if v and Path(str(v)).is_file():
                    return Path(str(v))
            data = cpa_result.get("data") if isinstance(cpa_result.get("data"), dict) else {}
            for k in ("path", "auth_path", "file"):
                v = data.get(k) if data else None
                if v and Path(str(v)).is_file():
                    return Path(str(v))
        return _find_cpa_file_for_email(em, cfg)

    errors: list[str] = []
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_tries + 1):
        cpa_path = _resolve_cpa_path()
        if cpa_path is not None:
            _log(
                log_callback,
                f"[*] Sub2API 优先 CPA OAuth 导入 email={em} file={cpa_path.name} "
                f"attempt={attempt}/{max_tries}",
            )
            try:
                return import_cpa_file_to_sub2api(
                    cpa_path,
                    config=cfg,
                    log_callback=log_callback,
                    update_existing=_truthy(cfg.get("sub2api_cpa_update_existing"), default=True),
                    allow_sso_fallback=False,
                    verify_after_import=_truthy(cfg.get("sub2api_verify_after_add"), default=True),
                )
            except Exception as exc:
                last_exc = exc
                errors.append(f"cpa_oauth#{attempt}:{exc}")
                _log(log_callback, f"[!] Sub2API CPA OAuth 导入失败 attempt={attempt}: {exc}")
        else:
            _log(
                log_callback,
                f"[*] Sub2API 无 CPA 文件，走 SSO→OAuth email={em} attempt={attempt}/{max_tries}",
            )

        _log(
            log_callback,
            f"[*] Sub2API 回退/主路径 SSO→OAuth 导入 email={em} attempt={attempt}/{max_tries}",
        )
        try:
            return import_grok_sso_to_sub2api(
                sso_token,
                email=em,
                config=cfg,
                log_callback=log_callback,
            )
        except Exception as exc:
            last_exc = exc
            errors.append(f"sso_oauth#{attempt}:{exc}")
            detail = str(exc)
            unauthorized = (
                "GROK_SSO_UNAUTHORIZED" in detail or "invalid or expired" in detail.lower()
            )
            _log(log_callback, f"[!] Sub2API SSO→OAuth 失败 attempt={attempt}: {exc}")
            if unauthorized and cpa_path is None and attempt >= 2:
                break
            if attempt < max_tries:
                time.sleep(gap * attempt)
                continue
            break

    joined = " | ".join(errors) if errors else (str(last_exc) if last_exc else "unknown")
    raise RuntimeError(joined) from last_exc


def log_pool_counts(
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    email: str = "",
) -> Dict[str, Any]:
    """Best-effort local/g2a-remote/sub2api counts for ops visibility (no secrets)."""
    cfg = config or {}
    out: Dict[str, Any] = {"email": email}
    try:
        tok_path = _project_root() / "token.json"
        if tok_path.is_file():
            raw = json.loads(tok_path.read_text(encoding="utf-8"))
            pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
            items = raw.get(pool) if isinstance(raw, dict) else None
            out["g2a_local"] = len(items) if isinstance(items, list) else 0
    except Exception as exc:
        out["g2a_local_err"] = str(exc)[:120]
    try:
        cpa_dir = Path(str(cfg.get("cpa_auth_dir") or "cpa_auths"))
        if not cpa_dir.is_absolute():
            cpa_dir = _project_root() / cpa_dir
        out["cpa_files"] = len(list(cpa_dir.glob("*.json"))) if cpa_dir.is_dir() else 0
    except Exception as exc:
        out["cpa_err"] = str(exc)[:120]
    try:
        client = get_client(cfg, log_callback=None)
        token = client.login(force=False)
        # paginate lightly
        total = None
        resp, payload = client._request_json(
            "GET",
            "/api/v1/admin/accounts?page=1&page_size=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = client._payload_data(payload) if isinstance(payload, dict) else {}
        if isinstance(data, dict) and data.get("total") is not None:
            total = int(data.get("total") or 0)
        out["sub2api_total"] = total
    except Exception as exc:
        out["sub2api_err"] = str(exc)[:160]
    _log(
        log_callback,
        f"[*] 池计数对照 email={email or '-'} g2a_local={out.get('g2a_local', '?')} "
        f"cpa_files={out.get('cpa_files', '?')} sub2api={out.get('sub2api_total', out.get('sub2api_err', '?'))}",
    )
    return out




def _collect_g2a_email_sso(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    cfg = config or {}
    tok_path = _project_root() / "token.json"
    if not tok_path.is_file():
        return {}
    raw = json.loads(tok_path.read_text(encoding="utf-8"))
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    entries = raw.get(pool) if isinstance(raw, dict) else []
    email_sso: Dict[str, str] = {}
    if not isinstance(entries, list):
        return {}
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        em = str(
            ent.get("email")
            or ent.get("mail")
            or ent.get("account")
            or ent.get("note")
            or ""
        ).strip().lower()
        sso = str(ent.get("token") or ent.get("sso") or ent.get("value") or "").strip()
        if not em or "@" not in em:
            blob = json.dumps(ent, ensure_ascii=False)
            m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", blob)
            if m:
                em = m.group(0).lower()
        if not sso:
            for k, v in ent.items():
                if isinstance(v, str) and len(v) > 40 and ("eyJ" in v or len(v) > 80):
                    sso = v
                    break
        if em and "@" in em and sso:
            email_sso[em] = sso
    return email_sso


def _collect_hybrid_email_sso() -> Dict[str, str]:
    out: Dict[str, str] = {}
    root = _project_root()
    patterns = (
        "accounts_hybrid*.txt",
        "accounts_reregistered_*.txt",
        "accounts_pending_sso_recovered_*.txt",
        "accounts_cli.txt",
    )
    paths: list[Path] = []
    for pat in patterns:
        paths.extend(root.glob(pat))
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for line in lines:
            parts = line.strip().split("----")
            if len(parts) < 3 or "@" not in parts[0]:
                continue
            em = parts[0].strip().lower()
            # never take pending reason / mail_token as SSO
            sso = ""
            for part in parts[2:]:
                if _is_session_sso_token(part):
                    sso = _normalize_sso_token(part)
                    break
            if em and sso:
                out[em] = sso
    return out


def _collect_cpa_email_files(config: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
    cfg = config or {}
    cpa_dir = Path(str(cfg.get("cpa_auth_dir") or "cpa_auths"))
    if not cpa_dir.is_absolute():
        cpa_dir = _project_root() / cpa_dir
    out: Dict[str, Path] = {}
    if not cpa_dir.is_dir():
        return out
    for path in cpa_dir.glob("*.json"):
        em = ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                em = str(data.get("email") or data.get("name") or "").strip().lower()
        except Exception:
            em = ""
        if not em or "@" not in em:
            m = re.search(r"xai-(.+?)\.json$", path.name, re.I)
            if m:
                em = m.group(1).strip().lower()
        if em and "@" in em:
            out[em] = path
    return out


def _list_sub2_account_names(
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> set[str]:
    client = get_client(config or {}, log_callback=log_callback)
    token = client.login(force=False)
    existing: set[str] = set()
    page = 1
    while page < 100:
        _resp, payload = client._request_json(
            "GET",
            f"/api/v1/admin/accounts?page={page}&page_size=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = client._payload_data(payload) if isinstance(payload, dict) else {}
        items = []
        if isinstance(data, dict):
            items = data.get("items") or data.get("list") or data.get("accounts") or []
        elif isinstance(data, list):
            items = data
        for a in items:
            if isinstance(a, dict):
                existing.add(str(a.get("name") or a.get("email") or "").strip().lower())
        if not items or len(items) < 100:
            break
        page += 1
    return existing


def process_sub2api_pending_file(
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    limit: int = 0,
) -> Dict[str, Any]:
    """Retry failed Sub2 imports recorded in sub2api_import_pending.jsonl."""
    cfg = _resolve_runtime_config(config)
    path = _pending_path(cfg)
    summary: Dict[str, Any] = {"path": str(path), "ok": 0, "fail": 0, "skipped": 0, "remaining": 0}
    if not path.is_file():
        return summary
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as exc:
        _log(log_callback, f"[!] 读取 Sub2API pending 失败: {exc}")
        return summary
    remaining: list[str] = []
    processed = 0
    for ln in lines:
        if limit and processed >= limit:
            remaining.append(ln)
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            remaining.append(ln)
            summary["skipped"] += 1
            continue
        em = str(rec.get("email") or "").strip()
        sso = str(rec.get("sso") or "").strip()
        password = str(rec.get("password") or "")
        if not em and not sso:
            summary["skipped"] += 1
            continue
        processed += 1
        try:
            import_after_success_prefer_cpa(
                sso,
                email=em,
                password=password,
                cpa_result=None,
                config=cfg,
                log_callback=log_callback,
            )
            summary["ok"] += 1
            _log(log_callback, f"[+] Sub2API pending 回填成功 email={em}")
        except Exception as exc:
            summary["fail"] += 1
            detail = str(exc)
            rec["error"] = detail[:800]
            rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            dead_sso = (
                "GROK_SSO_UNAUTHORIZED" in detail
                or "invalid or expired" in detail.lower()
            )
            if dead_sso:
                dead_path = _project_root() / "sub2api_import_dead.jsonl"
                rec["dead_reason"] = "GROK_SSO_UNAUTHORIZED"
                with dead_path.open("a", encoding="utf-8") as df:
                    df.write(json.dumps(rec, ensure_ascii=False) + "\n")
                summary.setdefault("dead", 0)
                summary["dead"] = int(summary.get("dead") or 0) + 1
                _log(
                    log_callback,
                    f"[!] Sub2API pending SSO 已失效，移入 dead 队列（需二次补SSO） email={em} err={exc}",
                )
            else:
                remaining.append(json.dumps(rec, ensure_ascii=False))
                _log(log_callback, f"[!] Sub2API pending 回填失败 email={em} err={exc}")
    path.write_text(("\n".join(remaining) + ("\n" if remaining else "")), encoding="utf-8")
    summary["remaining"] = len(remaining)
    _log(
        log_callback,
        f"[*] Sub2API pending 处理结束 ok={summary['ok']} fail={summary['fail']} "
        f"remaining={summary['remaining']}",
    )
    return summary


def reconcile_sub2api_pools(
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    limit: int = 0,
    include_pending_file: bool = True,
) -> Dict[str, Any]:
    """Align Sub2API with G2A / hybrid / CPA sources. Import missing accounts.

    Order per email: CPA OAuth JSON -> SSO from G2A/hybrid.
    Does not delete anything. Safe to run at job end.
    """
    cfg = config or {}
    log = log_callback
    summary: Dict[str, Any] = {
        "g2a": 0,
        "hybrid": 0,
        "cpa": 0,
        "sub2_before": 0,
        "missing": 0,
        "ok": 0,
        "fail": 0,
        "errors": [],
        "pending_file": {},
    }
    if include_pending_file:
        summary["pending_file"] = process_sub2api_pending_file(
            config=cfg, log_callback=log, limit=limit
        )

    g2a = _collect_g2a_email_sso(cfg)
    hybrid = _collect_hybrid_email_sso()
    cpa_map = _collect_cpa_email_files(cfg)
    summary["g2a"] = len(g2a)
    summary["hybrid"] = len(hybrid)
    summary["cpa"] = len(cpa_map)

    email_sso: Dict[str, str] = {}
    email_sso.update(hybrid)
    email_sso.update(g2a)  # g2a preferred over hybrid if both

    existing = _list_sub2_account_names(cfg, log)
    summary["sub2_before"] = len(existing)
    all_emails = sorted(set(email_sso) | set(cpa_map))
    # skip known dead SSO emails (cannot enter Sub2 without fresh SSO/CPA)
    dead_emails: set[str] = set()
    dead_path = _project_root() / "sub2api_import_dead.jsonl"
    if dead_path.is_file():
        for ln in dead_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
                de = str(r.get("email") or "").strip().lower()
                if de:
                    dead_emails.add(de)
            except Exception:
                pass
    missing = [em for em in all_emails if em not in existing and em not in dead_emails]
    summary["missing"] = len(missing)
    summary["dead_skipped"] = len([em for em in all_emails if em not in existing and em in dead_emails])
    if summary["dead_skipped"]:
        _log(log, f"[*] Sub2API 对账跳过 dead SSO {summary['dead_skipped']} 个（需二次补SSO/CPA）")
    _log(
        log,
        f"[*] Sub2API 对账: g2a={summary['g2a']} hybrid={summary['hybrid']} "
        f"cpa={summary['cpa']} sub2={summary['sub2_before']} missing={summary['missing']}",
    )

    for i, em in enumerate(missing, 1):
        if limit and i > limit:
            break
        sso = email_sso.get(em) or ""
        cpa_path = cpa_map.get(em)
        try:
            if cpa_path is not None:
                _log(log, f"[*] 对账补入 CPA email={em} file={cpa_path.name} ({i}/{len(missing)})")
                import_cpa_file_to_sub2api(
                    cpa_path,
                    config=cfg,
                    log_callback=log,
                    update_existing=True,
                    allow_sso_fallback=bool(sso),
                    verify_after_import=_truthy(cfg.get("sub2api_verify_after_add"), default=True),
                )
            elif sso:
                _log(log, f"[*] 对账补入 SSO→OAuth email={em} ({i}/{len(missing)})")
                import_after_success_prefer_cpa(
                    sso, email=em, config=cfg, log_callback=log
                )
            else:
                raise RuntimeError("no cpa file and no sso material")
            summary["ok"] += 1
            _log(log, f"[+] 对账补入成功 email={em}")
            time.sleep(float(cfg.get("sub2api_backfill_gap_sec") or 1.5))
        except Exception as exc:
            summary["fail"] += 1
            summary["errors"].append({"email": em, "error": str(exc)[:300]})
            if sso:
                try:
                    record_sub2api_import_failure(
                        email=em, sso=sso, error=str(exc), config=cfg, log_callback=log
                    )
                except Exception:
                    pass
            _log(log, f"[!] 对账补入失败 email={em} err={exc}")
            time.sleep(float(cfg.get("sub2api_backfill_fail_gap_sec") or 2.0))

    try:
        counts = log_pool_counts(config=cfg, log_callback=log, email="reconcile")
        summary["counts_after"] = counts
    except Exception as exc:
        summary["counts_after_err"] = str(exc)[:160]
    _log(
        log,
        f"[*] Sub2API 对账结束 ok={summary['ok']} fail={summary['fail']} "
        f"missing_was={summary['missing']}",
    )
    return summary



def backfill_missing_sub2api_from_cpa_and_sso(
    *,
    config: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    limit: int = 0,
    prefer_cpa: bool = True,
) -> Dict[str, Any]:
    """Import G2A emails missing from Sub2API using CPA files first, else SSO token."""
    cfg = _resolve_runtime_config(config)
    log = log_callback
    tok_path = _project_root() / "token.json"
    raw = json.loads(tok_path.read_text(encoding="utf-8")) if tok_path.is_file() else {}
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    entries = raw.get(pool) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        entries = []

    # map email -> sso (token.json + accounts*.txt session SSO) 18r43n
    email_sso: Dict[str, str] = {}
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        # grok-regkit local token.json: {token, tags, note=email}
        em = str(
            ent.get("email")
            or ent.get("mail")
            or ent.get("account")
            or ent.get("note")
            or ""
        ).strip().lower()
        sso = str(ent.get("token") or ent.get("sso") or ent.get("value") or "").strip()
        if not em or "@" not in em:
            blob = json.dumps(ent, ensure_ascii=False)
            m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", blob)
            if m:
                em = m.group(0).lower()
        if not sso:
            for k, v in ent.items():
                if isinstance(v, str) and len(v) > 40 and ("eyJ" in v or len(v) > 80):
                    sso = v
                    break
        if em and "@" in em and sso:
            email_sso[em] = sso

    # 18r43n: harvest session SSO from accounts*.txt (not only token.json)
    try:
        from grok_register_ttk import _is_importable_session_sso as _is_sess
    except Exception:
        _is_sess = None  # type: ignore
    for apath in sorted(_project_root().glob("accounts*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            for ln in apath.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = (ln or "").strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split("----")
                if len(parts) < 2:
                    continue
                em = parts[0].strip().lower()
                if "@" not in em:
                    continue
                tok = ""
                for part in reversed(parts):
                    cand = part.strip()
                    if not cand:
                        continue
                    ok = False
                    if _is_sess is not None:
                        try:
                            ok = bool(_is_sess(cand))
                        except Exception:
                            ok = False
                    else:
                        ok = cand.count(".") == 2 and 40 <= len(cand) <= 800
                    if ok:
                        tok = cand
                        break
                if tok:
                    email_sso[em] = tok
        except Exception:
            continue

    client = get_client(cfg, log_callback=log)
    token = client.login(force=True)
    existing: set[str] = set()
    page = 1
    while page < 80:
        resp, payload = client._request_json(
            "GET",
            f"/api/v1/admin/accounts?page={page}&page_size=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = client._payload_data(payload) if isinstance(payload, dict) else {}
        items = []
        if isinstance(data, dict):
            items = data.get("items") or data.get("list") or []
        for a in items:
            if isinstance(a, dict):
                existing.add(str(a.get("name") or a.get("email") or "").strip().lower())
        if not items or len(items) < 100:
            break
        page += 1

    missing = [em for em in sorted(email_sso) if em not in existing]
    _log(log, f"[*] Sub2API 回填: g2a_emails={len(email_sso)} sub2_existing={len(existing)} missing={len(missing)}")
    summary = {"missing": len(missing), "ok": 0, "fail": 0, "errors": []}
    for i, em in enumerate(missing, 1):
        if limit and i > limit:
            break
        try:
            if prefer_cpa:
                res = import_after_success_prefer_cpa(
                    email_sso[em],
                    email=em,
                    cpa_result=None,
                    config=cfg,
                    log_callback=log,
                )
            else:
                res = import_grok_sso_to_sub2api(email_sso[em], email=em, config=cfg, log_callback=log)
            summary["ok"] += 1
            _log(log, f"[+] 回填成功 {i}/{len(missing)} email={em}")
            time.sleep(float(cfg.get("sub2api_backfill_gap_sec") or 2))
        except Exception as exc:
            summary["fail"] += 1
            summary["errors"].append({"email": em, "error": str(exc)[:300]})
            record_sub2api_import_failure(
                email=em, sso=email_sso[em], error=str(exc), config=cfg, log_callback=log
            )
            _log(log, f"[!] 回填失败 {i}/{len(missing)} email={em} err={exc}")
            time.sleep(float(cfg.get("sub2api_backfill_fail_gap_sec") or 5))
    _log(log, f"[*] Sub2API 回填结束 ok={summary['ok']} fail={summary['fail']} missing_was={summary['missing']}")
    return summary

