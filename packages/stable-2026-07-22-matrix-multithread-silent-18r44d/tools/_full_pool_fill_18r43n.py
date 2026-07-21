# -*- coding: utf-8 -*-
import json, sys, time, traceback, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
LOG = ROOT / "tools" / "_full_pool_fill_18r43n.log"

def log(m):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + str(m)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_cfg():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg = dict(cfg)
    cfg["sub2api_verify_after_add"] = False
    cfg["sub2api_require_verify_success"] = False
    return cfg

def collect_session_sso_map():
    from grok_register_ttk import _is_importable_session_sso
    best = {}
    files = sorted(ROOT.glob("accounts*.txt"), key=lambda p: p.stat().st_mtime)
    for path in files:
        try:
            mtime = path.stat().st_mtime
            for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split("----")
                if len(parts) < 2:
                    continue
                email = parts[0].strip().lower()
                if "@" not in email:
                    continue
                tok = ""
                for part in reversed(parts):
                    cand = part.strip()
                    if _is_importable_session_sso(cand):
                        tok = cand
                        break
                if not tok:
                    continue
                prev = best.get(email)
                if prev is None or mtime >= prev[1]:
                    best[email] = (tok, mtime, path.name)
        except Exception as exc:
            log("scan_err %s %s" % (path.name, exc))
    try:
        raw = json.loads((ROOT / "token.json").read_text(encoding="utf-8"))
        pool = str((load_cfg().get("grok2api_pool_name") or "ssoBasic"))
        for e in (raw.get(pool) or []):
            if not isinstance(e, dict):
                continue
            email = str(e.get("note") or e.get("email") or "").strip().lower()
            tok = str(e.get("token") or e.get("sso") or "").strip()
            if not email or "@" not in email:
                continue
            if not _is_importable_session_sso(tok):
                continue
            if email not in best:
                best[email] = (tok, time.time(), "token.json")
    except Exception as exc:
        log("token_json_scan_err %s" % exc)
    return best

def fetch_g2a_remote(cfg):
    base = str(cfg.get("grok2api_remote_base") or "http://127.0.0.1:8010").rstrip("/")
    key = str(cfg.get("grok2api_remote_app_key") or "")
    url = base + "/admin/api/tokens?" + urllib.parse.urlencode({"app_key": key})
    with urllib.request.urlopen(url, timeout=60) as resp:
        remote = json.loads(resp.read().decode())
    tokens = remote.get("tokens") or []
    vals = set()
    notes = set()
    for t in tokens:
        if not isinstance(t, dict):
            continue
        v = str(t.get("token") or t.get("sso") or t.get("value") or "").strip()
        if v:
            vals.add(v)
        n = str(t.get("note") or t.get("email") or "").strip().lower()
        if n:
            notes.add(n)
    return len(tokens), vals, notes

def fetch_sub2_emails(cfg):
    import sub2api_client as s2
    client = s2.get_client(cfg, force_new=True)
    emails = set()
    accounts = client.list_accounts()
    if isinstance(accounts, dict):
        accounts = accounts.get("data") or accounts.get("accounts") or accounts.get("items") or []
    for a in accounts or []:
        if not isinstance(a, dict):
            continue
        em = str(a.get("email") or a.get("username") or a.get("name") or "").strip().lower()
        if em:
            emails.add(em)
    return emails, len(accounts or [])

