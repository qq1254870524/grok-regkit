# -*- coding: utf-8 -*-
"""Multi-worker coordination for grok-regkit (18r30 multithread, 18r41 exclusivity).

- Shared counters with locks (success/fail/pending/skipped)
- Slot claim so workers do not overshoot target count
- Rate-limit attempts reclaim slots (same semantics as serial hybrid)
- Per-worker SOCKS5 bind: pool[(worker_id-1) % n], sequential reuse
- Email pool preflight at job start (login check; drop bad mailboxes)
- Continuous background email pre-login warm queue (keep ahead of workers)
- Thread-safe log prefix [wN]

Logs are plaintext (no redaction). Do not use this module to print SSO/cookies.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
    def undo_fail(self) -> None:
        """18r35i: after hybrid re-register success, reverse a prior fail tally."""
        with self._lock:
            if int(getattr(self, 'fail', 0) or 0) > 0:
                self.fail = int(self.fail) - 1


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
                    mark_preflight_warm(email, "outlook")
                    lg(f"[+] Outlook preflight OK email={email}")
                except Exception as exc:
                    summary["outlook_bad"] += 1
                    invalidate_preflight_warm(email)
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



# ---------------------------------------------------------------------------
# Continuous background email pre-login (18r31c)
# Keep a warm queue of recently verified-login mailboxes so workers spend less
# time blocking on first IMAP/Graph auth. Login failures are removed immediately.
# ---------------------------------------------------------------------------

_warm_lock = threading.RLock()
_warm_ok: Dict[str, float] = {}  # email.lower() -> monotonic ts of last OK preflight
_warm_provider: Dict[str, str] = {}
_preflight_daemon: Optional["ContinuousEmailPreflight"] = None
_preflight_daemon_lock = threading.Lock()


def _email_key(email: str) -> str:
    return str(email or "").strip().lower()


def mark_preflight_warm(email: str, provider: str = "") -> None:
    em = _email_key(email)
    if not em:
        return
    with _warm_lock:
        _warm_ok[em] = time.monotonic()
        if provider:
            _warm_provider[em] = str(provider).strip().lower()


def invalidate_preflight_warm(email: str) -> None:
    em = _email_key(email)
    if not em:
        return
    with _warm_lock:
        _warm_ok.pop(em, None)
        _warm_provider.pop(em, None)


def is_preflight_warm(email: str, *, ttl_sec: float = 600.0) -> bool:
    """True if email passed auth preflight recently (still in pool assumed by caller)."""
    em = _email_key(email)
    if not em:
        return False
    ttl = max(30.0, float(ttl_sec or 600.0))
    with _warm_lock:
        ts = _warm_ok.get(em)
        if ts is None:
            return False
        if (time.monotonic() - float(ts)) > ttl:
            _warm_ok.pop(em, None)
            _warm_provider.pop(em, None)
            return False
        return True


def warm_queue_snapshot() -> Dict[str, Any]:
    now = time.monotonic()
    with _warm_lock:
        alive = {k: v for k, v in _warm_ok.items() if (now - float(v)) <= 900.0}
        return {
            "warm_count": len(alive),
            "emails_sample": list(alive.keys())[:12],
            "daemon_alive": bool(
                _preflight_daemon is not None and getattr(_preflight_daemon, "is_alive", lambda: False)()
            ),
        }


def _token_blob_from_account(acc: Any, config: dict) -> str:
    import json as _json

    email = str(getattr(acc, "email", "") or "").strip()
    try:
        if hasattr(acc, "token_blob"):
            tb = acc.token_blob() if callable(acc.token_blob) else str(acc.token_blob or "")
            if tb:
                return tb
        if hasattr(acc, "as_token_blob"):
            tb = acc.as_token_blob()
            if tb:
                return str(tb)
    except Exception:
        pass
    data = {
        "email": email,
        "password": getattr(acc, "password", "") or "",
        "totp_secret": getattr(acc, "totp_secret", "") or getattr(acc, "totp", "") or "",
        "refresh_token": getattr(acc, "refresh_token", "") or "",
        "access_token": getattr(acc, "access_token", "") or "",
        "client_id": getattr(acc, "client_id", "") or (config.get("outlook_client_id") if isinstance(config, dict) else "") or "",
    }
    return _json.dumps(data, ensure_ascii=False)


def _iter_idle_accounts(pool: Any) -> List[Any]:
    try:
        accounts = list(getattr(pool, "accounts", []) or [])
    except Exception:
        accounts = []
    out = []
    for acc in accounts:
        status = str(getattr(acc, "status", "") or "")
        if status in ("bad", "registered", "in_use", "warming"):
            continue
        email = str(getattr(acc, "email", "") or "").strip()
        if not email:
            continue
        # respect cooldown if present
        try:
            cd = float(getattr(acc, "cooldown_until", 0) or 0)
            if cd and cd > time.time():
                continue
        except Exception:
            pass
        out.append(acc)
    return out


def _preflight_one_account(
    *,
    provider: str,
    acc: Any,
    config: dict,
    log: LogFn,
    top: int,
) -> Tuple[bool, str]:
    """Return (ok, email). On permanent fail removes from pool only if still warming/idle."""
    email = str(getattr(acc, "email", "") or "").strip()
    if not email:
        return False, ""
    c = config if isinstance(config, dict) else {}
    token_blob = _token_blob_from_account(acc, c)

    def _clear_warming_to_idle() -> None:
        try:
            if str(getattr(acc, "status", "") or "") == "warming":
                acc.status = "idle"
        except Exception:
            pass

    try:
        if provider == "aol":
            import aol_mail as am

            am.preflight_mailbox(c, token_blob, email, log_callback=log, top=top)
            mark_preflight_warm(email, "aol")
            _clear_warming_to_idle()
            return True, email
        else:
            import outlook_mail as om

            om.preflight_mailbox(c, token_blob, email, log_callback=log, top=top)
            mark_preflight_warm(email, "outlook")
            _clear_warming_to_idle()
            return True, email
    except Exception as exc:
        invalidate_preflight_warm(email)
        log(
            f"[!] continuous preflight FAIL provider={provider} email={email} "
            f"exc={type(exc).__name__}: {exc} | remove from pool if not in_use"
        )
        try:
            if provider == "aol":
                import aol_mail as am

                pool = am.get_pool(c, log_callback=log)
                lock = getattr(am, "_POOL_LOCK", None)
            else:
                import outlook_mail as om

                pool = om.get_pool(c, log_callback=log)
                lock = getattr(om, "_POOL_LOCK", None)

            def _safe_remove() -> None:
                st = str(getattr(acc, "status", "") or "")
                if st == "in_use":
                    log(f"[*] continuous preflight skip remove (in_use) email={email}")
                    return
                # clear warming before remove path
                try:
                    if st == "warming":
                        acc.status = "idle"
                except Exception:
                    pass
                pool.remove_account(email, reason=f"continuous_preflight_fail:{type(exc).__name__}")

            if lock is not None:
                with lock:
                    _safe_remove()
            else:
                _safe_remove()
        except Exception as rm_exc:
            log(f"[!] continuous preflight remove fail email={email}: {rm_exc}")
            _clear_warming_to_idle()
        return False, email

class ContinuousEmailPreflight:
    """Background thread: keep warm_ahead mailboxes auth-verified ahead of workers."""

    def __init__(
        self,
        config: dict,
        *,
        log: Optional[LogFn] = None,
        top: int = 5,
        warm_ahead: int = 6,
        interval_sec: float = 0.8,
        ttl_sec: float = 600.0,
    ):
        self.config = config if isinstance(config, dict) else {}
        self.log = log or (lambda _m: None)
        self.top = max(1, int(top or 5))
        self.warm_ahead = max(1, int(warm_ahead or 1))
        self.interval_sec = max(0.2, float(interval_sec or 0.8))
        self.ttl_sec = max(60.0, float(ttl_sec or 600.0))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cursor = 0
        self.stats = {
            "ok": 0,
            "bad": 0,
            "skipped_warm": 0,
            "loops": 0,
        }

    def is_alive(self) -> bool:
        t = self._thread
        return bool(t is not None and t.is_alive())

    def start(self) -> None:
        if self.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="email-preflight-continuous",
            daemon=True,
        )
        self._thread.start()
        self.log(
            f"[*] continuous email preflight START warm_ahead={self.warm_ahead} "
            f"interval={self.interval_sec}s ttl={self.ttl_sec}s top={self.top}"
        )

    def stop(self, *, join_timeout: float = 2.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            try:
                t.join(timeout=max(0.1, float(join_timeout)))
            except Exception:
                pass
        self.log(
            f"[*] continuous email preflight STOP ok={self.stats['ok']} "
            f"bad={self.stats['bad']} skipped_warm={self.stats['skipped_warm']} "
            f"loops={self.stats['loops']} warm_now={warm_queue_snapshot().get('warm_count')}"
        )

    def _providers(self) -> List[str]:
        prov = str(self.config.get("email_provider") or "").strip().lower()
        out: List[str] = []
        if prov in ("outlook", "microsoft", "hotmail", "live", "msn", "both", "all", "outlook+aol", ""):
            out.append("outlook")
        if prov in ("aol", "aim", "both", "all", "outlook+aol", "aol+outlook", ""):
            out.append("aol")
        if not out:
            out = ["outlook", "aol"]
        return out

    def _warm_count_live(self) -> int:
        snap = warm_queue_snapshot()
        return int(snap.get("warm_count") or 0)

    def _pick_next(self, provider: str) -> Optional[Any]:
        try:
            if provider == "aol":
                import aol_mail as am

                pool = am.get_pool(self.config, log_callback=self.log)
                lock = getattr(am, "_POOL_LOCK", None)
            else:
                import outlook_mail as om

                pool = om.get_pool(self.config, log_callback=self.log)
                lock = getattr(om, "_POOL_LOCK", None)
        except Exception as exc:
            self.log(f"[!] continuous preflight get_pool fail provider={provider}: {exc}")
            return None

        def _scan_and_reserve() -> Optional[Any]:
            idle = _iter_idle_accounts(pool)
            if not idle:
                return None
            n = len(idle)
            start = self._cursor % n
            self._cursor = (self._cursor + 1) % max(n, 1)
            ordered = idle[start:] + idle[:start]
            for acc in ordered:
                em = _email_key(getattr(acc, "email", ""))
                if is_preflight_warm(em, ttl_sec=self.ttl_sec):
                    self.stats["skipped_warm"] += 1
                    continue
                # 18r41: mark warming so workers cannot acquire mid-preflight
                try:
                    acc.status = "warming"
                except Exception:
                    pass
                return acc
            return None

        try:
            if lock is not None:
                with lock:
                    return _scan_and_reserve()
            return _scan_and_reserve()
        except Exception as exc:
            self.log(f"[!] continuous preflight pick fail provider={provider}: {exc}")
            return None

    def _run(self) -> None:
        providers = self._providers()
        while not self._stop.is_set():
            self.stats["loops"] += 1
            try:
                warm_now = self._warm_count_live()
                need = max(0, self.warm_ahead - warm_now)
                if need <= 0:
                    # still slowly re-validate oldest? sleep only
                    if self._stop.wait(self.interval_sec):
                        break
                    continue
                did = 0
                for provider in providers:
                    if self._stop.is_set() or did >= need:
                        break
                    acc = self._pick_next(provider)
                    if acc is None:
                        continue
                    ok, email = _preflight_one_account(
                        provider=provider,
                        acc=acc,
                        config=self.config,
                        log=self.log,
                        top=self.top,
                    )
                    if ok:
                        self.stats["ok"] += 1
                        did += 1
                        self.log(
                            f"[+] continuous preflight OK provider={provider} email={email} "
                            f"warm_now={self._warm_count_live()}/{self.warm_ahead}"
                        )
                    else:
                        self.stats["bad"] += 1
                        did += 1  # consumed attempt
                # small pause between checks so we don't hammer IMAP/Graph
                if self._stop.wait(self.interval_sec if did else max(self.interval_sec, 1.5)):
                    break
            except Exception as loop_exc:
                self.log(f"[!] continuous preflight loop error: {type(loop_exc).__name__}: {loop_exc}")
                if self._stop.wait(2.0):
                    break


def start_continuous_preflight(
    config: dict,
    log: Optional[LogFn] = None,
    *,
    top: Optional[int] = None,
) -> Optional[ContinuousEmailPreflight]:
    """Start (or restart) background continuous email pre-login."""
    global _preflight_daemon
    lg = log or (lambda _m: None)
    c = config if isinstance(config, dict) else {}
    if not bool(c.get("email_preflight_on_start", True)):
        lg("[*] continuous email preflight disabled (email_preflight_on_start=false)")
        return None
    if not bool(c.get("email_preflight_continuous", True)):
        lg("[*] continuous email preflight disabled (email_preflight_continuous=false)")
        return None
    try:
        w = int(c.get("workers") or c.get("thread_count") or 1)
    except Exception:
        w = 1
    try:
        warm_ahead = int(c.get("email_preflight_warm_ahead") or 0)
    except Exception:
        warm_ahead = 0
    # 0/negative => auto from workers; positive => user web-defined cap (1..200)
    if warm_ahead <= 0:
        warm_ahead = max(6, min(40, w * 4))
    else:
        warm_ahead = max(1, min(200, warm_ahead))
    try:
        interval = float(c.get("email_preflight_interval_sec") or 0.8)
    except Exception:
        interval = 0.8
    try:
        ttl = float(c.get("email_preflight_warm_ttl_sec") or 600)
    except Exception:
        ttl = 600.0
    top_n = int(top if top is not None else (c.get("mail_top_per_folder") or 5))

    with _preflight_daemon_lock:
        if _preflight_daemon is not None:
            try:
                _preflight_daemon.stop(join_timeout=1.0)
            except Exception:
                pass
            _preflight_daemon = None
        daemon = ContinuousEmailPreflight(
            c,
            log=lg,
            top=top_n,
            warm_ahead=warm_ahead,
            interval_sec=interval,
            ttl_sec=ttl,
        )
        daemon.start()
        _preflight_daemon = daemon
        return daemon


def stop_continuous_preflight(log: Optional[LogFn] = None) -> None:
    global _preflight_daemon
    lg = log or (lambda _m: None)
    with _preflight_daemon_lock:
        d = _preflight_daemon
        _preflight_daemon = None
    if d is not None:
        try:
            d.stop(join_timeout=2.0)
        except Exception as exc:
            lg(f"[!] stop continuous preflight: {exc}")
    else:
        lg("[*] continuous email preflight already stopped")



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
