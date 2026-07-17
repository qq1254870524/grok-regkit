#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sub2API Grok SSO -> OAuth importer.

Changelog:
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
