# -*- coding: utf-8 -*-
"""18r40 multi-thread matrix cross runner.

User request 2026-07-20:
- workers=2, email_preheat=4, register_count=4
- modes: hybrid + full browser
- proxy: direct + SOCKS5
- mail: Microsoft(outlook) + AOL
- secondary SSO recovery + stop-registration tests
- each cross cell at least 2 rounds
- multi-thread version
- live monitor friendly (jsonl + md board)
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

MODES = ["hybrid", "browser"]
PROXIES = ["direct", "socks5_list"]
EMAILS = ["outlook", "aol"]
WORKERS = 2
COUNT = 4
ROUNDS_PER_CELL = 2
PREHEAT = 4
TIMEOUT_PER_JOB = 45 * 60  # 45min per cell-round
STOP_TEST_AFTER_SEC = 25


def _req(method: str, path: str, body=None, timeout=60, retries=6):
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
            time.sleep(min(2 + i * 1.5, 10))
    raise RuntimeError(f"API {method} {path} failed: {last}")


def wait_idle(timeout=180, force_stop_after=45):
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


def wait_done(timeout=TIMEOUT_PER_JOB):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        st = _req("GET", "/api/status")
        last = st
        if not st.get("running"):
            return st
        time.sleep(4)
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
    )
    prev = dict(c)
    c.update(cfg)
    for k in PRESERVE:
        oldv = prev.get(k)
        newv = c.get(k)
        if oldv and (newv is None or (isinstance(newv, str) and not str(newv).strip())):
            c[k] = oldv
    cfg_path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


def apply_cell_config(mode, proxy, email, workers=WORKERS, count=COUNT):
    cfg = {
        "register_mode": mode,
        "proxy_mode": "socks5_list" if proxy == "socks5_list" else "direct",
        "workers": workers,
        "thread_count": workers,
        "register_count": count,
        "email_provider": email,
        "email_preflight_on_start": True,
        "email_preflight_continuous": True,
        "email_preflight_limit": int(PREHEAT),
        "email_preflight_warm_ahead": int(PREHEAT),
        "mail_top_per_folder": 5,
    }
    if cfg["proxy_mode"] == "direct":
        cfg["proxy"] = ""
    write_config_file(cfg)
    put_config({k: cfg[k] for k in cfg if cfg.get(k) is not None})
    return cfg


def clear_logs():
    try:
        _req("POST", "/api/logs/clear", {})
    except Exception:
        pass


def start_job(count, workers, job_kind="register"):
    return _req(
        "POST",
        "/api/start",
        {"count": int(count), "workers": int(workers), "job_kind": job_kind},
        timeout=30,
    )


def browser_regkit_count():
    try:
        import subprocess

        ps = r"""
$pat = 'grok-regkit|\.chrome-data|DrissionPage'
@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|msedge|chromedriver)\.exe$' -and
    $_.CommandLine -and ($_.CommandLine -match $pat)
  }).Count