def clean_dead_pending():
    from grok_register_ttk import _is_importable_session_sso
    path = ROOT / "sub2api_import_pending.jsonl"
    if not path.is_file():
        return {"kept": 0, "archived": 0}
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    keep, dead = [], []
    for ln in lines:
        try:
            o = json.loads(ln)
        except Exception:
            dead.append(ln)
            continue
        sso = str(o.get("sso") or o.get("token") or "")
        if _is_importable_session_sso(sso):
            keep.append(ln)
        else:
            dead.append(ln)
    arch_name = ""
    if dead:
        arch = ROOT / ("sub2api_import_pending_dead_mailtoken_%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))
        arch.write_text("\n".join(dead) + "\n", encoding="utf-8")
        arch_name = arch.name
    path.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
    return {"kept": len(keep), "archived": len(dead), "archive": arch_name}

def main():
    LOG.write_text("", encoding="utf-8")
    log("BEGIN full pool fill 18r43n")
    cfg = load_cfg()
    from grok_register_ttk import load_config, add_token_to_grok2api_remote_pool, add_token_to_grok2api_local_pool
    import sub2api_client as s2
    load_config()
    cfg = s2._resolve_runtime_config(cfg)
    log("admin_email_len=%s pass_len=%s" % (len(str(cfg.get("sub2api_admin_email") or "")), len(str(cfg.get("sub2api_admin_password") or ""))))
    sso_map = collect_session_sso_map()
    log("local_session_sso_emails=%s" % len(sso_map))
    g2a_n, g2a_vals, g2a_notes = fetch_g2a_remote(cfg)
    log("BEFORE g2a_remote=%s token_vals=%s notes=%s" % (g2a_n, len(g2a_vals), len(g2a_notes)))
    try:
        sub2_emails, sub2_n = fetch_sub2_emails(cfg)
        log("BEFORE sub2_accounts=%s emails=%s" % (sub2_n, len(sub2_emails)))
    except Exception as exc:
        log("sub2_list_err %s" % exc)
        sub2_emails, sub2_n = set(), 0

    g_added = g_skip = g_fail = 0
    for email, (tok, _mt, src) in sso_map.items():
        if tok in g2a_vals or email in g2a_notes:
            g_skip += 1
            continue
        try:
            ok = add_token_to_grok2api_remote_pool(tok, email=email, log_callback=None)
            if ok:
                g_added += 1
                g2a_vals.add(tok)
                g2a_notes.add(email)
                try:
                    add_token_to_grok2api_local_pool(tok, email=email, log_callback=None)
                except Exception:
                    pass
            else:
                g_fail += 1
        except Exception as exc:
            g_fail += 1
            if g_fail <= 12:
                log("g2a_fail email=%s err=%s" % (email, exc))
        if g_added and g_added % 50 == 0:
            log("g2a progress added=%s fail=%s skip=%s" % (g_added, g_fail, g_skip))
        time.sleep(0.02)
    log("G2A_FILL added=%s fail=%s skip=%s" % (g_added, g_fail, g_skip))

    # Sub2 via backfill helper first (CPA + SSO)
    try:
        bf = s2.backfill_missing_sub2api_from_cpa_and_sso(config=cfg, log_callback=log, limit=0, prefer_cpa=True)
        log("SUB2_BACKFILL %s" % json.dumps({k: v for k, v in (bf or {}).items() if k != "errors"}, ensure_ascii=False)[:900])
        if bf and bf.get("errors"):
            log("SUB2_BACKFILL_ERRS %s" % json.dumps(bf.get("errors")[:15], ensure_ascii=False))
    except Exception as exc:
        log("SUB2_BACKFILL_ERR %s" % exc)
        traceback.print_exc()

    # CPA dir import if available
    try:
        import inspect
        fn = s2.import_cpa_dir_to_sub2api
        sig = str(inspect.signature(fn))
        log("import_cpa_dir_sig %s" % sig)
        if "directory" in sig or "dir" in sig:
            cpa_sum = fn(config=cfg, log_callback=log, directory=str(ROOT / "cpa_auths"))
        else:
            cpa_sum = fn(config=cfg, log_callback=log)
        log("CPA_IMPORT %s" % repr(cpa_sum)[:800])
    except Exception as exc:
        log("CPA_IMPORT_ERR %s" % exc)

    try:
        pend = s2.process_sub2api_pending_file(config=cfg, log_callback=log, limit=0)
        log("PENDING %s" % json.dumps(pend, ensure_ascii=False)[:500])
    except Exception as exc:
        log("PENDING_ERR %s" % exc)
    dead = clean_dead_pending()
    log("DEAD_PENDING %s" % dead)

    try:
        g2a_n2, _, _ = fetch_g2a_remote(cfg)
    except Exception as exc:
        g2a_n2 = "err:%s" % exc
    try:
        sub2_emails2, sub2_n2 = fetch_sub2_emails(cfg)
    except Exception as exc:
        sub2_n2, sub2_emails2 = "err:%s" % exc, set()
    try:
        integ = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/integration", timeout=15).read().decode())
        s2c = integ.get("sub2api") or {}
        g2 = integ.get("g2a") or {}
        log("INTEGRATION sub2=%s g2a=%s" % (s2c.get("account_count"), g2.get("account_count")))
    except Exception as exc:
        log("INTEGRATION_ERR %s" % exc)
    log("FINAL g2a_remote=%s sub2=%s sub2_emails=%s" % (g2a_n2, sub2_n2, len(sub2_emails2) if isinstance(sub2_emails2, set) else sub2_emails2))
    log("END")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log("FATAL " + traceback.format_exc())
        raise
