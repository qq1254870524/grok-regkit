# -*- coding: utf-8 -*-
"""Multi-worker coordination for grok-regkit (18r30 multithread).

- Shared counters with locks (success/fail/pending/skipped)
- Slot claim so workers do not overshoot target count
- Rate-limit attempts reclaim slots (same semantics as serial hybrid)
- Per-worker SOCKS5 bind: pool[(worker_id-1) % n], sequential reuse
- Email pool preflight at job start (login check; drop bad mailboxes)
- Thread-safe log prefix [wN]

Logs are plaintext (no redaction). Do not use this module to print SSO/cookies.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

LogFn = Callable[[str], None]


class JobCoordinator:
    """Coordinate multi-worker registration slots and counters."""

    def __init__(
        self,
        target: int,
        *,
        log: Optional[LogFn] = None,
        max_switch_mailbox: int = 0,
    ):
        self.target = max(0, int(target or 0))
        self.log = log or (lambda _m: None)
        self.max_switch_mailbox = int(max_switch_mailbox or 0)
        self._lock = threading.Lock()
        self._slots_started = 0
        self.success = 0
        self.fail = 0
        self.pending_sso = 0
        self.skipped = 0
        self.pool_empty = False
        self.switch_mailbox_tries = 0
        self.active_workers = 0
        self._stop_extra = False

    def worker_enter(self) -> None:
        with self._lock:
            self.active_workers += 1

    def worker_leave(self) -> None:
        with self._lock:
            self.active_workers = max(0, self.active_workers - 1)

    def claim_slot(self) -> Optional[int]:
        """Return 1-based slot number, or None if target reached / pool empty / stop_extra."""
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            if self._slots_started >= self.target:
                return None
            self._slots_started += 1
            return self._slots_started

    def reclaim_slot(self) -> None:
        """Rate-limit / switch_mailbox did not consume a success-target slot."""
        with self._lock:
            if self._slots_started > 0:
                self._slots_started -= 1

    def mark_pool_empty(self) -> None:
        with self._lock:
            self.pool_empty = True
            self.skipped += 1
            self._stop_extra = True

    def record_success(self) -> None:
        with self._lock:
            self.success += 1

    def record_fail(self) -> None:
        with self._lock:
            self.fail += 1

    def record_pending(self, *, rate_limited: bool = False) -> None:
        with self._lock:
            self.pending_sso += 1
            if rate_limited:
                self.switch_mailbox_tries += 1
                if self.max_switch_mailbox and self.switch_mailbox_tries >= self.max_switch_mailbox:
                    self._stop_extra = True

    def should_halt(self) -> bool:
        with self._lock:
            return bool(self._stop_extra or self.pool_empty)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "success": self.success,
                "fail": self.fail,
                "pending_sso": self.pending_sso,
                "skipped": self.skipped,
                "pool_empty": bool(self.pool_empty),
                "slots_started": self._slots_started,
                "target": self.target,
                "active_workers": self.active_workers,
                "switch_mailbox_tries": self.switch_mailbox_tries,
            }

    def log_stats(self, prefix: str = "[*]") -> None:
        s = self.snapshot()
        self.log(
            f"{prefix} 当前统计: 成功 {s['success']} | 失败 {s['fail']} | "
            f"pending_sso {s['pending_sso']} | 跳过(池空) {s['skipped']} | "
            f"slots={s['slots_started']}/{s['target']} | workers={s['active_workers']}"
        )


def worker_log(base_log: Optional[LogFn], worker_id: int) -> LogFn:
    base = base_log or (lambda _m: None)

    def _lg(msg: str) -> None:
        text = str(msg)
        if text.startswith(f"[w{worker_id}]"):
            base(text)
        else:
            base(f"[w{worker_id}] {text}")

    return _lg


def bind_worker_proxy(engine, worker_id: int, log: Optional[LogFn] = None) -> str:
    """Bind one SOCKS5 (or current resolved proxy) to this worker for the whole job.

    SOCKS5 list: sequential reuse pool[(worker_id-1) % len(pool)].
    Other modes: use config['proxy'] / resolve once.
    Sets thread-local proxy override so start_browser/get_configured_proxy stay isolated.
    """
    lg = log or (lambda _m: None)
    wid = max(1, int(worker_id or 1))
    c = engine.config if isinstance(getattr(engine, "config", None), dict) else {}
    mode = str(c.get("proxy_mode", "") or "").strip().lower()
    proxy = ""
    try:
        if hasattr(engine, "is_socks5_list_mode") and engine.is_socks5_list_mode(c):
            pool = engine.load_proxy_list(c) if hasattr(engine, "load_proxy_list") else []
            if pool:
                proxy = pool[(wid - 1) % len(pool)]
                lg(
                    f"[*] worker proxy bind socks5_list worker={wid} "
                    f"index={(wid - 1) % len(pool)}/{len(pool)} | {proxy}"
                )
            else:
                proxy = str(c.get("proxy") or "").strip()
                lg(f"[*] worker proxy bind socks5_list empty; fallback proxy={proxy!r}")
        else:
            proxy = str(c.get("proxy") or "").strip()
            if not proxy and mode not in ("direct", "none", "off", ""):
                try:
                    proxy = str(engine.resolve_runtime_proxy(c, log_callback=lg, fetch_live=False) or "")
                except Exception:
                    proxy = str(c.get("proxy") or "")
            lg(f"[*] worker proxy bind mode={mode or 'direct'} worker={wid} | {proxy or '(direct)'}")
    except Exception as exc:
        lg(f"[!] worker proxy bind fail worker={wid}: {exc}")
        proxy = str(c.get("proxy") or "").strip()

    try:
        engine.set_thread_proxy(proxy)
    except Exception as exc:
        lg(f"[!] set_thread_proxy fail: {exc}")
    return proxy


def clear_worker_proxy(engine, log: Optional[LogFn] = None) -> None:
    lg = log or (lambda _m: None)
    try:
        engine.clear_thread_proxy()
    except Exception as exc:
        lg(f"[!] clear_thread_proxy fail: {exc}")


def preflight_email_pools(
    config: dict,
    log: Optional[LogFn] = None,
    *,
    top: int = 5,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """At job start: try login sample of mailboxes; remove login-fail accounts from pool.

    Still scans ALL folders at poll time; preflight only validates auth + top=N sample.
    Large pools (10k+) must NOT full-scan: default limit from config or max(30, workers*3).
    """
    lg = log or (lambda _m: None)
    summary: Dict[str, Any] = {
        "outlook_ok": 0,
        "outlook_bad": 0,
        "aol_ok": 0,
        "aol_bad": 0,
        "provider": "",
        "limit": 0,
        "checked": 0,
    }
    c = config if isinstance(config, dict) else {}
    prov = str(c.get("email_provider") or "").strip().lower()
    summary["provider"] = prov
    top_n = max(1, int(top or 5))
    if limit is None:
        try:
            limit = int(c.get("email_preflight_limit") or 0) or None
        except Exception:
            limit = None
    if limit is None:
        try:
            w = int(c.get("workers") or c.get("thread_count") or 1)
        except Exception:
            w = 1
        try:
            tgt = int(c.get("register_count") or 0)
        except Exception:
            tgt = 0
        limit = max(12, min(30, max(w * 3, tgt * 2 if tgt else w * 3)))
    limit = max(1, int(limit))
    summary["limit"] = limit
    lg(
        f"[*] email pool preflight start provider={prov or '-'} "
        f"top_per_folder={top_n} scanned_folders=ALL limit={limit} "
        f"(large pools sample-only; login-fail removed immediately)"
    )

    # Outlook / Microsoft
    if prov in ("outlook", "microsoft", "hotmail", "live", "msn", "both", "all", "outlook+aol", ""):
        try:
            import outlook_mail as om

            pool = om.get_pool(c, log_callback=lg)
            accounts = list(getattr(pool, "accounts", []) or [])
            lg(f"[*] Outlook preflight candidates={len(accounts)} will_check_up_to={limit}")
            checked_out = 0
            for acc in accounts:
                if checked_out >= limit:
                    lg(f"[*] Outlook preflight sample reached limit={limit}, stop further checks")
                    break
                checked_out += 1
                summary["checked"] = int(summary.get("checked") or 0) + 1
                email = str(getattr(acc, "email", "") or "").strip()
                if not email:
                    continue
                status = str(getattr(acc, "status", "") or "")
                if status in ("bad", "registered"):
                    continue
                try:
                    # rebuild token blob via acquire path without holding in_use forever
                    token_blob = ""
                    try:
                        if hasattr(acc, "token_blob"):
                            token_blob = acc.token_blob() if callable(acc.token_blob) else str(acc.token_blob or "")
                        elif hasattr(acc, "as_token_blob"):
                            token_blob = acc.as_token_blob()
                        else:
                            # common fields
                            import json as _json

                            data = {
                                "email": email,
                                "password": getattr(acc, "password", "") or "",
                                "totp_secret": getattr(acc, "totp_secret", "") or getattr(acc, "totp", "") or "",
                                "refresh_token": getattr(acc, "refresh_token", "") or "",
                                "access_token": getattr(acc, "access_token", "") or "",
                                "client_id": getattr(acc, "client_id", "") or c.get("outlook_client_id") or "",
                            }
                            token_blob = _json.dumps(data, ensure_ascii=False)
                    except Exception:
                        token_blob = ""
                    om.preflight_mailbox(c, token_blob, email, log_callback=lg, top=top_n)
                    summary["outlook_ok"] += 1
                    lg(f"[+] Outlook preflight OK email={email}")
                except Exception as exc:
                    summary["outlook_bad"] += 1
                    lg(f"[!] Outlook preflight FAIL email={email} err={exc}")
                    try:
                        pool.remove_account(email, reason=f"preflight_fail:{type(exc).__name__}")
                    except Exception as rm_exc:
                        lg(f"[!] Outlook remove after preflight fail: {rm_exc}")
        except Exception as exc:
            lg(f"[!] Outlook preflight block error: {exc}")

    # AOL
    if prov in ("aol", "aim", "both", "all", "outlook+aol", "aol+outlook", ""):
        # Always try AOL if file has accounts when provider empty or dual
        try:
            import aol_mail as am

            pool = am.get_pool(c, log_callback=lg)
            accounts = list(getattr(pool, "accounts", []) or [])
            if accounts or prov in ("aol", "aim"):
                lg(f"[*] AOL preflight candidates={len(accounts)} will_check_up_to={limit}")
                checked_aol = 0
                for acc in accounts:
                    if checked_aol >= limit:
                        lg(f"[*] AOL preflight sample reached limit={limit}, stop further checks")
                        break
                    checked_aol += 1
                    summary["checked"] = int(summary.get("checked") or 0) + 1
                    email = str(getattr(acc, "email", "") or "").strip()
                    if not email:
                        continue
                    status = str(getattr(acc, "status", "") or "")
                    if status in ("bad", "registered"):
                        continue
                    try:
                        token_blob = ""
                        try:
                            if hasattr(acc, "token_blob"):
                                token_blob = acc.token_blob() if callable(acc.token_blob) else str(acc.token_blob or "")
                            else:
                                import json as _json

                                token_blob = _json.dumps(
                                    {
                                        "email": email,
                                        "password": getattr(acc, "password", "") or getattr(acc, "app_password", "") or "",
                                    },
                                    ensure_ascii=False,
                                )
                        except Exception:
                            token_blob = str(getattr(acc, "password", "") or "")
                        am.preflight_mailbox(c, token_blob, email, log_callback=lg, top=top_n)
                        summary["aol_ok"] += 1
                        lg(f"[+] AOL preflight OK email={email}")
                    except Exception as exc:
                        summary["aol_bad"] += 1
                        lg(f"[!] AOL preflight FAIL email={email} err={exc}")
                        try:
                            pool.remove_account(email, reason=f"preflight_fail:{type(exc).__name__}")
                        except Exception as rm_exc:
                            lg(f"[!] AOL remove after preflight fail: {rm_exc}")
        except Exception as exc:
            lg(f"[!] AOL preflight block error: {exc}")

    lg(
        f"[*] email pool preflight done outlook_ok={summary['outlook_ok']} "
        f"outlook_bad={summary['outlook_bad']} aol_ok={summary['aol_ok']} "
        f"aol_bad={summary['aol_bad']}"
    )
    return summary


def resolve_workers(config: dict, workers: Optional[int] = None) -> int:
    if workers is not None:
        n = int(workers)
    else:
        c = config if isinstance(config, dict) else {}
        raw = c.get("workers", c.get("thread_count", c.get("register_workers", 1)))
        try:
            n = int(raw or 1)
        except Exception:
            n = 1
    return max(1, min(n, 32))
