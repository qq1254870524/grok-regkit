# -*- coding: utf-8 -*-
"""pending SSO full-run monitor: pools + CPA + stop. No secrets printed."""
from __future__ import annotations
import json, re, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / f"pending_sso_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "monitor.log"
BASE = "http://127.0.0.1:8092"
WORKERS = 2
COUNT = 8  # solid batch; multi-round until stop test
ROUNDS = 2
STOP_TEST = True
POLL = 8

FAIL_PAT = re.compile(
    r"(?<![非])入池失败|(?<![_\w])pool[_\s-]?fail(?!\s*=\s*0)|(?<![_\w])import[_\s-]?fail|"
    r"写入号池.*失败|号池远端.*失败|"
    r"CPA\s*导出失败|mint failed|device code network retries exhausted|(?<![非])丢号|"
    r"Sub2API\s*OAuth\s*入池失败|G2A\s*入池失败|"
    r"post_process.*失败|mirror_v3.*失败)",
    re.I,
)
OK_POOL_PAT = re.compile(
    r"(已写入号池远端\[primary\]|已写入号池远端\[mirror_v3\]|sub2api.*success|Sub2API.*成功|CPA.*导出成功|cpa.*written|auth\.json)",
    re.I,
)


def log(m: str) -> None:
    line = time.strftime("%H:%M:%S ") + str(m)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, body=None, timeout=30):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(raw) if raw.strip() else {}
        except Exception:
            j = {"raw": raw[:200]}
        return e.code, j
    except Exception as e:
        return 0, {"error": str(e)}


def pool_snap():
    code, integ = api("GET", "/api/integration", timeout=20)
    if code != 200:
        return {"ok": False, "g2a": None, "sub2": None, "err": str(integ)[:120]}
    g2a = integ.get("g2a") or {}
    s2 = integ.get("sub2api") or {}
    return {
        "ok": bool(integ.get("ok")),
        "g2a": int(g2a.get("account_count") or 0),
        "sub2": int(s2.get("account_count") or 0),
        "g2a_ok": bool(g2a.get("ok")),
        "sub2_ok": bool(s2.get("ok")),
        "has_admin_email": bool((integ.get("config") or {}).get("has_sub2api_admin_email")),
        "has_admin_password": bool((integ.get("config") or {}).get("has_sub2api_admin_password")),
    }


def cpa_count():
    d = ROOT / "cpa_auths"
    if not d.is_dir():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.suffix.lower() in {".json", ".txt"})


def apply_cfg():
    body = {
        "proxy_mode": "socks5_list",
        "register_mode": "hybrid",
        "workers": WORKERS,
        "thread_count": WORKERS,
        "register_count": COUNT,
        "browser_silent": True,
        "email_preflight_limit": 4,
        "email_preflight_warm_ahead": 4,
        "grok2api_auto_add_remote": True,
        "grok2api_auto_add_local": True,
        "sub2api_auto_add": True,
        "cpa_export_enabled": True,
        "cpa_auto_add": True,
        "post_success_workers": 4,
        "browser_headless": False,
    }
    code, resp = api("PUT", "/api/config", body, timeout=60)
    log(f"PUT /api/config code={code} ok={resp.get('ok') if isinstance(resp, dict) else resp}")
    return code == 200


def scan_logs(n=80):
    code, data = api("GET", f"/api/logs/snapshot?n={n}", timeout=30)
    lines = []
    if isinstance(data, dict):
        lines = data.get("lines") or data.get("logs") or data.get("items") or []
        if isinstance(data.get("text"), str):
            lines = data["text"].splitlines()
    if not isinstance(lines, list):
        lines = []
    text_lines = [str(x) for x in lines]
    fails = [ln for ln in text_lines if FAIL_PAT.search(ln)]
    oks = [ln for ln in text_lines if OK_POOL_PAT.search(ln)]
    return text_lines, fails, oks


