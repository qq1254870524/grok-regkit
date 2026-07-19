# -*- coding: utf-8 -*-
"""18r30 multi-thread matrix cross runner.

Combos: register_mode x proxy_mode x email_provider
Each cell: workers=2, count=rounds (default 10 accounts via one job, or rounds of count=1).
Does NOT kill 8010/8080/8317/8318. Only uses /api/start /api/stop /api/config.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
BASE = "http://127.0.0.1:8092"
OUT = ROOT / "matrix_runs"
OUT.mkdir(exist_ok=True)

MODES = ["hybrid", "browser"]
PROXIES = ["direct", "socks5_list"]
EMAILS = ["aol", "outlook"]
WORKERS = 2
ROUNDS = 10  # accounts per cell (one job with count=ROUNDS)
TIMEOUT_PER_JOB = 3600 * 3  # 3h max per cell


def _req(method: str, path: str, body=None, timeout=60):
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def wait_idle(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = _req("GET", "/api/status")
        if not st.get("running"):
            return st
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
        time.sleep(5)
    # force stop registration only
    try:
        _req("POST", "/api/stop", {})
    except Exception:
        pass
    time.sleep(3)
    return last or _req("GET", "/api/status")


def put_config(patch: dict):
    # merge: get full config not available as full; put partial fields supported by ConfigBody
    return _req("PUT", "/api/config", patch)


def run_cell(mode, proxy, email, workers=WORKERS, count=ROUNDS):
    cell = f"{mode}__{proxy}__{email}"
    print(f"\n===== CELL {cell} workers={workers} count={count} =====", flush=True)
    wait_idle(90)
    # clear logs optional
    try:
        _req("POST", "/api/logs/clear", {})
    except Exception:
        pass
    cfg = {
        "register_mode": mode,
        "proxy_mode": proxy if proxy != "socks5_list" else "socks5_list",
        "workers": workers,
        "thread_count": workers,
        "register_count": count,
        "email_provider": email,
        "email_preflight_on_start": True,
        "email_preflight_limit": max(4, int(workers) * 2),  # 18r30b faster preflight sample
        "mail_top_per_folder": 5,
    }
    # put_config supports email_provider in ConfigBody; also mirror config.json
    put_config(cfg)
    # force email_provider into config.json (ConfigBody may omit it)
    cfg_path = ROOT / "config.json"
    try:
        c = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        c = {}
    # 18r31e: never wipe secrets / pool textareas when matrix rewrites config.json
    PRESERVE_NONEMPTY = (
        "sub2api_admin_email", "sub2api_admin_password", "sub2api_base_url",
        "grok2api_remote_app_key", "grok2api_remote_base", "web_access_key",
        "outlook_accounts", "aol_accounts", "proxy_list", "duckmail_api_key",
    )
    prev = dict(c)
    c.update(cfg)
    for k in PRESERVE_NONEMPTY:
        oldv = prev.get(k)
        newv = c.get(k)
        if oldv and (newv is None or (isinstance(newv, str) and not str(newv).strip())):
            c[k] = oldv
    c["email_provider"] = email
    c["email_preflight_continuous"] = True
    c["email_preflight_on_start"] = True
    c["mail_top_per_folder"] = 5
    c["browser_window_width"] = int(c.get("browser_window_width") or 900)
    c["browser_window_height"] = int(c.get("browser_window_height") or 640)
    if proxy == "socks5_list":
        c["proxy_mode"] = "socks5_list"
    elif proxy == "direct":
        c["proxy_mode"] = "direct"
        c["proxy"] = ""
    cfg_path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    # reload config by put again of known fields
    put_config({k: c.get(k) for k in ("register_mode", "proxy_mode", "workers", "thread_count", "register_count", "email_provider", "email_preflight_on_start", "email_preflight_limit", "mail_top_per_folder") if k in c and c.get(k) is not None})

    start = _req("POST", "/api/start", {"count": count, "workers": workers})
    print("start", start, flush=True)
    st = wait_done()
    result = {
        "cell": cell,
        "mode": mode,
        "proxy": proxy,
        "email": email,
        "workers": workers,
        "count": count,
        "success": st.get("success"),
        "fail": st.get("fail"),
        "pending_sso": st.get("pending_sso"),
        "skipped": st.get("skipped"),
        "error": st.get("error"),
        "last_event": st.get("last_event"),
        "finished_at": st.get("finished_at"),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    print("result", result, flush=True)
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--smoke", action="store_true", help="1 cell hybrid socks5 aol count=2")
    ap.add_argument("--cells", type=str, default="", help="comma cells mode__proxy__email")
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = OUT / f"matrix_18r30_{stamp}.jsonl"
    summary = []

    if args.smoke:
        cells = [("hybrid", "socks5_list", "aol")]
        rounds = 2
    elif args.cells:
        cells = []
        for part in args.cells.split(","):
            a, b, c = part.strip().split("__")
            cells.append((a, b, c))
        rounds = args.rounds
    else:
        cells = [(m, p, e) for m in MODES for p in PROXIES for e in EMAILS]
        rounds = args.rounds

    print(f"18r30 matrix start cells={len(cells)} rounds={rounds} workers={args.workers}", flush=True)
    print(f"report={report}", flush=True)

    for mode, proxy, email in cells:
        try:
            r = run_cell(mode, proxy, email, workers=args.workers, count=rounds)
        except Exception as exc:
            r = {
                "cell": f"{mode}__{proxy}__{email}",
                "error": str(exc),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            print("CELL FAIL", r, flush=True)
        summary.append(r)
        with report.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # pending recover multi-thread smoke after matrix
    try:
        wait_idle(60)
        put_config({"workers": args.workers, "thread_count": args.workers})
        try:
            start = _req("POST", "/api/pending-sso/recover", {"count": min(rounds, 10), "workers": args.workers})
            print("pending start", start, flush=True)
            st = wait_done()
            pr = {
                "cell": "pending_sso_recovery",
                "workers": args.workers,
                "success": st.get("success"),
                "fail": st.get("fail"),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        except Exception as exc:
            pr = {"cell": "pending_sso_recovery", "error": str(exc)}
        summary.append(pr)
        with report.open("a", encoding="utf-8") as f:
            f.write(json.dumps(pr, ensure_ascii=False) + "\n")
    except Exception as exc:
        print("pending block", exc, flush=True)

    sum_path = OUT / f"matrix_18r30_{stamp}_summary.json"
    sum_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", sum_path, flush=True)
    # also write short markdown
    md = OUT / f"MATRIX_18r30_{stamp}.md"
    lines = ["# Matrix 18r30 multi-thread", f"stamp={stamp}", f"workers={args.workers}", ""]
    for r in summary:
        lines.append(f"- `{r.get('cell')}` success={r.get('success')} fail={r.get('fail')} pending={r.get('pending_sso')} err={r.get('error') or ''}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("MD", md, flush=True)


if __name__ == "__main__":
    main()