"""
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
    print(f"\n===== CELL {name} workers={workers} count={count} preheat={PREHEAT} =====", flush=True)
    wait_idle(timeout=240, force_stop_after=30)
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
    st = wait_done(TIMEOUT_PER_JOB)
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
    print("result", {k: result[k] for k in ("cell", "success", "fail", "pending_sso", "elapsed_sec", "error")}, flush=True)
    return result


def run_pending_round(proxy, round_i, workers=WORKERS, count=COUNT):
    name = f"pending_sso_recovery__{proxy}__r{round_i}"
    print(f"\n===== CELL {name} =====", flush=True)
    wait_idle(timeout=240, force_stop_after=30)
    clear_logs()
    apply_cell_config("hybrid", proxy, "outlook", workers=workers, count=count)
    t0 = time.time()
    try:
        # prefer dedicated endpoint if present
        try:
            start = _req("POST", "/api/pending-sso/recover", {"count": count, "workers": workers})
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
    st = wait_done(TIMEOUT_PER_JOB)
    return {
        "cell": name,
        "kind": "pending_sso_recovery",
        "proxy": proxy,
        "round": round_i,
        "workers": workers,
        "count": count,
        "success": st.get("success"),
        "fail": st.get("fail"),
        "pending_sso": st.get("pending_sso"),
        "error": st.get("error") or "",
        "elapsed_sec": round(time.time() - t0, 1),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


def run_stop_test(round_i, workers=WORKERS, count=COUNT):
    name = f"stop_registration__hybrid__direct__r{round_i}"
    print(f"\n===== CELL {name} stop_after={STOP_TEST_AFTER_SEC}s =====", flush=True)
    wait_idle(timeout=240, force_stop_after=20)
    clear_logs()
    apply_cell_config("hybrid", "direct", "outlook", workers=workers, count=count)
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
    # wait until running or timeout
    for _ in range(40):
        st = _req("GET", "/api/status")
        if st.get("running"):
            break
        time.sleep(0.5)
    time.sleep(STOP_TEST_AFTER_SEC)
    stop_resp = _req("POST", "/api/stop", {})
    # poll until idle or 90s
    idle_at = None
    for i in range(45):
        st = _req("GET", "/api/status")
        if not st.get("running"):
            idle_at = time.time() - t0
            break
        if i in (10, 20, 30):
            try:
                _req("POST", "/api/stop", {})
            except Exception:
                pass
        time.sleep(2)
    time.sleep(2)
    browsers_after = browser_regkit_count()
    st = _req("GET", "/api/status")
    ok_stop = (not bool(st.get("running"))) and (browsers_after <= max(0, browsers_before))
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
        "stop_ok": ok_stop,
        "phase": st.get("phase"),
        "last_event": (st.get("last_event") or "")[:180],
        "elapsed_sec": round(time.time() - t0, 1),
        "error": "" if ok_stop else "stop_did_not_clear_running_or_browsers",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = OUT / f"matrix_18r40_{stamp}.jsonl"
    md_path = OUT / f"MATRIX_18r40_{stamp}.md"
    board = OUT / "_CODEX_MATRIX_18r40_BOARD.md"
    summary = []

    print(
        f"18r40 matrix start workers={WORKERS} count={COUNT} preheat={PREHEAT} "
        f"rounds_per_cell={ROUNDS_PER_CELL} report={report}",
        flush=True,
    )

    # 1) register matrix 8 cells x 2 rounds
    for mode in MODES:
        for proxy in PROXIES:
            for email in EMAILS:
                for r in range(1, ROUNDS_PER_CELL + 1):
                    try:
                        row = run_register_round(mode, proxy, email, r)
                    except Exception as exc:
                        row = {
                            "cell": f"{mode}__{proxy}__{email}__r{r}",
                            "kind": "register",
                            "error": str(exc),
                            "ts": datetime.now().isoformat(timespec="seconds"),
                        }
                        print("CELL FAIL", row, flush=True)
                    summary.append(row)
                    with report.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    board.write_text(
                        "# 18r40 Matrix Board\n\n"
                        f"updated={datetime.now().isoformat(timespec='seconds')}\n"
                        f"done={len(summary)}\n"
                        f"last={row.get('cell')} ok={row.get('success')} fail={row.get('fail')} "
                        f"pend={row.get('pending_sso')} err={row.get('error')}\n",
                        encoding="utf-8",
                    )

    # 2) pending SSO recovery 2 proxies x 2 rounds
    for proxy in PROXIES:
        for r in range(1, ROUNDS_PER_CELL + 1):
            try:
                row = run_pending_round(proxy, r)
            except Exception as exc:
                row = {
                    "cell": f"pending_sso_recovery__{proxy}__r{r}",
                    "kind": "pending_sso_recovery",
                    "error": str(exc),
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            summary.append(row)
            with report.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 3) stop registration tests x2
    for r in range(1, ROUNDS_PER_CELL + 1):
        try:
            row = run_stop_test(r)
        except Exception as exc:
            row = {
                "cell": f"stop_registration__r{r}",
                "kind": "stop_test",
                "error": str(exc),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        summary.append(row)
        with report.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    sum_path = OUT / f"matrix_18r40_{stamp}_summary.json"
    sum_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Matrix 18r40 multi-thread",
        f"stamp={stamp}",
        f"workers={WORKERS}",
        f"count={COUNT}",
        f"preheat={PREHEAT}",
        f"rounds_per_cell={ROUNDS_PER_CELL}",
        "",
        "## Cells",
    ]
    for r in summary:
        lines.append(
            f"- `{r.get('cell')}` kind={r.get('kind')} success={r.get('success')} "
            f"fail={r.get('fail')} pending={r.get('pending_sso')} stop_ok={r.get('stop_ok')} "
            f"err={r.get('error') or ''}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    board.write_text(
        "# 18r40 Matrix Board DONE\n\n"
        f"updated={datetime.now().isoformat(timespec='seconds')}\n"
        f"cells={len(summary)}\n"
        f"summary={sum_path.name}\n"
        f"report={report.name}\n",
        encoding="utf-8",
    )
    print("DONE", sum_path, flush=True)
    print("MD", md_path, flush=True)


if __name__ == "__main__":
    main()
