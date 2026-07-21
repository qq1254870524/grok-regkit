# -*- coding: utf-8 -*-
"""Periodic G2A/Sub2/CPA pool reconcile + loss report. Never kills 8010/8080/8092/8317/8318."""
from __future__ import annotations
import json, time, traceback, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
OUT.mkdir(exist_ok=True)
LOG = OUT / "_loss_watchdog.log"
SNAP = OUT / "_pool_snapshot.jsonl"
INTERVAL = 120
BASE8092 = "http://127.0.0.1:8092"

def log(m: str):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {m}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def http_json(method, url, body=None, timeout=60):
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))

def diag_local():
    import sys
    sys.path.insert(0, str(ROOT))
    try:
        from sub2api_client import reconcile_sub2api_pools
        r = reconcile_sub2api_pools(log=lambda m: log(f"[reconcile] {m}"))
        return r if isinstance(r, dict) else {"raw": str(r)}
    except Exception as e:
        return {"error": str(e), "tb": traceback.format_exc()[-800:]}

def counts():
    out = {"ts": datetime.now().isoformat(timespec="seconds")}
    # token.json
    tj = ROOT / "token.json"
    try:
        raw = json.loads(tj.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            out["g2a_token"] = len(raw)
        elif isinstance(raw, dict):
            for k in ("tokens", "data", "items", "list"):
                if isinstance(raw.get(k), list):
                    out["g2a_token"] = len(raw[k])
                    break
            else:
                out["g2a_token"] = len(raw)
        else:
            out["g2a_token"] = 0
    except Exception as e:
        out["g2a_token_err"] = str(e)
    # cpa
    cpa = ROOT / "cpa_auths"
    out["cpa"] = len(list(cpa.glob("*.json"))) if cpa.exists() else 0
    # pending
    pend = ROOT / "accounts_registered_pending_sso.txt"
    out["pending_sso_lines"] = sum(1 for ln in pend.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()) if pend.exists() else 0
    dead = ROOT / "sub2api_import_dead.jsonl"
    out["dead_lines"] = sum(1 for ln in dead.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()) if dead.exists() else 0
    # status api
    try:
        st = http_json("GET", f"{BASE8092}/api/status", timeout=12)
        out["job"] = {
            "running": st.get("running"),
            "success": st.get("success"),
            "fail": st.get("fail"),
            "pending_sso": st.get("pending_sso"),
            "session_success": st.get("session_success"),
            "session_fail": st.get("session_fail"),
            "session_pending_sso": st.get("session_pending_sso"),
            "phase": st.get("phase"),
            "jobs": f"{st.get('jobs_started')}/{st.get('jobs_finished')}",
        }
    except Exception as e:
        out["job_err"] = str(e)
    try:
        integ = http_json("GET", f"{BASE8092}/api/integration", timeout=20)
        out["integration"] = {
            "g2a": (integ.get("g2a") or integ.get("grok2api") or {}),
            "sub2": (integ.get("sub2api") or integ.get("sub2") or {}),
        }
    except Exception as e:
        out["integration_err"] = str(e)
    return out

def main():
    log("loss_watchdog start interval=%ss" % INTERVAL)
    while True:
        try:
            c = counts()
            log(
                "snap g2a_token=%s cpa=%s pending=%s dead=%s job=%s"
                % (
                    c.get("g2a_token"),
                    c.get("cpa"),
                    c.get("pending_sso_lines"),
                    c.get("dead_lines"),
                    c.get("job"),
                )
            )
            with SNAP.open("a", encoding="utf-8") as f:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
            # reconcile when gap or idle moments
            rec = diag_local()
            log("reconcile result keys=%s summary=%s" % (list(rec.keys()) if isinstance(rec, dict) else type(rec), str(rec)[:500]))
            # also hit HTTP reconcile if available
            try:
                r2 = http_json("POST", f"{BASE8092}/api/sub2api/reconcile", {}, timeout=120)
                log("http reconcile %s" % str(r2)[:400])
            except Exception as e:
                log("http reconcile skip/fail: %s" % e)
        except Exception as e:
            log("loop error: %s" % e)
            log(traceback.format_exc()[-600:])
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
