# -*- coding: utf-8 -*-
"""Parallel Sub2 fill from accounts*.txt + token.json; G2A already filled."""
import json, sys, time, traceback, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(r"C:\Users\zhang\grok-regkit")
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
LOG = ROOT / "tools" / "_parallel_sub2_fill_18r43n.log"
WORKERS = 6

def log(m):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + str(m)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    LOG.write_text("", encoding="utf-8")
    log("BEGIN parallel sub2 fill workers=%s" % WORKERS)
    import sub2api_client as s2
    from grok_register_ttk import load_config, _is_importable_session_sso
    load_config()
    cfg = s2._resolve_runtime_config(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))
    cfg["sub2api_verify_after_add"] = False
    cfg["sub2api_require_verify_success"] = False

    # collect email->sso
    email_sso = {}
    tok = json.loads((ROOT / "token.json").read_text(encoding="utf-8")) if (ROOT / "token.json").is_file() else {}
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    for ent in (tok.get(pool) or []):
        if not isinstance(ent, dict):
            continue
        em = str(ent.get("note") or ent.get("email") or "").strip().lower()
        sso = str(ent.get("token") or ent.get("sso") or "").strip()
        if em and "@" in em and _is_importable_session_sso(sso):
            email_sso[em] = sso
    for path in sorted(ROOT.glob("accounts*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = ln.strip().split("----")
                if len(parts) < 2:
                    continue
                em = parts[0].strip().lower()
                if "@" not in em:
                    continue
                for part in reversed(parts):
                    cand = part.strip()
                    if _is_importable_session_sso(cand):
                        email_sso[em] = cand
                        break
        except Exception:
            pass
    log("source_emails=%s" % len(email_sso))

    # existing sub2 emails paginated
    client = s2.get_client(cfg, force_new=True)
    token = client.login(force=True)
    existing = set()
    page = 1
    while page < 120:
        resp, payload = client._request_json(
            "GET",
            "/api/v1/admin/accounts?page=%s&page_size=100" % page,
            headers={"Authorization": "Bearer %s" % token},
        )
        data = client._payload_data(payload) if isinstance(payload, dict) else {}
        items = []
        if isinstance(data, dict):
            items = data.get("items") or data.get("list") or []
        for a in items:
            if isinstance(a, dict):
                existing.add(str(a.get("name") or a.get("email") or "").strip().lower())
        if not items or len(items) < 100:
            break
        page += 1
    missing = [(em, email_sso[em]) for em in sorted(email_sso) if em not in existing]
    log("sub2_existing=%s missing=%s pages=%s" % (len(existing), len(missing), page))

    stats = {"ok": 0, "fail": 0}
    lock = Lock()

    def one(item):
        em, sso = item
        try:
            # each thread own client for safety
            res = s2.import_after_success_prefer_cpa(
                sso,
                email=em,
                cpa_result=None,
                config=cfg,
                log_callback=None,
            )
            ok = bool(res) if not isinstance(res, dict) else bool(res.get("ok") or res.get("success") or res.get("account_id"))
            # some helpers return None on success path with side effects - check better
            if isinstance(res, dict):
                if res.get("error") or res.get("ok") is False:
                    ok = False
                elif res.get("account_id") or res.get("ok") is True or res.get("status") in (200, "ok", "success"):
                    ok = True
            return em, ok, repr(res)[:120]
        except Exception as exc:
            return em, False, "%s:%s" % (type(exc).__name__, exc)

    # Discover correct import function signature once
    import inspect
    fn = s2.import_after_success_prefer_cpa
    log("import_fn_sig %s" % inspect.signature(fn))

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(one, it) for it in missing]
        for i, fut in enumerate(as_completed(futs), 1):
            em, ok, detail = fut.result()
            with lock:
                if ok:
                    stats["ok"] += 1
                else:
                    stats["fail"] += 1
                    if stats["fail"] <= 20:
                        log("FAIL %s %s" % (em, detail))
                if i % 20 == 0 or i == len(missing):
                    log("progress %s/%s ok=%s fail=%s" % (i, len(missing), stats["ok"], stats["fail"]))

    # final integration
    try:
        integ = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/integration", timeout=20).read().decode())
        log("FINAL sub2=%s g2a=%s" % ((integ.get("sub2api") or {}).get("account_count"), (integ.get("g2a") or {}).get("account_count")))
    except Exception as e:
        log("FINAL_ERR %s" % e)
    log("STATS %s" % stats)
    log("END")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log("FATAL " + traceback.format_exc())
        raise
