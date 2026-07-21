# -*- coding: utf-8 -*-
"""18r43n: stop non-blocking + dual quota + post_success stop + proxy antiwipe verify."""
from __future__ import annotations

from pathlib import Path
import re
import json
import shutil
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(p: Path) -> None:
    if p.is_file():
        shutil.copy2(p, p.with_suffix(p.suffix + f".bak_18r43n_{TS}"))


def patch_worker_coord() -> None:
    p = ROOT / "worker_coord.py"
    backup(p)
    t = p.read_text(encoding="utf-8")
    # header note
    if "18r43n:" not in t[:300]:
        t = (
            "# 18r43n: dual halt success>=target OR slots>=target; success never overshoots\n"
            + t
        )

    old_claim = '''    def claim_slot(self) -> Optional[int]:
        """Return 1-based attempt number, or None if quota reached / pool empty / stop_extra.

        18r43m default claim_mode=attempt: hard stop when slots_started >= target
        (fail/pending_sso consume register_count). Legacy success only if claim_mode=success.
        """
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            mode = str(getattr(self, "claim_mode", "attempt") or "attempt").strip().lower()
            if mode in ("success", "success_based", "ok"):
                if int(self.success or 0) >= self.target:
                    return None
                max_attempts = max(self.target * 8, self.target + 50)
                if self._slots_started >= max_attempts:
                    self._stop_extra = True
                    return None
            else:
                if self._slots_started >= self.target:
                    return None
            self._slots_started += 1
            return self._slots_started
'''

    new_claim = '''    def claim_slot(self) -> Optional[int]:
        """Return 1-based attempt number, or None if quota reached / pool empty / stop_extra.

        18r43n dual (default/attempt):
          - hard stop when slots_started >= target (never run 1600 for count=1000)
          - also stop when success >= target (注册数量=注册成功数量 ceiling)
        Legacy claim_mode=success: keep going until success>=target with soft max_attempts=target*8.
        """
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            if int(self.success or 0) >= self.target > 0:
                self._stop_extra = True
                return None
            mode = str(getattr(self, "claim_mode", "attempt") or "attempt").strip().lower()
            if mode in ("success", "success_based", "ok"):
                max_attempts = max(self.target * 8, self.target + 50)
                if self._slots_started >= max_attempts:
                    self._stop_extra = True
                    return None
            else:
                # attempt / dual: register_count is both attempt budget and success ceiling
                if self._slots_started >= self.target:
                    return None
            self._slots_started += 1
            return self._slots_started
'''
    if old_claim not in t:
        raise SystemExit("claim_slot block not found")
    t = t.replace(old_claim, new_claim, 1)

    old_rec = '''    def record_success(self) -> None:
        with self._lock:
            self.success += 1
'''
    new_rec = '''    def record_success(self) -> None:
        with self._lock:
            # 18r43n: never overshoot success past register_count
            if self.target > 0 and int(self.success or 0) >= self.target:
                self._stop_extra = True
                return
            self.success += 1
            if self.target > 0 and int(self.success or 0) >= self.target:
                self._stop_extra = True
'''
    if old_rec not in t:
        raise SystemExit("record_success block not found")
    t = t.replace(old_rec, new_rec, 1)

    # should_halt
    if "def should_halt" in t:
        m = re.search(r"def should_halt\(self\) -> bool:\n(?:.*\n){1,25}", t)
        if m:
            new_halt = '''def should_halt(self) -> bool:
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return True
            if self.target > 0 and int(self.success or 0) >= self.target:
                return True
            mode = str(getattr(self, "claim_mode", "attempt") or "attempt").strip().lower()
            if mode in ("success", "success_based", "ok"):
                max_attempts = max(self.target * 8, self.target + 50)
                return self._slots_started >= max_attempts
            return self._slots_started >= self.target

'''
            # replace only the function - find end at next def
            start = t.find("def should_halt")
            end = t.find("\n    def ", start + 1)
            if end < 0:
                end = t.find("\n\nclass ", start + 1)
            if end > start:
                t = t[:start] + new_halt + t[end + 1 :]

    p.write_text(t, encoding="utf-8")
    print("worker_coord patched")