def wait_job(timeout=1200):
    t0 = time.time()
    last = {}
    fail_hits = []
    ok_hits = []
    while time.time() - t0 < timeout:
        code, st = api("GET", "/api/status", timeout=15)
        if code != 200:
            log(f"status code={code} {st}")
            time.sleep(POLL)
            continue
        last = st
        running = bool(st.get("running"))
        s = int(st.get("success") or 0)
        f = int(st.get("fail") or 0)
        p = int(st.get("pending_sso") or 0)
        ap = int(st.get("awaiting_pool") or 0)
        phase = st.get("phase") or ""
        ev = str(st.get("last_event") or "")[:140]
        log(f".. t={int(time.time()-t0)}s run={running} s={s} f={f} p={p} ap={ap} phase={phase} | {ev}")
        _, fails, oks = scan_logs(60)
        for ln in fails[-5:]:
            if ln not in fail_hits:
                fail_hits.append(ln)
                log(f"[FAILHIT] {ln[:220]}")
        for ln in oks[-5:]:
            if ln not in ok_hits:
                ok_hits.append(ln)
                log(f"[POOL/CPA] {ln[:220]}")
        if not running and st.get("finished_at"):
            break
        if not running and float(st.get("started_at") or 0) and (time.time() - t0) > 15:
            # finished without finished_at sometimes
            if phase in ("finished", "idle", "") or st.get("jobs_finished"):
                # wait one more poll to settle
                time.sleep(3)
                code2, st2 = api("GET", "/api/status", timeout=15)
                if code2 == 200 and not st2.get("running"):
                    last = st2
                    break
        time.sleep(POLL)
    return last, fail_hits, ok_hits


def stop_test():
    api("POST", "/api/logs/clear", {})
    # start a register job then stop quickly
    code, resp = api("POST", "/api/start", {"count": COUNT, "workers": WORKERS, "job_kind": "register"}, timeout=30)
    log(f"stop_test start code={code} resp_ok={resp.get('ok') if isinstance(resp, dict) else resp}")
    time.sleep(6)
    code_s, st_b = api("GET", "/api/status")
    running_before = bool(st_b.get("running")) if code_s == 200 else False
    code2, resp2 = api("POST", "/api/stop", {}, timeout=30)
    time.sleep(8)
    code3, st_a = api("GET", "/api/status")
    running_after = bool(st_a.get("running")) if code3 == 200 else True
    # panel alive
    code4, _ = api("GET", "/api/integration", timeout=10)
    rec = {
        "start_code": code,
        "stop_code": code2,
        "stop_resp": resp2,
        "running_before": running_before,
        "running_after": running_after,
        "panel_alive": code4 == 200,
        "ok": (code2 == 200) and (not running_after) and (code4 == 200),
    }
    log(f"stop_test result ok={rec['ok']} before={running_before} after={running_after} panel={rec['panel_alive']} detail={str(resp2)[:200]}")
    return rec


