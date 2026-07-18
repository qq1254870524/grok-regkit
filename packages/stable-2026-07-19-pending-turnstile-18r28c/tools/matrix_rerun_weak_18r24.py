# -*- coding: utf-8 -*-
"""Rerun weak matrix cells after 18r24 fixes. 2 rounds each."""
from __future__ import annotations
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / f"matrix_18r24_weak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("mcr", ROOT / "tools" / "matrix_cross_run.py")
mcr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcr)
mcr.OUT = OUT
mcr.SUMMARY = OUT / "summary.jsonl"
mcr.REPORT = OUT / "REPORT.md"
mcr.JOB_TIMEOUT = 720

CELLS = [
    {"name": "hybrid__direct__outlook", "kind": "register", "register_mode": "hybrid", "proxy_mode": "direct", "email_provider": "outlook"},
    {"name": "hybrid__direct__aol", "kind": "register", "register_mode": "hybrid", "proxy_mode": "direct", "email_provider": "aol"},
    {"name": "hybrid__socks5_list__outlook", "kind": "register", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "hybrid__socks5_list__aol", "kind": "register", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "browser__direct__outlook", "kind": "register", "register_mode": "browser", "proxy_mode": "direct", "email_provider": "outlook"},
    {"name": "browser__direct__aol", "kind": "register", "register_mode": "browser", "proxy_mode": "direct", "email_provider": "aol"},
    {"name": "browser__socks5_list__outlook", "kind": "register", "register_mode": "browser", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "browser__socks5_list__aol", "kind": "register", "register_mode": "browser", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "pending_sso_recovery__socks5_list", "kind": "pending_sso_recovery", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "pending_sso_recovery__direct", "kind": "pending_sso_recovery", "register_mode": "hybrid", "proxy_mode": "direct", "email_provider": "aol"},
]
ROUNDS = 2
mcr.ROUNDS = ROUNDS
mcr.PENDING_ROUNDS = ROUNDS
LOG = OUT / "runner.log"
SUM = OUT / "summary.jsonl"

def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def main() -> int:
    log(f"OUT={OUT}")
    log(f"ROUNDS={ROUNDS} weak_cells={len(CELLS)} tag=18r24")
    try:
        code, st = mcr.api("GET", "/api/status")
        log(f"8092 status code={code} running={st.get('running')}")
    except Exception as e:
        log(f"8092 not ready: {e}")
        return 1

    results = []
    for cell in CELLS:
        for r in range(1, ROUNDS + 1):
            rec = mcr.run_one(cell, r)
            if rec.get("class") in ("stop_requested", "empty_log", "runner_exception", "start_fail"):
                log(f"[retry] {cell['name']} r{r} class={rec.get('class')}")
                mcr.stop_job()
                mcr.wait_idle(45)
                time.sleep(3)
                rec2 = mcr.run_one(cell, r)
                rec2["retried_from"] = rec.get("class")
                rec = rec2
            results.append(rec)
            log(
                f"[{cell['name']}] r{r}/{ROUNDS} ok={rec.get('ok')} class={rec.get('class')} "
                f"s={rec.get('success')} f={rec.get('fail')} p={rec.get('pending_sso')} t={rec.get('elapsed_s')}s"
            )
            time.sleep(2)

    if hasattr(mcr, "write_report"):
        try:
            mcr.write_report(results)
        except Exception as e:
            log(f"write_report fail: {e}")
    ok_n = sum(1 for x in results if x.get("ok"))
    log(f"DONE weak rerun total={len(results)} ok={ok_n}")
    (OUT / "DONE.txt").write_text(f"ok={ok_n} total={len(results)}\n", encoding="utf-8")
    return 0 if ok_n > 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