def patch_api_stop() -> None:
    p = ROOT / "web" / "server.py"
    backup(p)
    t = p.read_text(encoding="utf-8")
    if "18r43n:" not in t[:2500]:
        t = t.replace(
            "18r40: /api/stop sets stop Event + double force_stop/browser kill",
            "18r43n: /api/stop non-blocking thread cleanup; dual quota; keep web alive\n18r40: /api/stop sets stop Event + double force_stop/browser kill",
            1,
        )

    old = '''@app.post("/api/stop")
async def api_stop(x_access_key: Optional[str] = Header(None)):
    """Stop ONLY registration/pending jobs + browsers.

    18r40: set stop Event first, force_stop twice (browsers/preflight/workers),
    clear running immediately so UI/status clears. Never touch G2A/Sub2/CPA.
    """
    global _controller
    _require_auth(x_access_key)
    with _job_lock:
        ctrl = _controller
        running = bool(_job_state.get("running"))
        job_kind = str(_job_state.get("job_kind") or "")
        # Clear running flag immediately so /api/status and new starts work.
        if running:
            _job_state["running"] = False
            _job_state["phase"] = "stopping"
            _job_state["finished_at"] = time.time()
            _job_state["updated_at"] = time.time()
            _job_state["last_event"] = "[!] stop requested бк clearing running flag (18r40)"
    _append_log("[!] stop requested from web (18r40 stop_event + double force_stop)")
    try:
        # 1) signal workers ASAP
        if ctrl is not None:
            try:
                # set flag without waiting cleanup first
                if hasattr(ctrl, "stop_requested"):
                    ctrl.stop_requested = True
            except Exception:
                pass
            try:
                ctrl.stop(force_cleanup=True)
            except TypeError:
                try:
                    ctrl.stop()
                except Exception:
                    pass
            except Exception as _se:
                _append_log(f"[!] controller.stop error: {_se}")
        # 2) hard-kill browsers/preflight
        engine.force_stop_registration(
            log_callback=_append_log, reason="web_stop_18r40_pass1"
        )
        # 3) brief wait then second kill for late-spawned chromium
        try:
            time.sleep(0.8)
        except Exception:
            pass
        try:
            engine.force_stop_registration(
                log_callback=_append_log, reason="web_stop_18r40_pass2"
            )
        except Exception as _e2:
            _append_log(f"[!] stop pass2 error: {_e2}")
        try:
            if hasattr(engine, "force_kill_registration_browsers"):
                engine.force_kill_registration_browsers(log_callback=_append_log)
        except Exception:
            pass
    except Exception as exc:
        _append_log(f"[!] stop cleanup error: {exc}")
        try:
            engine.force_stop_registration(
                log_callback=_append_log, reason="web_stop_exception"
            )
        except Exception:
            pass
    with _job_lock:
        # If job thread already finished, keep its totals; only fix stuck state.
        if _controller is ctrl:
            _controller = None
        if _job_state.get("phase") == "stopping":
            _job_state["phase"] = "idle"
            _job_state["updated_at"] = time.time()
            _job_state["last_event"] = "[!] stop complete бк job idle (gateways untouched) 18r40"
    return {
        "ok": True,
        "stopped": True,
        "running_was": running,
        "had_controller": ctrl is not None,
        "job_kind": job_kind,
        "running_now": False,
        "detail": (
            "stopped: running cleared + double browser cleanup; gateways kept alive"
            if running or ctrl is not None
            else "no running job (browser cleanup attempted; gateways untouched)"
        ),
    }
'''

    # Use ASCII hyphen in last_event to avoid encoding issues
    new = '''@app.post("/api/stop")
async def api_stop(x_access_key: Optional[str] = Header(None)):
    """Stop ONLY registration/pending jobs + script browsers.

    18r43n: clear running immediately; signal stop; heavy browser kill runs in a
    background thread so /api/status stays reachable. Never kill web server /
    G2A / Sub2API / CPA / user Edge.
    """
    global _controller
    _require_auth(x_access_key)
    with _job_lock:
        ctrl = _controller
        running = bool(_job_state.get("running"))
        job_kind = str(_job_state.get("job_kind") or "")
        if running:
            _job_state["running"] = False
            _job_state["phase"] = "stopping"
            _job_state["finished_at"] = time.time()
            _job_state["updated_at"] = time.time()
            _job_state["last_event"] = "[!] stop requested - clearing running flag (18r43n)"
        # detach controller so new starts are not blocked
        if _controller is ctrl:
            _controller = None
    _append_log("[!] stop requested from web (18r43n non-blocking cleanup)")

    def _cleanup_stop(ctrl_obj) -> None:
        try:
            if ctrl_obj is not None:
                try:
                    if hasattr(ctrl_obj, "stop_requested"):
                        ctrl_obj.stop_requested = True
                except Exception:
                    pass
                try:
                    ctrl_obj.stop(force_cleanup=True)
                except TypeError:
                    try:
                        ctrl_obj.stop()
                    except Exception:
                        pass
                except Exception as _se:
                    _append_log(f"[!] controller.stop error: {_se}")
            try:
                engine.force_stop_registration(
                    log_callback=_append_log, reason="web_stop_18r43n_pass1"
                )
            except Exception as _e1:
                _append_log(f"[!] stop pass1 error: {_e1}")
            try:
                time.sleep(0.5)
            except Exception:
                pass
            try:
                engine.force_stop_registration(
                    log_callback=_append_log, reason="web_stop_18r43n_pass2"
                )
            except Exception as _e2:
                _append_log(f"[!] stop pass2 error: {_e2}")
            try:
                if hasattr(engine, "force_kill_registration_browsers"):
                    engine.force_kill_registration_browsers(log_callback=_append_log)
            except Exception:
                pass
        except Exception as exc:
            _append_log(f"[!] stop cleanup error: {exc}")
        finally:
            with _job_lock:
                if _job_state.get("phase") == "stopping":
                    _job_state["phase"] = "idle"
                    _job_state["running"] = False
                    _job_state["updated_at"] = time.time()
                    _job_state["last_event"] = "[!] stop complete - job idle (gateways/web untouched) 18r43n"

    try:
        th = threading.Thread(
            target=_cleanup_stop,
            args=(ctrl,),
            name="web-stop-cleanup-18r43n",
            daemon=True,
        )
        th.start()
    except Exception as exc:
        _append_log(f"[!] stop thread spawn fail, sync fallback: {exc}")
        _cleanup_stop(ctrl)

    return {
        "ok": True,
        "stopped": True,
        "running_was": running,
        "had_controller": ctrl is not None,
        "job_kind": job_kind,
        "running_now": False,
        "detail": (
            "stopped: running cleared; browser cleanup async; gateways/web kept alive"
            if running or ctrl is not None
            else "no running job (browser cleanup async; gateways/web untouched)"
        ),
    }
'''

    if old not in t:
        # try looser match by markers
        start = t.find('@app.post("/api/stop")')
        if start < 0:
            raise SystemExit("api_stop not found")
        end = t.find('@app.get("/api/logs")', start)
        if end < 0:
            raise SystemExit("api_logs after stop not found")
        t = t[:start] + new + "\n\n" + t[end:]
        print("api_stop replaced by markers")
    else:
        t = t.replace(old, new, 1)
        print("api_stop replaced exact")

    p.write_text(t, encoding="utf-8")
    print("server stop patched")


