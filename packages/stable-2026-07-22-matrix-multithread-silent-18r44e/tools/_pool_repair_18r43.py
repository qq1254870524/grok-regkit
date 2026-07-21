# -*- coding: utf-8 -*-
import json, sys, time, traceback
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
LOG = ROOT / "matrix_runs" / "_POOL_REPAIR_18r43.log"

def log(m):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + str(m)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    LOG.write_text("", encoding="utf-8")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg = dict(cfg)
    cfg["sub2api_verify_after_add"] = False
    cfg["sub2api_require_verify_success"] = False
    cfg["sub2api_backfill_gap_sec"] = 0.8
    cfg["sub2api_backfill_fail_gap_sec"] = 2.0
    from sub2api_client import (
        process_sub2api_pending_file,
        backfill_missing_sub2api_from_cpa_and_sso,
        log_pool_counts,
        get_client,
    )
    from grok_register_ttk import load_config, add_token_to_grok2api_remote_pool, add_token_to_grok2api_local_pool
    load_config()

    log("=== BEFORE ===")
    log_pool_counts(config=cfg, log_callback=log)

    log("=== PROCESS PENDING ===")
    try:
        pend = process_sub2api_pending_file(config=cfg, log_callback=log, limit=0)
        log("PENDING_SUMMARY " + json.dumps({k:v for k,v in pend.items() if k!='errors'}, ensure_ascii=False))
    except Exception as e:
        log("PENDING_ERR " + repr(e))
        traceback.print_exc()

    log("=== BACKFILL SUB2 FROM CPA/SSO ===")
    try:
        summary = backfill_missing_sub2api_from_cpa_and_sso(
            config=cfg, log_callback=log, limit=0, prefer_cpa=True
        )
        log("BACKFILL_SUMMARY " + json.dumps({k:v for k,v in summary.items() if k!='errors'}, ensure_ascii=False))
        if summary.get("errors"):
            log("BACKFILL_ERRS " + json.dumps(summary["errors"][:20], ensure_ascii=False))
    except Exception as e:
        log("BACKFILL_ERR " + repr(e))
        traceback.print_exc()

    # sync local g2a tokens missing from remote
    log("=== G2A LOCAL -> REMOTE SYNC ===")
    try:
        import urllib.request, urllib.parse
        pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
        tok = json.loads((ROOT / "token.json").read_text(encoding="utf-8"))
        items = tok.get(pool) or []
        base = str(cfg.get("grok2api_remote_base") or "http://127.0.0.1:8010").rstrip("/")
        key = str(cfg.get("grok2api_remote_app_key") or "")
        url = base + "/admin/api/tokens?" + urllib.parse.urlencode({"app_key": key})
        with urllib.request.urlopen(url, timeout=20) as resp:
            remote = json.loads(resp.read().decode())
        remote_tokens = remote.get("tokens") or []
        remote_notes = set()
        remote_vals = set()
        for t in remote_tokens:
            if not isinstance(t, dict):
                continue
            n = str(t.get("note") or t.get("email") or "").strip().lower()
            if "@" in n:
                remote_notes.add(n)
            v = str(t.get("token") or t.get("sso") or t.get("value") or "").strip()
            if v:
                remote_vals.add(v)
        log(f"g2a remote={len(remote_tokens)} local={len(items)} remote_emails={len(remote_notes)}")
        added = 0
        skipped = 0
        failed = 0
        for e in items:
            if not isinstance(e, dict):
                skipped += 1
                continue
            email = str(e.get("note") or e.get("email") or "").strip()
            token = str(e.get("token") or e.get("sso") or e.get("value") or "").strip()
            if not token:
                skipped += 1
                continue
            em_l = email.lower()
            if (em_l and em_l in remote_notes) or (token in remote_vals):
                skipped += 1
                continue
            try:
                ok = add_token_to_grok2api_remote_pool(token, email=email, log_callback=None)
                if ok:
                    added += 1
                    if email:
                        remote_notes.add(email.lower())
                    remote_vals.add(token)
                else:
                    failed += 1
            except Exception as ex:
                failed += 1
                if failed <= 10:
                    log(f"g2a remote add fail email={email} err={type(ex).__name__}")
            if added and added % 50 == 0:
                log(f"g2a remote progress added={added} failed={failed} skipped={skipped}")
            time.sleep(0.05)
        log(f"G2A_REMOTE_SYNC added={added} failed={failed} skipped={skipped}")
    except Exception as e:
        log("G2A_SYNC_ERR " + repr(e))
        traceback.print_exc()

    log("=== AFTER ===")
    log_pool_counts(config=cfg, log_callback=log)
    # remote recount
    try:
        import urllib.request, urllib.parse
        base = str(cfg.get("grok2api_remote_base") or "http://127.0.0.1:8010").rstrip("/")
        key = str(cfg.get("grok2api_remote_app_key") or "")
        url = base + "/admin/api/tokens?" + urllib.parse.urlencode({"app_key": key})
        with urllib.request.urlopen(url, timeout=20) as resp:
            remote = json.loads(resp.read().decode())
        log("g2a_remote_final=" + str(len(remote.get("tokens") or [])))
        c = get_client(cfg, log_callback=None)
        tok = c.login(force=True)
        _r, p = c._request_json("GET", "/api/v1/admin/accounts?page=1&page_size=1", headers={"Authorization": f"Bearer {tok}"})
        total = None
        if isinstance(p, dict):
            total = p.get("total")
            if total is None and isinstance(p.get("data"), dict):
                total = p["data"].get("total")
        log("sub2_final=" + str(total))
    except Exception as e:
        log("final_count_err " + repr(e))
    log("DONE")

if __name__ == "__main__":
    main()
