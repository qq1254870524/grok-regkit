# 18r43m: no success top-up re-run (attempt-based cells; one run per cell)
# 18r43j: resume attach mid-cell even when start_idx>0
# 18r43i: register cells top-up until success>=count; resume re-runs incomplete register cells
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

18r43e resume:
- state file tracks stamp/results/current cell
- if matrix dies mid-cell, restart attaches to running web job (no force stop)
- skip completed cells from jsonl/state
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
STATE_PATH = OUT / "_CODEX_18r43_MATRIX_STATE.json"

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
        # 18r43d: force multi post-success workers so awaiting_pool drains under workers=20
        "post_success_async": True,
        "post_success_workers": 6,
        # 18r43f: permanent permission-denied fail-fast; short verify keeps awaiting_pool moving
        "sub2api_verify_after_add": True,
        "sub2api_require_verify_success": False,
        "sub2api_verify_attempts": 1,
        "sub2api_verify_timeout_sec": 35,
        "sub2api_verify_retry_delay_sec": 1,
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


def cell_name(kind, mode, proxy, email, round_i):
    if kind == "register":
        return f"{mode}__{proxy}__{email}__r{round_i}"
    if kind == "pending":
        return f"pending_sso_recovery__{proxy}__r{round_i}"
    return f"stop_registration__hybrid__socks5_list__r{round_i}"


def build_cells():
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
    return cells


def save_state(state: dict):
    try:
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(STATE_PATH)
    except Exception as exc:
        print(f"[matrix] save_state fail: {exc}", flush=True)


def load_state() -> dict | None:
    try:
        if STATE_PATH.is_file():
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and not data.get("done"):
                return data
    except Exception:
        pass
    return None


def load_results_from_jsonl(path: Path) -> list:
    results = []
    if not path.is_file():
        return results
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except Exception:
            pass
    return results



def _register_success_ok(success, count) -> bool:
    """True when cell met success target (18r43g success-based)."""
    try:
        ok = int(success or 0)
        tgt = int(count or 0)
    except Exception:
        return False
    if tgt <= 0:
        return True
    return ok >= tgt


def topup_register_until_target(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, first_result=None, max_topup=0):
    """18r43m: default max_topup=0 — do not re-run full count (attempt-based quota)."""
    name = f"{mode}__{proxy}__{email}__r{round_i}"
    res = first_result
    runs = []
    if res is not None:
        runs.append(res)
    topup = 0
    while not _register_success_ok((res or {}).get("success"), count) and topup < int(max_topup):
        topup += 1
        ok0 = int((res or {}).get("success") or 0)
        print(
            f"[matrix] 18r43i top-up {topup}/{max_topup} cell={name} success={ok0}<{count} -> re-run full count",
            flush=True,
        )
        res = run_register_round(mode, proxy, email, round_i, workers=workers, count=count, attach_if_running=False)
        res["topup_round"] = topup
        res["topup_prev_success"] = ok0
        runs.append(res)
    if res is None:
        res = run_register_round(mode, proxy, email, round_i, workers=workers, count=count)
        runs.append(res)
    # aggregate note
    try:
        res = dict(res or {})
        res["topup_runs"] = len(runs)
        res["topup_successes"] = [int(r.get("success") or 0) for r in runs]
        res["success_target_met"] = _register_success_ok(res.get("success"), count)
    except Exception:
        pass
    return res


