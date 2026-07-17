#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sub2API Grok importer: SSO->OAuth and CPA OAuth JSON direct import.

2026-07-18d: list_accounts returns total; optional native /import/grok-cpa path.

Changelog:
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
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.lower().startswith("sso="):
        text = text[4:].strip()
    if text.lower().startswith("sso:"):
        text = text[4:].strip()
    return text.strip().strip('"').strip("'")


def _sso_kind_meta(raw: str) -> Dict[str, Any]:
    sso = _normalize_sso_token(raw)
    looks_wrapper = ("set-cookie" in sso.lower()) or ("sso=" in sso.lower() and len(sso) > 200)
    keys = _jwt_payload_keys(sso)
    is_session = ("session_id" in keys) or (len(sso) < 400 and sso.count(".") == 2 and not looks_wrapper)
    session_id_prefix = ""
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
        token = self.login(force=False)
        params: Dict[str, Any] = {
            "page": max(1, int(page or 1)),
            "page_size": max(1, min(200, int(page_size or 50))),
            "lite": "true",
        }
        if platform:
            params["platform"] = platform
        if search:
            params["search"] = str(search).strip()[:100]
        response, payload = self._request_json(
            "GET",
            "/api/v1/admin/accounts",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if response.status_code >= 400 or not self._payload_ok(payload):
            detail = payload.get("message") or payload.get("msg") or payload.get("error") or _body_summary(response)
            raise RuntimeError(f"Sub2API 列表账号失败 status={response.status_code} detail={detail}")
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
                    f"[!] Sub2API OAuth 账号已{created.get('action')}但可用性验证失败 "
                    f"account_id={account_id or '-'} detail={verification.get('error') or 'unknown error'} "
                    f"(账号保留，不回滚；仅当 require_verify_success=true 时才视为入池失败)"
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
        groups = _parse_group_ids(group_ids)
        name = str(email or "").strip() or f"grok-{hashlib.sha256(sso.encode()).hexdigest()[:10]}"
        sso_meta = _sso_kind_meta(sso)
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
        for attempt in (1, 2):
            token = self.login(force=(attempt == 2))
            response, payload = self._request_json(
                "POST",
                "/api/v1/admin/grok/sso-to-oauth",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            if response.status_code == 401 and attempt == 1:
                _log(self.log_callback, "[!] Sub2API access token 已失效，重新登录后重试一次")
                self._access_token = ""
                self._token_expires_at = 0.0
                continue
            payload_code = payload.get("code")
            payload_message = payload.get("message") or payload.get("msg") or payload.get("error") or ""
            if response.status_code >= 400 or not self._payload_ok(payload):
                detail = payload_message or _body_summary(response)
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
                            f"[!] Sub2API 账号已创建但可用性验证失败 account_id={account_id or '-'} "
                            f"detail={verification.get('error') or 'unknown error'} "
                            f"(账号保留，不回滚；仅当 require_verify_success=true 时才视为入池失败)"
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
                detail = item.get("error") or item.get("message") or "unknown conversion/import failure"
                raise RuntimeError(
                    f"Sub2API SSO→OAuth 转换失败: status={response.status_code} "
                    f"code={payload_code!r} message={payload_message!r} failed.error={detail}"
                )
            raise RuntimeError(
                f"Sub2API 入池返回 created/failed 均为空 status={response.status_code} "
                f"code={payload_code!r} message={payload_message!r}"
            )
        raise RuntimeError("Sub2API 入池认证重试失败")


def _client_cache_key(config: Dict[str, Any]) -> str:
    raw = "\0".join(
        [
            str(config.get("sub2api_base_url") or "http://127.0.0.1:8080").strip().rstrip("/"),
            str(config.get("sub2api_admin_email") or "").strip(),
            str(config.get("sub2api_admin_password") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_client(config: Dict[str, Any], log_callback: Optional[Callable[[str], None]] = None) -> Sub2APIClient:
    key = _client_cache_key(config)
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
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
    return client


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