def main():
    (OUT / "meta.json").write_text(json.dumps({
        "workers": WORKERS, "count": COUNT, "rounds": ROUNDS,
        "started": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"OUT={OUT}")
    if not apply_cfg():
        log("CONFIG_FAIL"); return 2
    base_pool = pool_snap()
    base_cpa = cpa_count()
    log(f"BASE pool={base_pool} cpa_files={base_cpa}")
    summary = []
    for r in range(1, ROUNDS + 1):
        log(f"==== ROUND {r}/{ROUNDS} pending_sso_recovery ====")
        api("POST", "/api/logs/clear", {})
        before = pool_snap()
        cpa0 = cpa_count()
        code, resp = api(
            "POST",
            "/api/start",
            {"count": COUNT, "workers": WORKERS, "job_kind": "pending_sso_recovery"},
            timeout=30,
        )
        log(f"start code={code} resp={str(resp)[:200]}")
        if code != 200 or (isinstance(resp, dict) and resp.get("ok") is False):
            summary.append({"round": r, "ok": False, "error": f"start_failed {code} {resp}"})
            continue
        last, fail_hits, ok_hits = wait_job(timeout=1500)
        after = pool_snap()
        cpa1 = cpa_count()
        s = int(last.get("success") or 0)
        f = int(last.get("fail") or 0)
        p = int(last.get("pending_sso") or 0)
        ap = int(last.get("awaiting_pool") or 0)
        dg2a = (after.get("g2a") or 0) - (before.get("g2a") or 0) if after.get("g2a") is not None and before.get("g2a") is not None else None
        dsub2 = (after.get("sub2") or 0) - (before.get("sub2") or 0) if after.get("sub2") is not None and before.get("sub2") is not None else None
        dcpa = cpa1 - cpa0
        # classify
        pool_ok = True
        if s > 0:
            if dg2a is not None and dg2a < s:
                pool_ok = False
            if dsub2 is not None and dsub2 < s:
                pool_ok = False
        cls = "success" if s > 0 and f == 0 and pool_ok else (
            "success_partial" if s > 0 and pool_ok else (
                "pool_gap" if s > 0 and not pool_ok else (
                    "fail" if f > 0 and s == 0 else "empty"
                )
            )
        )
        rec = {
            "round": r,
            "ok": cls in ("success", "success_partial"),
            "class": cls,
            "success": s,
            "fail": f,
            "pending_sso": p,
            "awaiting_pool": ap,
            "pool_before": before,
            "pool_after": after,
            "delta_g2a": dg2a,
            "delta_sub2": dsub2,
            "delta_cpa_files": dcpa,
            "fail_hits": len(fail_hits),
            "ok_hits": len(ok_hits),
            "fail_samples": fail_hits[-8:],
            "ok_samples": [x[:160] for x in ok_hits[-8:]],
            "last_event": str(last.get("last_event") or "")[:200],
        }
        summary.append(rec)
        with (OUT / "summary.jsonl").open("a", encoding="utf-8") as fsum:
            fsum.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"ROUND{r} class={cls} s={s} f={f} dg2a={dg2a} dsub2={dsub2} dcpa={dcpa} fail_hits={len(fail_hits)}")
        time.sleep(3)

    stop_rec = None
    if STOP_TEST:
        log("==== STOP TEST ====")
        stop_rec = stop_test()
        with (OUT / "stop_test.json").open("w", encoding="utf-8") as f:
            json.dump(stop_rec, f, ensure_ascii=False, indent=2)

    final = pool_snap()
    final_cpa = cpa_count()
    report = {
        "base_pool": base_pool,
        "final_pool": final,
        "base_cpa": base_cpa,
        "final_cpa": final_cpa,
        "rounds": summary,
        "stop": stop_rec,
        "total_success": sum(int(x.get("success") or 0) for x in summary),
        "total_fail": sum(int(x.get("fail") or 0) for x in summary),
        "any_pool_gap": any(x.get("class") == "pool_gap" for x in summary),
        "finished": datetime.now().isoformat(timespec="seconds"),
    }
    (OUT / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# Pending SSO Full Run Report",
        f"- out: `{OUT.name}`",
        f"- workers={WORKERS} count={COUNT} rounds={ROUNDS}",
        f"- pool base g2a={base_pool.get('g2a')} sub2={base_pool.get('sub2')} -> final g2a={final.get('g2a')} sub2={final.get('sub2')}",
        f"- cpa files {base_cpa} -> {final_cpa}",
        "",
        "| r | class | s | f | dg2a | dsub2 | dcpa | fail_hits |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for x in summary:
        md.append(
            f"| {x.get('round')} | {x.get('class')} | {x.get('success')} | {x.get('fail')} | "
            f"{x.get('delta_g2a')} | {x.get('delta_sub2')} | {x.get('delta_cpa_files')} | {x.get('fail_hits')} |"
        )
    if stop_rec:
        md.append("")
        md.append(f"## Stop test: ok={stop_rec.get('ok')} before={stop_rec.get('running_before')} after={stop_rec.get('running_after')}")
    (OUT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT / "DONE.txt").write_text(json.dumps({"ok": not report["any_pool_gap"], "total_success": report["total_success"]}, ensure_ascii=False), encoding="utf-8")
    log(f"DONE report={OUT/'REPORT.md'} any_pool_gap={report['any_pool_gap']} total_s={report['total_success']}")
    return 0 if not report["any_pool_gap"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
