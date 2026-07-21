# -*- coding: utf-8 -*-
"""
18r44 silent-stable matrix: workers=2 preheat=4 count=4
proxy=socks5 only; modes hybrid/browser; mail outlook/aol;
pending_sso_recovery x2; stop_test x2; each cell >=2 rounds.
Monitors G2A/Sub2 pool deltas; full plaintext logs (user: no desensitization).
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
API = "http://127.0.0.1:8092"
WORKERS = 2
PREHEAT = 4
COUNT = 4
ROUNDS = 2
JOB_TIMEOUT = 900  # 4 accounts * workers=2

import os

STATE = ROOT / "_CODEX_18r44_MATRIX_STATE.json"
_env_out = (os.environ.get("MATRIX_OUT") or "").strip()
_state_out = ""
if not _env_out and STATE.is_file():
    try:
        _state_out = str(json.loads(STATE.read_text(encoding="utf-8")).get("out") or "").strip()
    except Exception:
        _state_out = ""
if _env_out:
    OUT = Path(_env_out)
elif _state_out and "matrix_18r44_silent_" in _state_out:
    # resume same run directory when state points at active matrix_out
    OUT = Path(_state_out)
else:
    OUT = ROOT / "matrix_runs" / f"matrix_18r44_silent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = OUT / "summary.jsonl"
LOGF = OUT / "runner.log"
BOARD = OUT / "BOARD.md"
SUM = OUT / "summary.jsonl"

CELLS = [
    {"name": "hybrid__socks5__outlook", "kind": "register", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "hybrid__socks5__aol", "kind": "register", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "browser__socks5__outlook", "kind": "register", "register_mode": "browser", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "browser__socks5__aol", "kind": "register", "register_mode": "browser", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "pending_sso_recovery__socks5", "kind": "pending_sso_recovery", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "stop_test__hybrid__socks5", "kind": "stop_test", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
]



def completed_rounds(summary_path: Path) -> set[tuple[str, int]]:
    """Skip cells already recorded in summary.jsonl when resuming same OUT."""
    done: set[tuple[str, int]] = set()
    if not summary_path.is_file():
        return done
    try:
        for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            name = str(obj.get("cell") or "")
            try:
                rnd = int(obj.get("round") or 0)
            except Exception:
                rnd = 0
            if name and rnd > 0 and obj.get("ok") is not None:
                done.add((name, rnd))
    except Exception:
        return done
    return done

def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOGF.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, body: dict | None = None, timeout: int = 60, retries: int = 6):
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                j = json.loads(raw) if raw else {}
            except Exception:
                j = {"raw": raw[:500]}
            return e.code, j
        except Exception as exc:
            last = exc
            time.sleep(min(8, attempt * 1.5))
    raise RuntimeError(f"api {method} {path} failed: {last}")


def wait_idle(sec: int = 90) -> bool:
    t0 = time.time()
    while time.time() - t0 < sec:
        try:
            code, st = api("GET", "/api/status", timeout=15)
            if code == 200 and not st.get("running"):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def stop_job() -> dict:
    try:
        code, resp = api("POST", "/api/stop", {}, timeout=30)
        return {"code": code, "resp": resp}
    except Exception as e:
        return {"error": str(e)}


def put_config(cell: dict) -> None:
    body = {
        "register_mode": cell["register_mode"],
        "proxy_mode": cell["proxy_mode"],
        "email_provider": cell["email_provider"],
        "workers": WORKERS,
        "thread_count": WORKERS,
        "register_count": COUNT,
        "email_preflight_on_start": True,
        "email_preflight_limit": PREHEAT,
        "email_preflight_warm_ahead": PREHEAT,
        "email_preflight_continuous": False,
        "proxy_no_direct_fallback": True,
        "browser_silent": True,
        "browser_start_minimized": True,
        "enable_nsfw": True,
        "cpa_export_enabled": True,
        "sub2api_auto_add": True,
        "grok2api_auto_add_remote": True,
        "post_success_async": True,
        "post_success_workers": 2,
    }
    code, resp = api("PUT", "/api/config", body, timeout=60)
    if code not in (200, 201):
        raise RuntimeError(f"put config failed {code} {resp}")


def pool_snap() -> dict:
    try:
        code, integ = api("GET", "/api/integration", timeout=20)
        if code != 200:
            return {"ok": False, "code": code}
        g2a = integ.get("g2a") or {}
        s2 = integ.get("sub2api") or {}
        return {
            "ok": True,
            "g2a": int(g2a.get("account_count") or 0),
            "sub2": int(s2.get("account_count") or 0),
            "g2a_ok": bool(g2a.get("ok")),
            "sub2_ok": bool(s2.get("ok")),
            "has_admin_email": bool(s2.get("has_admin_email")),
            "has_admin_password": bool(s2.get("has_admin_password")),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def snapshot_logs(n: int = 800) -> str:
    try:
        code, data = api("GET", f"/api/logs/snapshot?n={n}", timeout=30)
        if code != 200:
            return f"<log fetch fail code={code}>"
        if isinstance(data, dict):
            lines = data.get("lines") or data.get("logs") or data.get("text")
            if isinstance(lines, list):
                return "\n".join(str(x) for x in lines)
            if isinstance(lines, str):
                return lines
            return json.dumps(data, ensure_ascii=False)[:200000]
        return str(data)
    except Exception as e:
        return f"<log fetch fail {e}>"


def classify(logs: str, st: dict) -> str:
    t = logs or ""
    s = int(st.get("success") or 0)
    f = int(st.get("fail") or 0)
    p = int(st.get("pending_sso") or 0)
    ap = int(st.get("awaiting_pool") or st.get("pending_pool") or 0)
    if s > 0 and f == 0:
        return "success"
    if p > 0 or "pending_sso" in t.lower():
        return "pending_sso"
    if "stop" in (st.get("error") or "").lower() or "stop_requested" in t.lower():
        return "stop_requested"
    if "pool" in t.lower() and ("fail" in t.lower() or "error" in t.lower() or "入池" in t):
        if any(k in t for k in ("import fail", "入池失败", "sso-to-oauth", "add failed", "pool add fail", "remote add fail")):
            return "pool_import_fail"
    if "proxy" in t.lower() and any(k in t.lower() for k in ("fail", "timeout", "refused", "dead")):
        return "proxy_issue"
    if "socks" in t.lower() and "fail" in t.lower():
        return "proxy_issue"
    if "验证码过多" in t or "rate_limit" in t.lower():
        return "rate_limit_mailbox"
    if "early_no_new_mail" in t:
        return "early_no_new_mail"
    if "create_email" in t.lower() and "fail" in t.lower():
        return "create_email_fail"
    if f > 0:
        return "fail"
    if s == 0 and f == 0:
        return "no_progress"
    return "unknown"


def save_state(obj: dict) -> None:
    STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    BOARD.write_text(
        f"# 18r44 Matrix Board\n\n"
        f"- out: `{OUT}`\n"
        f"- updated: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- current: {obj.get('current')}\n"
        f"- done: {obj.get('done')}/{obj.get('total')}\n"
        f"- pools: g2a={obj.get('g2a')} sub2={obj.get('sub2')}\n",
        encoding="utf-8",
    )


def run_register_or_pending(cell: dict, round_i: int) -> dict:
    name = cell["name"]
    kind = cell["kind"]
    rec = {
        "cell": name,
        "round": round_i,
        "kind": kind,
        "started": datetime.now().isoformat(timespec="seconds"),
        "ok": False,
        "success": 0,
        "fail": 0,
        "pending_sso": 0,
        "awaiting_pool": 0,
        "pool_before": {},
        "pool_after": {},
        "pool_delta_g2a": 0,
        "pool_delta_sub2": 0,
        "class": "",
        "error": "",
        "elapsed_s": 0,
        "workers": WORKERS,
        "count": COUNT,
        "preheat": PREHEAT,
    }
    t0 = time.time()
    try:
        if not wait_idle(90):
            stop_job()
            wait_idle(45)
        put_config(cell)
        rec["pool_before"] = pool_snap()
        api("POST", "/api/logs/clear", {})
        if kind == "pending_sso_recovery":
            # recovery API may only take count; workers via config
            code, resp = api(
                "POST",
                "/api/start",
                {"count": COUNT, "workers": WORKERS, "job_kind": "pending_sso_recovery"},
                timeout=30,
            )
        else:
            code, resp = api(
                "POST",
                "/api/start",
                {"count": COUNT, "workers": WORKERS, "job_kind": "register"},
                timeout=30,
            )
        if code not in (200, 201):
            rec["error"] = f"start failed {code} {resp}"
            rec["class"] = "start_fail"
            return rec
        log(f"started {name} r{round_i} resp={resp}")
        last_st = {}
        while True:
            elapsed = time.time() - t0
            if elapsed > JOB_TIMEOUT:
                log(f"[timeout] {name} r{round_i} -> stop")
                stop_job()
                time.sleep(3)
                rec["error"] = "job_timeout"
                rec["class"] = "timeout"
                break
            code, st = api("GET", "/api/status", timeout=20)
            last_st = st if code == 200 else last_st
            if code == 200:
                s = int(st.get("success") or 0)
                f = int(st.get("fail") or 0)
                p = int(st.get("pending_sso") or 0)
                ap = int(st.get("awaiting_pool") or st.get("pending_pool") or 0)
                phase = st.get("phase") or ""
                if int(elapsed) % 20 < 5:
                    log(
                        f"  .. {name} r{round_i} t={int(elapsed)}s running={st.get('running')} "
                        f"s={s} f={f} p={p} ap={ap} phase={phase}"
                    )
                if not st.get("running"):
                    # wait pool drain a bit
                    drain_t0 = time.time()
                    while time.time() - drain_t0 < 45:
                        code2, st2 = api("GET", "/api/status", timeout=15)
                        if code2 == 200:
                            last_st = st2
                            ap2 = int(st2.get("awaiting_pool") or st2.get("pending_pool") or st2.get("post_success_pending") or 0)
                            if ap2 <= 0:
                                break
                        time.sleep(2)
                    rec["success"] = int(last_st.get("success") or 0)
                    rec["fail"] = int(last_st.get("fail") or 0)
                    rec["pending_sso"] = int(last_st.get("pending_sso") or 0)
                    rec["awaiting_pool"] = int(last_st.get("awaiting_pool") or 0)
                    rec["error"] = str(last_st.get("error") or "")
                    break
            time.sleep(4)

        rec["pool_after"] = pool_snap()
        if rec["pool_before"].get("ok") and rec["pool_after"].get("ok"):
            rec["pool_delta_g2a"] = int(rec["pool_after"]["g2a"]) - int(rec["pool_before"]["g2a"])
            rec["pool_delta_sub2"] = int(rec["pool_after"]["sub2"]) - int(rec["pool_before"]["sub2"])

        logs = snapshot_logs(1200)
        (OUT / f"{name}_r{round_i:02d}.log").write_text(logs, encoding="utf-8")
        rec["class"] = classify(logs, last_st or {})
        # success criteria: at least 1 success OR pending_sso progress; no pool_import_fail
        if rec["class"] == "pool_import_fail":
            rec["ok"] = False
        elif rec["success"] > 0:
            # if success but pool didn't grow and auto-add on — flag for review but not auto-fail if pending already in pool
            rec["ok"] = True
            if rec["success"] > 0 and rec["pool_delta_g2a"] <= 0 and rec["pool_delta_sub2"] <= 0:
                # may already exist / dual-write lag — mark soft
                if "already" in logs.lower() or "exists" in logs.lower() or "duplicate" in logs.lower():
                    rec["class"] = "success_dup_or_exists"
                else:
                    rec["class"] = "success_pool_delta_zero"
                    # still ok if post_success logs show import ok
                    if any(k in logs for k in ("入池成功", "import ok", "added to pool", "sso-to-oauth ok", "remote add ok", "G2A", "Sub2")):
                        rec["ok"] = True
                    else:
                        # keep ok True for registration success; pool issue tracked separately
                        rec["ok"] = True
                        rec["pool_warning"] = True
        elif rec["pending_sso"] > 0:
            rec["ok"] = True  # mailbox burned intentionally
            rec["class"] = "pending_sso"
        elif rec["class"] == "stop_requested":
            rec["ok"] = False
        else:
            rec["ok"] = False
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["class"] = "runner_exception"
        (OUT / f"{name}_r{round_i:02d}.exc").write_text(traceback.format_exc(), encoding="utf-8")
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["finished"] = datetime.now().isoformat(timespec="seconds")
    with SUMMARY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(
        f"[{name}] r{round_i}/{ROUNDS} ok={rec['ok']} class={rec['class']} "
        f"s={rec['success']} f={rec['fail']} p={rec['pending_sso']} "
        f"dg2a={rec['pool_delta_g2a']} dsub2={rec['pool_delta_sub2']} t={rec['elapsed_s']}s"
    )
    return rec


def run_stop_test(cell: dict, round_i: int) -> dict:
    name = cell["name"]
    rec = {
        "cell": name,
        "round": round_i,
        "kind": "stop_test",
        "started": datetime.now().isoformat(timespec="seconds"),
        "ok": False,
        "class": "",
        "error": "",
        "elapsed_s": 0,
    }
    t0 = time.time()
    try:
        if not wait_idle(60):
            stop_job()
            wait_idle(30)
        put_config(cell)
        api("POST", "/api/logs/clear", {})
        code, resp = api(
            "POST",
            "/api/start",
            {"count": COUNT, "workers": WORKERS, "job_kind": "register"},
            timeout=30,
        )
        if code not in (200, 201):
            rec["error"] = f"start failed {code} {resp}"
            rec["class"] = "start_fail"
            return rec
        # let workers spin up
        time.sleep(12)
        code_s, st_before = api("GET", "/api/status")
        stop_resp = stop_job()
        time.sleep(5)
        idle = wait_idle(60)
        code2, st_after = api("GET", "/api/status")
        # 8092 still up?
        alive = False
        try:
            c3, _ = api("GET", "/api/integration", timeout=10)
            alive = c3 == 200
        except Exception:
            alive = False
        rec["stop_resp"] = stop_resp
        rec["running_before"] = bool((st_before or {}).get("running")) if code_s == 200 else None
        rec["running_after"] = bool((st_after or {}).get("running")) if code2 == 200 else None
        rec["idle_ok"] = idle
        rec["panel_alive"] = alive
        rec["ok"] = bool(idle and alive and rec["running_after"] is False)
        rec["class"] = "stop_ok" if rec["ok"] else "stop_fail"
        logs = snapshot_logs(400)
        (OUT / f"{name}_r{round_i:02d}.log").write_text(logs, encoding="utf-8")
        log(f"[stop_test] r{round_i} ok={rec['ok']} running_after={rec['running_after']} alive={alive}")
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["class"] = "runner_exception"
        (OUT / f"{name}_r{round_i:02d}.exc").write_text(traceback.format_exc(), encoding="utf-8")
    rec["elapsed_s"] = round(time.time() - t0, 1)
    rec["finished"] = datetime.now().isoformat(timespec="seconds")
    with SUMMARY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def write_report(results: list) -> None:
    lines = [
        f"# Matrix 18r44 Silent Stable Report",
        f"",
        f"- generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- workers={WORKERS} preheat={PREHEAT} count={COUNT} rounds={ROUNDS}",
        f"- proxy: socks5_list only; silent browser; no console window (pythonw parent)",
        f"",
        f"## Results",
        f"",
        f"| cell | r | ok | class | s | f | p | dg2a | dsub2 | t |",
        f"|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('cell')} | {r.get('round')} | {r.get('ok')} | {r.get('class')} | "
            f"{r.get('success',0)} | {r.get('fail',0)} | {r.get('pending_sso',0)} | "
            f"{r.get('pool_delta_g2a',0)} | {r.get('pool_delta_sub2',0)} | {r.get('elapsed_s',0)} |"
        )
    ok_n = sum(1 for x in results if x.get("ok"))
    lines += [
        f"",
        f"## Summary",
        f"- total={len(results)} ok={ok_n} fail={len(results)-ok_n}",
        f"",
    ]
    # issues
    issues = [x for x in results if not x.get("ok") or x.get("pool_warning") or x.get("class") in ("pool_import_fail", "success_pool_delta_zero")]
    lines.append("## Issues / pool notes")
    if not issues:
        lines.append("- none")
    else:
        for x in issues:
            lines.append(
                f"- {x.get('cell')} r{x.get('round')}: class={x.get('class')} "
                f"err={str(x.get('error') or '')[:120]} pool_warn={x.get('pool_warning')}"
            )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    log(f"OUT={OUT}")
    log(f"params workers={WORKERS} preheat={PREHEAT} count={COUNT} rounds={ROUNDS} cells={len(CELLS)}")
    try:
        code, st = api("GET", "/api/status")
        log(f"8092 status code={code} running={st.get('running')} phase={st.get('phase')}")
        if st.get("running"):
            log("stopping leftover job before matrix")
            stop_job()
            wait_idle(60)
    except Exception as e:
        log(f"8092 not ready: {e}")
        return 1

    base_pool = pool_snap()
    log(f"pool base {base_pool}")
    total = len(CELLS) * ROUNDS
    results = []
    done = 0
    save_state({"current": "starting", "done": 0, "total": total, "g2a": base_pool.get("g2a"), "sub2": base_pool.get("sub2"), "out": str(OUT)})

    already = completed_rounds(SUM)
    if already:
        log(f"resume skip already-done cells: {sorted(already)}")
    for cell in CELLS:
        for r in range(1, ROUNDS + 1):
            if (cell["name"], r) in already:
                log(f"SKIP already done {cell['name']} r{r}")
                done += 1
                continue
            save_state(
                {
                    "current": f"{cell['name']} r{r}",
                    "done": done,
                    "total": total,
                    "g2a": (pool_snap() or {}).get("g2a"),
                    "sub2": (pool_snap() or {}).get("sub2"),
                    "out": str(OUT),
                }
            )
            if cell["kind"] == "stop_test":
                rec = run_stop_test(cell, r)
            else:
                rec = run_register_or_pending(cell, r)
                if rec.get("class") in ("stop_requested", "empty_log", "runner_exception", "start_fail", "timeout"):
                    log(f"[retry] {cell['name']} r{r} class={rec.get('class')}")
                    stop_job()
                    wait_idle(45)
                    time.sleep(3)
                    rec2 = run_register_or_pending(cell, r)
                    rec2["retried_from"] = rec.get("class")
                    rec = rec2
            results.append(rec)
            done += 1
            write_report(results)
            time.sleep(2)

    final_pool = pool_snap()
    write_report(results)
    ok_n = sum(1 for x in results if x.get("ok"))
    log(f"DONE total={len(results)} ok={ok_n} pool_final={final_pool}")
    save_state(
        {
            "current": "done",
            "done": done,
            "total": total,
            "ok": ok_n,
            "g2a": final_pool.get("g2a"),
            "sub2": final_pool.get("sub2"),
            "out": str(OUT),
            "finished": datetime.now().isoformat(timespec="seconds"),
        }
    )
    (OUT / "DONE.txt").write_text(
        f"ok={ok_n} total={len(results)}\nbase={base_pool}\nfinal={final_pool}\n",
        encoding="utf-8",
    )
    return 0 if ok_n == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