def patch_engine_stop_flag() -> None:
    """Make force_stop also set a global registration cancel if present."""
    p = ROOT / "grok_register_ttk.py"
    t = p.read_text(encoding="utf-8")
    if "18r43n:" not in t[:400]:
        t = "# 18r43n: force_stop sets cancel + non-block web stop\n" + t
    # ensure force_stop_registration starts with stop signal for hybrid loops
    needle = 'def force_stop_registration(log_callback=None, reason="user_stop"):\n    """Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA."""\n    _lg = log_callback if callable(log_callback) else (lambda m: None)\n    _lg(f"[!] force_stop_registration: {reason}")\n'
    repl = 'def force_stop_registration(log_callback=None, reason="user_stop"):\n    """Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA/web."""\n    _lg = log_callback if callable(log_callback) else (lambda m: None)\n    _lg(f"[!] force_stop_registration: {reason}")\n    try:\n        # 18r43n: cooperative cancel for hybrid/browser loops still checking flag\n        global _REGISTRATION_CANCEL\n        _REGISTRATION_CANCEL = True\n    except Exception:\n        pass\n'
    if needle in t and "_REGISTRATION_CANCEL = True" not in t[t.find("def force_stop_registration"): t.find("def force_stop_registration") + 500]:
        # only add global if symbol exists or introduce soft attribute on module
        if "_REGISTRATION_CANCEL" not in t:
            # inject near top after imports is hard; use config flag instead
            repl = 'def force_stop_registration(log_callback=None, reason="user_stop"):\n    """Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA/web."""\n    _lg = log_callback if callable(log_callback) else (lambda m: None)\n    _lg(f"[!] force_stop_registration: {reason}")\n    try:\n        config["stop_requested"] = True\n    except Exception:\n        pass\n'
        t = t.replace(needle, repl, 1)
        backup(p)
        p.write_text(t, encoding="utf-8")
        print("engine force_stop patched")
    else:
        print("engine force_stop skip/already")