def discover_resume():
    """Return (stamp, jsonl, summary_path, report_path, results, start_idx) or None for fresh."""
    st = load_state()
    if st and st.get("stamp"):
        stamp = str(st["stamp"])
        jsonl = OUT / f"matrix_18r43_{stamp}.jsonl"
        results = list(st.get("results") or [])
        if not results:
            results = load_results_from_jsonl(jsonl)
        # 18r43i: keep completed cells even if success<COUNT (historical attempt-based);
        # top-up only applies to cells run after this process start.
        print(f"[matrix] resume from state stamp={stamp} done_cells={len(results)}", flush=True)
        return (
            stamp,
            jsonl,
            OUT / f"matrix_18r43_{stamp}_summary.json",
            OUT / f"MATRIX_18r43_{stamp}.md",
            results,
            len(results),
        )
    # fallback: newest incomplete jsonl without summary
    jsonls = sorted(OUT.glob("matrix_18r43_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for jl in jsonls:
        name = jl.name  # matrix_18r43_STAMP.jsonl
        stamp = name[len("matrix_18r43_") : -len(".jsonl")]
        summary = OUT / f"matrix_18r43_{stamp}_summary.json"
        if summary.is_file():
            continue
        results = load_results_from_jsonl(jl)
        print(f"[matrix] resume from jsonl stamp={stamp} done_cells={len(results)}", flush=True)
        return stamp, jl, summary, OUT / f"MATRIX_18r43_{stamp}.md", results, len(results)
    return None


def result_from_status(name, kind, st, t0, **extra):
    base = {
        "cell": name,
        "kind": kind,
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
        "resumed_attach": bool(extra.pop("resumed_attach", False)),
    }
    base.update(extra)
    return base



def run_register_round(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, attach_if_running=False):
    cell = f"{mode}__{proxy}__{email}"
    name = f"{cell}__r{round_i}"
    print(f"\n===== CELL {name} workers={workers} count={count} preheat={PREHEAT} silent=1 =====", flush=True)
    t0 = time.time()
    try:
        st0 = _req("GET", "/api/status")
    except Exception as exc:
        st0 = {"running": False, "error": str(exc)}
    if attach_if_running and st0.get("running"):
        print(f"[matrix] attach running job as {name} (no force-stop)", flush=True)
        st = wait_done(TIMEOUT_PER_JOB, label=name)
        result = result_from_status(
            name,
            "register",
            st,
            t0,
            mode=mode,
            proxy=proxy,
            email=email,
            round=round_i,
            workers=workers,
            count=count,
            preheat=PREHEAT,
            silent=True,
            resumed_attach=True,
        )
        print(
            "result",
            {k: result[k] for k in ("cell", "success", "fail", "pending_sso", "elapsed_sec", "error")},
            flush=True,
        )
        return result

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
    result = result_from_status(
        name,
        "register",
        st,
        t0,
        mode=mode,
        proxy=proxy,
        email=email,
        round=round_i,
        workers=workers,
        count=count,
        preheat=PREHEAT,
        silent=True,
    )
    print(
        "result",
        {k: result[k] for k in ("cell", "success", "fail", "pending_sso", "elapsed_sec", "error")},
        flush=True,
    )
    return result


def run_pending_round(proxy, round_i, workers=WORKERS, count=COUNT, attach_if_running=False):
    name = f"pending_sso_recovery__{proxy}__r{round_i}"
    print(f"\n===== CELL {name} =====", flush=True)
    t0 = time.time()
    try:
        st0 = _req("GET", "/api/status")
    except Exception:
        st0 = {"running": False}
    if attach_if_running and st0.get("running") and str(st0.get("job_kind") or "") in (
        "pending_sso_recovery",
        "pending_sso",
    ):
        print(f"[matrix] attach running pending job as {name}", flush=True)
        st = wait_done(TIMEOUT_PER_JOB, label=name)
        return result_from_status(
            name,
            "pending_sso_recovery",
            st,
            t0,
            proxy=proxy,
            round=round_i,
            workers=workers,
            count=count,
            silent=True,
            resumed_attach=True,
        )

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
    return result_from_status(
        name,
        "pending_sso_recovery",
        st,
        t0,
        proxy=proxy,
        round=round_i,
        workers=workers,
        count=count,
        silent=True,
    )


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


def write_board(board: Path, results: list, idx: int, total: int):
    lines = [
        "# Matrix 18r43 silent stable MT board",
        f"updated={datetime.now().isoformat(timespec='seconds')}",
        f"progress={idx}/{total}",
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


def main():
    cells = build_cells()
    board = OUT / "_CODEX_MATRIX_18r43_BOARD.md"
    resume = discover_resume()
    if resume:
        stamp, jsonl, summary_path, report_path, results, start_idx = resume
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jsonl = OUT / f"matrix_18r43_{stamp}.jsonl"
        summary_path = OUT / f"matrix_18r43_{stamp}_summary.json"
        report_path = OUT / f"MATRIX_18r43_{stamp}.md"
        results = []
        start_idx = 0

    # if no completed cells but a long job is running, treat as cell0 attach
    try:
        live = _req("GET", "/api/status")
    except Exception:
        live = {"running": False}
    attach_first = bool(live.get("running"))  # 18r43j: attach mid-cell even if start_idx>0

    print(
        f"18r43 silent stable matrix start workers={WORKERS} count={COUNT} preheat={PREHEAT} "
        f"cells={len(cells)} stamp={stamp} resume_from={start_idx} attach_first={attach_first}",
        flush=True,
    )
    save_state(
        {
            "stamp": stamp,
            "done": False,
            "start_idx": start_idx,
            "current_cell": None,
            "results": results,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
    )

    for idx, item in enumerate(cells, 1):
        if idx <= start_idx:
            continue
        kind, mode, proxy, email, r = item
        name = cell_name(kind, mode, proxy, email, r)
        print(f"\n#### progress {idx}/{len(cells)} kind={kind} cell={name}", flush=True)
        save_state(
            {
                "stamp": stamp,
                "done": False,
                "start_idx": idx - 1,
                "current_cell": name,
                "current_idx": idx,
                "results": results,
                "updated": datetime.now().isoformat(timespec="seconds"),
            }
        )
        attach = attach_first and idx == (start_idx + 1)
        if kind == "register":
            res = run_register_round(mode, proxy, email, r, attach_if_running=attach)
            # 18r43i: attempt-based legacy jobs stop at ~count attempts; top-up to success target
            if not _register_success_ok(res.get("success"), COUNT):
                res = topup_register_until_target(
                    mode, proxy, email, r, workers=WORKERS, count=COUNT, first_result=res, max_topup=3
                )
        elif kind == "pending":
            res = run_pending_round(proxy, r, attach_if_running=attach)
        else:
            res = run_stop_test(r)
        attach_first = False
        results.append(res)
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        write_board(board, results, idx, len(cells))
        save_state(
            {
                "stamp": stamp,
                "done": False,
                "start_idx": idx,
                "current_cell": None,
                "current_idx": idx,
                "results": results,
                "updated": datetime.now().isoformat(timespec="seconds"),
            }
        )

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
    save_state(
        {
            "stamp": stamp,
            "done": True,
            "start_idx": len(cells),
            "results": results,
            "summary": str(summary_path),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print(f"DONE jsonl={jsonl}", flush=True)
    print(f"DONE summary={summary_path}", flush=True)
    print(f"DONE report={report_path}", flush=True)


if __name__ == "__main__":
    main()
