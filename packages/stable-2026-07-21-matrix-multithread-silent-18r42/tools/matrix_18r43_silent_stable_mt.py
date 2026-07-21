# -*- coding: utf-8 -*-
"""18r43 silent stable multi-thread matrix (workers=20, preheat=40, count=1000).

Cross (each >=2 rounds):
- modes: hybrid only (stable silent)
- proxy: SOCKS5 only
- mail: outlook + aol
- pending_sso recovery SOCKS5 x2 (full real run)
- scale: workers=20 preheat=40 count=1000

Silent: browser_silent headed+minimize/offscreen (no focus steal).
No Python console windows when started via start_hidden.ps1.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
BASE = "http://127.0.0.1:8092"
OUT = ROOT / "matrix_runs"
OUT.mkdir(exist_ok=True)

MODES = ["hybrid"]
PROXIES = ["socks5_list"]
EMAILS = ["outlook", "aol"]
WORKERS = 20
COUNT = 1000
ROUNDS_PER_CELL = 2
PREHEAT = 40
# 1000 accounts / 20 workers ~ multi-hour; allow up to 36h per cell
TIMEOUT_PER_JOB = 36 * 60 * 60
STOP_TEST_AFTER_SEC = 30
INCLUDE_STOP_TESTS = True


def _req(method: str, path: str, body=None, timeout=60, retries=8):
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last = None
    for i in range(retries):
        try:
            r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last = exc
            time.sleep(min(2 + i * 1.5, 12))
    raise RuntimeError(f"API {method} {path} failed: {last}")


def wait_idle(timeout=300, force_stop_after=60):
    t0 = time.time()
    forced = False
    while time.time() - t0 < timeout:
        st = _req("GET", "/api/status")
        if not st.get("running"):
            return st
        if (not forced) and force_stop_after is not None and (time.time() - t0) >= float(force_stop_after):
            try:
                _req("POST", "/api/stop", {})
                forced = True
                print("[matrix] wait_idle force_stop", flush=True)
            except Exception as exc:
                print(f"[matrix] wait_idle stop fail: {exc}", flush=True)
        time.sleep(2)
    try:
        _req("POST", "/api/stop", {})
    except Exception:
        pass
    time.sleep(2)
    return _req("GET", "/api/status")


def wait_done(timeout=TIMEOUT_PER_JOB, label=""):
    t0 = time.time()
    last = None
    last_print = 0.0
    while time.time() - t0 < timeout:
        st = _req("GET", "/api/status")
        last = st
        if not st.get("running"):
            return st
        now = time.time()
        if now - last_print >= 60:
            last_print = now
            print(
                f"[matrix] {label} running ok={st.get('success')} fail={st.get('fail')} "
                f"pending={st.get('pending_sso')} await_pool={st.get('awaiting_pool')} "
                f"phase={st.get('phase')} elapsed={int(now - t0)}s",
                flush=True,
            )
        time.sleep(5)
    try:
        _req("POST", "/api/stop", {})
    except Exception:
        pass
    time.sleep(3)
    return last or _req("GET", "/api/status")


def put_config(patch: dict):
    return _req("PUT", "/api/config", patch)


def write_config_file(cfg: dict):
    cfg_path = ROOT / "config.json"
    try:
        c = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        c = {}
    PRESERVE = (
        "sub2api_admin_email",
        "sub2api_admin_password",
        "sub2api_base_url",
        "grok2api_remote_app_key",
        "grok2api_remote_base",
        "web_access_key",
        "outlook_accounts",
        "aol_accounts",
        "proxy_list",
        "duckmail_api_key",
        "cloudflare_api_key",
        "cloudflare_api_base",
        "cpa_management_key",
        "yyds_api_key",
        "yyds_jwt",
        "outlook_client_id",
    )
    prev = dict(c)
    c.update(cfg)
    for k in PRESERVE:
        if k in prev and prev.get(k) not in (None, ""):
            c[k] = prev[k]
        elif k in prev:
            c[k] = prev[k]
    cfg_path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


def clear_logs():
    try:
        _req("POST", "/api/logs/clear", {})
    except Exception:
        try:
            _req("DELETE", "/api/logs")
        except Exception:
            pass


def apply_cell_config(mode, proxy, email, workers=WORKERS, count=COUNT):
    cfg = {
        "register_mode": mode,
        "proxy_mode": proxy,
        "email_provider": email,
        "workers": workers,
        "thread_count": workers,
        "register_count": count,
        "email_preflight_on_start": True,
        "email_preflight_continuous": True,
        "email_preflight_limit": int(PREHEAT),
        "email_preflight_warm_ahead": int(PREHEAT),
        # 18r43 silent stable multi-thread
        "browser_silent": True,
        "browser_start_minimized": True,
        "browser_window_x": -32000,
        "browser_window_y": 0,
        "browser_window_width": 900,
        "browser_window_height": 640,
    }
    write_config_file(cfg)
    put_config({k: cfg[k] for k in cfg if cfg.get(k) is not None})
    return cfg


def start_job(count, workers, job_kind="register"):
    return _req(
        "POST",
        "/api/start",
        {"count": int(count), "workers": int(workers), "job_kind": job_kind},
        timeout=120,
    )


def browser_regkit_count():
    try:
        import subprocess

        ps = (
            "(Get-Process chrome,msedge,chromium -ErrorAction SilentlyContinue | "
            "Where-Object { $_.MainWindowTitle -ne '' }).Count"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            timeout=15,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return int((out or "0").strip().splitlines()[-1] or 0)
    except Exception:
        return -1


def run_register_round(mode, proxy, email, round_i, workers=WORKERS, count=COUNT):
    cell = f"{mode}__{proxy}__{email}"
    name = f"{cell}__r{round_i}"
    print(f"\n===== CELL {name} workers={workers} count={count} preheat={PREHEAT} silent=1 =====", flush=True)
    wait_idle(timeout=360, force_stop_after=45)
    clear_logs()
    apply_cell_config(mode, proxy, email, workers=workers, count=count)
    t0 = time.time()
    try:
        start = start_job(count, workers, "register")
    except Exception as exc:
        return {
            "cell": name,
            "kind": "register",
            "error": f"start_fail:{exc}",
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
    print("start", start, flush=True)
    st = wait_done(TIMEOUT_PER_JOB, label=name)
    result = {
        "cell": name,
        "kind": "register",
        "mode": mode,
        "proxy": proxy,
        "email": email,
        "round": round_i,
        "workers": workers,
        "count": count,
        "preheat": PREHEAT,
        "silent": True,
        "success": st.get("success"),
        "fail": st.get("fail"),
        "pending_sso": st.get("pending_sso"),
        "skipped": st.get("skipped"),
        "phase": st.get("phase"),
        "running": st.get("running"),
        "error": st.get("error") or "",
        "elapsed_sec": round(time.time() - t0, 1),
        "last_event": (st.get("last_event") or "")[:180],
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    print(
        "result",
        {k: result[k] for k in ("cell", "success", "fail", "pending_sso", "elapsed_sec", "error")},
        flush=True,
    )
    return result


def run_pending_round(proxy, round_i, workers=WORKERS, count=COUNT):
    name = f"pending_sso_recovery__{proxy}__r{round_i}"
    print(f"\n===== CELL {name} =====", flush=True)
    wait_idle(timeout=360, force_stop_after=45)
    clear_logs()
    apply_cell_config("hybrid", proxy, "outlook", workers=workers, count=count)
    t0 = time.time()
    try:
        try:
            start = _req(
                "POST",
                "/api/pending-sso/recover",
                {"count": count, "workers": workers},
                timeout=120,
            )
        except Exception:
            start = start_job(count, workers, "pending_sso_recovery")
    except Exception as exc:
        return {
            "cell": name,
            "kind": "pending_sso_recovery",
            "error": f"start_fail:{exc}",
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
    print("pending start", start, flush=True)
    st = wait_done(TIMEOUT_PER_JOB, label=name)
    return {
        "cell": name,
        "kind": "pending_sso_recovery",
        "proxy": proxy,
        "round": round_i,
        "workers": workers,
        "count": count,
        "silent": True,
        "success": st.get("success"),
        "fail": st.get("fail"),
        "pending_sso": st.get("pending_sso"),
        "error": st.get("error") or "",
        "elapsed_sec": round(time.time() - t0, 1),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


def run_stop_test(round_i, workers=min(WORKERS, 4), count=min(COUNT, 20)):
    name = f"stop_registration__hybrid__socks5_list__r{round_i}"
    print(f"\n===== CELL {name} stop_after={STOP_TEST_AFTER_SEC}s =====", flush=True)
    wait_idle(timeout=300, force_stop_after=30)
    clear_logs()
    apply_cell_config("hybrid", "socks5_list", "outlook", workers=workers, count=count)
    t0 = time.time()
    browsers_before = browser_regkit_count()
    try:
        start = start_job(count, workers, "register")
    except Exception as exc:
        return {
            "cell": name,
            "kind": "stop_test",
            "error": f"start_fail:{exc}",
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
    print("stop-test start", start, flush=True)
    for _ in range(60):
        st = _req("GET", "/api/status")
        if st.get("running"):
            break
        time.sleep(0.5)
    time.sleep(STOP_TEST_AFTER_SEC)
    stop_resp = _req("POST", "/api/stop", {})
    idle_at = None
    for i in range(60):
        st = _req("GET", "/api/status")
        if not st.get("running"):
            idle_at = time.time() - t0
            break
        if i in (10, 20, 30, 45):
            try:
                _req("POST", "/api/stop", {})
            except Exception:
                pass
        time.sleep(2)
    time.sleep(2)
    browsers_after = browser_regkit_count()
    st = _req("GET", "/api/status")
    return {
        "cell": name,
        "kind": "stop_test",
        "round": round_i,
        "workers": workers,
        "count": count,
        "stop_resp": stop_resp,
        "running_after": bool(st.get("running")),
        "idle_after_sec": idle_at,
        "browsers_before": browsers_before,
        "browsers_after": browsers_after,
        "stop_ok": (not bool(st.get("running"))),
        "phase": st.get("phase"),
        "last_event": (st.get("last_event") or "")[:180],
        "elapsed_sec": round(time.time() - t0, 1),
        "error": "",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl = OUT / f"matrix_18r43_{stamp}.jsonl"
    summary_path = OUT / f"matrix_18r43_{stamp}_summary.json"
    report_path = OUT / f"MATRIX_18r43_{stamp}.md"
    board = OUT / "_CODEX_MATRIX_18r43_BOARD.md"

    cells = []
    for mode in MODES:
        for proxy in PROXIES:
            for email in EMAILS:
                for r in range(1, ROUNDS_PER_CELL + 1):
                    cells.append(("register", mode, proxy, email, r))
    for proxy in PROXIES:
        for r in range(1, ROUNDS_PER_CELL + 1):
            cells.append(("pending", None, proxy, None, r))
    if INCLUDE_STOP_TESTS:
        for r in range(1, ROUNDS_PER_CELL + 1):
            cells.append(("stop", None, None, None, r))

    print(
        f"18r43 silent stable matrix start workers={WORKERS} count={COUNT} preheat={PREHEAT} "
        f"cells={len(cells)} stamp={stamp}",
        flush=True,
    )
    results = []
    for idx, item in enumerate(cells, 1):
        kind, mode, proxy, email, r = item
        print(f"\n#### progress {idx}/{len(cells)} kind={kind}", flush=True)
        if kind == "register":
            res = run_register_round(mode, proxy, email, r)
        elif kind == "pending":
            res = run_pending_round(proxy, r)
        else:
            res = run_stop_test(r)
        results.append(res)
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        # live board
        lines = [
            f"# Matrix 18r43 silent stable MT board",
            f"updated={datetime.now().isoformat(timespec='seconds')}",
            f"progress={idx}/{len(cells)}",
            f"workers={WORKERS} count={COUNT} preheat={PREHEAT} silent=1",
            "",
            "## Done",
        ]
        for rr in results:
            lines.append(
                f"- `{rr.get('cell')}` ok={rr.get('success')} fail={rr.get('fail')} "
                f"pending={rr.get('pending_sso')} stop_ok={rr.get('stop_ok')} "
                f"err={(rr.get('error') or '')[:80]}"
            )
        board.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        f"# Matrix 18r43 silent stable multi-thread",
        f"stamp={stamp}",
        f"workers={WORKERS}",
        f"count={COUNT}",
        f"preheat={PREHEAT}",
        f"rounds_per_cell={ROUNDS_PER_CELL}",
        f"proxy=socks5_list",
        f"silent=browser_silent headed minimize/offscreen",
        "",
        "## Cells",
    ]
    for rr in results:
        md.append(
            f"- `{rr.get('cell')}` kind={rr.get('kind')} success={rr.get('success')} "
            f"fail={rr.get('fail')} pending={rr.get('pending_sso')} "
            f"stop_ok={rr.get('stop_ok')} err={rr.get('error') or ''}"
        )
    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"DONE jsonl={jsonl}", flush=True)
    print(f"DONE summary={summary_path}", flush=True)
    print(f"DONE report={report_path}", flush=True)


if __name__ == "__main__":
    main()