def ensure_proxy_pool() -> None:
    pf = ROOT / "socks5_proxies.txt"
    bak = ROOT / "backup_before_general_socks5_20260717_063218" / "socks5_proxies.txt"
    if (not pf.exists() or pf.stat().st_size == 0) and bak.exists():
        shutil.copy2(bak, pf)
        print("proxy restored from bak")
    body = pf.read_text(encoding="utf-8", errors="ignore") if pf.exists() else ""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    cfgp = ROOT / "config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    if lines and not str(cfg.get("proxy_list") or "").strip():
        cfg["proxy_list"] = body.rstrip("\n")
    cfg["proxy_mode"] = cfg.get("proxy_mode") or "socks5_list"
    cfg["proxy_list_file"] = "socks5_proxies.txt"
    cfg["claim_mode"] = "attempt"
    cfg["register_quota_mode"] = "attempt"
    # keep creds lengths only log
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("proxy_lines", len(lines), "claim_mode", cfg.get("claim_mode"))


def unit_claim() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    # reload fresh
    import importlib
    import worker_coord
    importlib.reload(worker_coord)
    from worker_coord import JobCoordinator
    c = JobCoordinator(3, claim_mode="attempt")
    claims = [c.claim_slot() for _ in range(5)]
    print("claims", claims, "halt", c.should_halt())
    assert claims == [1, 2, 3, None, None], claims
    c2 = JobCoordinator(2, claim_mode="attempt")
    assert c2.claim_slot() == 1
    c2.record_success()
    assert c2.claim_slot() == 2
    c2.record_success()
    assert c2.claim_slot() is None  # success ceiling
    # overshoot guard
    c2.record_success()
    assert c2.success == 2
    print("unit_claim OK")


def main() -> None:
    patch_worker_coord()
    patch_api_stop()
    patch_engine_stop_flag()
    ensure_proxy_pool()
    unit_claim()
    # syntax
    import ast
    for rel in ("worker_coord.py", "web/server.py", "grok_register_ttk.py"):
        ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        print("syntax_ok", rel)


if __name__ == "__main__":
    main()
