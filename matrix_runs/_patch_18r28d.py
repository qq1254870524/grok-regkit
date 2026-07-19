# -*- coding: utf-8 -*-
"""Apply 18r28d patches: fresh Turnstile + mail_token recovery from outlook cache."""
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

ROOT = Path(r"C:\Users\zhang\grok-regkit")

# ---------- pending_sso_recovery.py ----------
p = ROOT / "pending_sso_recovery.py"
text = p.read_text(encoding="utf-8")
if "18r28d:" not in text[:1200]:
    text = text.replace(
        '"""\n18r28c:',
        '"""\n18r28d: force_fresh Turnstile on refill/auth-error/cf-stuck (no stale already-present reuse)\n'
        "18r28c:",
        1,
    )

old_ensure = '''def _ensure_signin_turnstile(
    page,
    browser,
    log: Callable[[str], None],
    stop: Optional[Callable[[], bool]] = None,
    *,
    reason: str = "pre-submit",
    timeout: float = 75.0,
) -> dict:
    """Solve Cloudflare Turnstile on sign-in and inject token into the login form.

    This is mandatory for many xAI sign-in sessions; blind login clicks loop forever
    when CF is pending and no token is attached.
    """
    stop = stop or (lambda: False)
    out: dict[str, Any] = {"ok": False, "reason": reason, "token_len": 0, "method": ""}
    if page is None:
        out["detail"] = "no_page"
        return out
    if stop():
        out["detail"] = "stopped"
        return out

    probe0 = _probe_signin_turnstile(page)
    log(f"[pending-sso] turnstile probe before solve reason={reason} {probe0}")
    try:
        if int(probe0.get("tokLen") or 0) >= 80:
            out.update({"ok": True, "token_len": int(probe0.get("tokLen") or 0), "method": "already-present"})
            log(f"[pending-sso] turnstile already present len={out['token_len']} reason={reason}")
            return out
    except Exception:
        pass
'''

new_ensure = '''def _ensure_signin_turnstile(
    page,
    browser,
    log: Callable[[str], None],
    stop: Optional[Callable[[], bool]] = None,
    *,
    reason: str = "pre-submit",
    timeout: float = 75.0,
    force_fresh: bool = False,
) -> dict:
    """Solve Cloudflare Turnstile on sign-in and inject token into the login form.

    This is mandatory for many xAI sign-in sessions; blind login clicks loop forever
    when CF is pending and no token is attached.

    force_fresh=True (18r28d): never reuse already-present token — clear and solve again.
    Use after failed submit / refill / CF stuck / generic An error occurred.
    """
    stop = stop or (lambda: False)
    out: dict[str, Any] = {"ok": False, "reason": reason, "token_len": 0, "method": "", "force_fresh": bool(force_fresh)}
    if page is None:
        out["detail"] = "no_page"
        return out
    if stop():
        out["detail"] = "stopped"
        return out

    probe0 = _probe_signin_turnstile(page)
    log(f"[pending-sso] turnstile probe before solve reason={reason} force_fresh={bool(force_fresh)} {probe0}")
    if force_fresh:
        try:
            page.run_js(
                """
try { window.__hybrid_turnstile = ''; window.__hybrid_turnstile_status = 'cleared_for_fresh'; } catch (e) {}
try {
  document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"], input[name="cf_turnstile_response"]').forEach(n => { try { n.value=''; n.dispatchEvent(new Event('input',{bubbles:true})); } catch (e) {} });
} catch (e) {}
try { if (window.turnstile && turnstile.reset) turnstile.reset(); } catch (e) {}
return true;
"""
            )
            log(f"[pending-sso] turnstile cleared for force_fresh reason={reason}")
        except Exception as clr_exc:
            log(f"[pending-sso] turnstile clear fail reason={reason}: {clr_exc}")
    else:
        try:
            if int(probe0.get("tokLen") or 0) >= 80:
                out.update({"ok": True, "token_len": int(probe0.get("tokLen") or 0), "method": "already-present"})
                log(f"[pending-sso] turnstile already present len={out['token_len']} reason={reason}")
                return out
        except Exception:
            pass
'''

if old_ensure not in text:
    raise SystemExit("pending: old_ensure block not found")
text = text.replace(old_ensure, new_ensure, 1)

# force_fresh call sites
replacements = [
    (
        'ts_r = _ensure_signin_turnstile(\n                                    page, browser, log, stop, reason="auth-error-retry", timeout=70.0\n                                )',
        'ts_r = _ensure_signin_turnstile(\n                                    page, browser, log, stop, reason="auth-error-retry", timeout=70.0, force_fresh=True\n                                )',
    ),
    (
        'ts_rf = _ensure_signin_turnstile(\n                                    page,\n                                    browser,\n                                    log,\n                                    stop,\n                                    reason=f"refill-{refill_tries}",\n                                    timeout=70.0,\n                                )',
        'ts_rf = _ensure_signin_turnstile(\n                                    page,\n                                    browser,\n                                    log,\n                                    stop,\n                                    reason=f"refill-{refill_tries}",\n                                    timeout=70.0,\n                                    force_fresh=True,\n                                )',
    ),
]
# cf-stuck path - more flexible
text2 = text
for a, b in replacements:
    if a not in text2:
        print("WARN missing block:", a[:80])
    else:
        text2 = text2.replace(a, b, 1)
        print("OK replaced", a.split("reason=")[-1][:40])

# cf-stuck: add force_fresh to reason=cf-
text2 = re.sub(
    r'(reason=f?"cf-[^"]*",\s*timeout=70\.0,)',
    r'\1 force_fresh=True,',
    text2,
)
# also pattern with reason="cf-stuck..." 
text2 = re.sub(
    r'(reason=f"cf_stuck[^"]*",\s*\n\s*timeout=70\.0,)',
    r'\1\n                                    force_fresh=True,',
    text2,
)

# Find cf turnstile ensure calls without force_fresh
for m in re.finditer(r'_ensure_signin_turnstile\([\s\S]{0,220}?\)', text2):
    block = m.group(0)
    if 'cf' in block.lower() and 'force_fresh' not in block:
        print("CF CALL without force_fresh:\n", block[:200])

p.write_text(text2, encoding="utf-8")
print("pending_sso_recovery.py patched")

# ---------- hybrid_register.py ----------
hp = ROOT / "hybrid_register.py"
ht = hp.read_text(encoding="utf-8")
if "18r28d:" not in ht[:2000]:
    ht = ht.replace(
        "18r28b: _lookup_mail_token_from_pool for forced_email re-register\n",
        "18r28d: mail_token lookup from outlook_token_cache + fix resolve_credentials misuse; rate_limit burn keeps mail_token\n"
        "18r28b: _lookup_mail_token_from_pool for forced_email re-register\n",
        1,
    )

# Fix handle_create_email_rate_limited signature
old_h = '''def handle_create_email_rate_limited(
    email: str,
    password: str,
    *,
    log: Callable[[str], None] | None = None,
    source: str = "unknown",
    evidence: str = "",
) -> dict:
    """Burn mailbox to pending_sso and return PENDING so job can switch / stats stay clear."""
    if log:
        log(
            f"[hybrid] CreateEmail RATE_LIMITED source={source} email={email} "
            f"password={password!r} evidence={evidence}"
        )
    try:
        burn_mailbox_to_pending(
            email,
            password or "",
            reason="create_email_rate_limited",
            log=log,
            mail_token=mail_token,
        )
'''
new_h = '''def handle_create_email_rate_limited(
    email: str,
    password: str,
    *,
    log: Callable[[str], None] | None = None,
    source: str = "unknown",
    evidence: str = "",
    mail_token: str = "",
) -> dict:
    """Burn mailbox to pending_sso and return PENDING so job can switch / stats stay clear."""
    if log:
        log(
            f"[hybrid] CreateEmail RATE_LIMITED source={source} email={email} "
            f"password={password!r} evidence={evidence} mail_token_len={len(str(mail_token or ''))}"
        )
    try:
        burn_mailbox_to_pending(
            email,
            password or "",
            reason="create_email_rate_limited",
            log=log,
            mail_token=mail_token,
        )
'''
if old_h not in ht:
    raise SystemExit("hybrid: handle_create_email_rate_limited block not found")
ht = ht.replace(old_h, new_h, 1)

# Pass mail_token into handle_create_email_rate_limited call sites
# Pattern: return handle_create_email_rate_limited(\n email,\n password...\n evidence=...
def add_mail_token_kw(src: str) -> str:
    out = []
    i = 0
    key = "handle_create_email_rate_limited("
    while True:
        j = src.find(key, i)
        if j < 0:
            out.append(src[i:])
            break
        out.append(src[i:j])
        # find matching close paren at call level
        k = j + len(key)
        depth = 1
        while k < len(src) and depth:
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
            k += 1
        call = src[j:k]
        if "mail_token=" not in call and "def handle_create_email_rate_limited" not in call:
            # insert before closing )
            call = call[:-1] + ",\n                    mail_token=mail_token,\n                )"
            print("patched call site at", j)
        out.append(call)
        i = k
    return "".join(out)

ht = add_mail_token_kw(ht)

# Replace entire _lookup_mail_token_from_pool function
m = re.search(r"\ndef _lookup_mail_token_from_pool\(email: str, log=None\) -> str:\n", ht)
if not m:
    raise SystemExit("lookup fn not found")
start = m.start() + 1
# find next top-level def after this
m2 = re.search(r"\ndef [a-zA-Z_]", ht[start + 10 :])
if not m2:
    raise SystemExit("next def not found")
end = start + 10 + m2.start()
old_fn = ht[start:end]
print("old lookup len", len(old_fn), "head", old_fn[:80])

new_fn = r'''def _lookup_mail_token_from_pool(email: str, log=None) -> str:
    """Find IMAP/Graph mail_token for email from pools, outlook_token_cache, config, files.

    18r28d: recover Graph tokens from outlook_token_cache.json even after burn-remove;
    do NOT call AolAccountPool.resolve_credentials(email) (needs token_blob).
    18r28b: pending re-register needs original mailbox credentials; older pending
    lines may lack the 4th b64 mail_token field, so recover from live pools.
    """
    import json as _json
    from pathlib import Path as _Path

    em = str(email or "").strip().lower()
    if not em:
        return ""
    lg = log or (lambda m: None)

    def _from_aol_account(acc) -> str:
        try:
            pw = str(getattr(acc, "password", "") or "").strip()
            totp = str(getattr(acc, "totp_secret", "") or getattr(acc, "totp", "") or "").strip()
            if pw and totp:
                return f"{pw}----{totp}"
            return pw
        except Exception:
            return ""

    def _outlook_blob_from_acc(acc) -> str:
        try:
            if isinstance(acc, dict):
                data = {
                    "email": str(acc.get("email") or acc.get("user") or em),
                    "access_token": str(acc.get("access_token") or ""),
                    "refresh_token": str(acc.get("refresh_token") or acc.get("token") or acc.get("mail_token") or ""),
                    "access_expires_at": acc.get("access_expires_at") or 0,
                    "client_id": str(acc.get("client_id") or ""),
                    "password": str(acc.get("password") or ""),
                    "totp_secret": str(acc.get("totp_secret") or acc.get("totp") or ""),
                }
            else:
                data = {
                    "email": str(getattr(acc, "email", "") or em),
                    "access_token": str(getattr(acc, "access_token", "") or ""),
                    "refresh_token": str(getattr(acc, "refresh_token", "") or ""),
                    "access_expires_at": getattr(acc, "access_expires_at", 0) or 0,
                    "client_id": str(getattr(acc, "client_id", "") or ""),
                    "password": str(getattr(acc, "password", "") or ""),
                    "totp_secret": str(getattr(acc, "totp_secret", "") or ""),
                }
            # Prefer Graph token JSON when refresh/access present.
            if data.get("refresh_token") or data.get("access_token"):
                return _json.dumps(data, ensure_ascii=False)
            if data.get("password") and data.get("totp_secret"):
                return _json.dumps(data, ensure_ascii=False)
            if data.get("password"):
                return _json.dumps(data, ensure_ascii=False)
            return ""
        except Exception:
            return ""

    def _norm_line_token(line: str):
        s = str(line or "").strip()
        if not s or s.startswith("#"):
            return None
        for sep in ("----", "|", "\t"):
            if sep in s and "@" in s.split(sep, 1)[0]:
                parts = [x.strip() for x in s.split(sep) if str(x).strip()]
                if len(parts) >= 2 and parts[0].lower() == em:
                    rest = parts[1:]
                    # If looks like email----client_id----refresh or email----refresh
                    if len(rest) >= 2 and len(rest[0]) == 36 and "-" in rest[0] and len(rest[1]) > 40:
                        return _json.dumps(
                            {"email": em, "client_id": rest[0], "refresh_token": rest[1]},
                            ensure_ascii=False,
                        )
                    if len(rest) == 1 and len(rest[0]) > 40:
                        return _json.dumps(
                            {"email": em, "refresh_token": rest[0]},
                            ensure_ascii=False,
                        )
                    if len(rest) >= 2 and em.endswith(("@outlook.com", "@hotmail.com", "@live.com", "@msn.com")):
                        data = {
                            "email": em,
                            "password": rest[0],
                            "totp_secret": rest[1].replace(" ", ""),
                        }
                        if len(rest) >= 3 and len(rest[2]) == 36:
                            data["client_id"] = rest[2]
                        return _json.dumps(data, ensure_ascii=False)
                    # AOL / generic: password----totp
                    return "----".join(rest)
        if s.lower().startswith(em + ":"):
            return s.split(":", 1)[1].strip()
        return None

    # 1) outlook_token_cache.json (survives pool burn)
    try:
        cache_paths = [
            _Path(__file__).resolve().parent / "outlook_token_cache.json",
            _Path(__file__).resolve().parent / "data" / "outlook_token_cache.json",
        ]
        try:
            import grok_register_ttk as _eng

            cfg = getattr(_eng, "config", {}) or {}
            cf = str(cfg.get("outlook_token_cache") or "").strip()
            if cf:
                cache_paths.insert(0, _Path(cf) if _Path(cf).is_absolute() else (_Path(__file__).resolve().parent / cf))
        except Exception:
            pass
        for cp in cache_paths:
            if not cp.is_file():
                continue
            try:
                blob = _json.loads(cp.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                lg(f"[hybrid] outlook_token_cache read fail {cp}: {e}")
                continue
            if not isinstance(blob, dict):
                continue
            entry = blob.get(em) or blob.get(email) or blob.get(str(email or "").strip())
            if not entry and isinstance(blob, dict):
                for k, v in blob.items():
                    if str(k).strip().lower() == em and isinstance(v, dict):
                        entry = v
                        break
            if isinstance(entry, dict) and (entry.get("refresh_token") or entry.get("access_token")):
                data = {
                    "email": em,
                    "access_token": str(entry.get("access_token") or ""),
                    "refresh_token": str(entry.get("refresh_token") or ""),
                    "access_expires_at": entry.get("access_expires_at") or 0,
                    "client_id": str(entry.get("client_id") or ""),
                }
                tok = _json.dumps(data, ensure_ascii=False)
                lg(f"[hybrid] mail_token from outlook_token_cache email={em} file={cp.name} rt_len={len(data['refresh_token'])}")
                return tok
    except Exception as exc:
        lg(f"[hybrid] outlook_token_cache lookup skip: {exc}")

    # 2) AOL pool object (iterate accounts ONLY — resolve_credentials needs token_blob)
    try:
        import aol_mail as _am
        import grok_register_ttk as engine

        pool = None
        try:
            pool = _am.get_pool(getattr(engine, "config", None), force_reload=True)
        except TypeError:
            try:
                pool = _am.get_pool(force_reload=True)
            except Exception as e:
                lg(f"[hybrid] aol get_pool: {e}")
                pool = None
        except Exception as e:
            lg(f"[hybrid] aol get_pool: {e}")
            pool = None
        if pool is not None:
            accs = getattr(pool, "accounts", None) or []
            for acc in list(accs):
                ae = str(getattr(acc, "email", "") or "").strip().lower()
                if ae == em:
                    tok = _from_aol_account(acc)
                    if tok:
                        lg(f"[hybrid] mail_token from AolAccountPool email={em}")
                        return tok
    except Exception as exc:
        lg(f"[hybrid] aol pool lookup skip: {exc}")

    # 3) Outlook live pool
    try:
        import outlook_mail as _om
        import grok_register_ttk as engine

        pool = None
        try:
            pool = _om.get_pool(getattr(engine, "config", None), force_reload=True)
        except TypeError:
            try:
                pool = _om.get_pool(force_reload=True)
            except Exception:
                pool = None
        except Exception as e:
            lg(f"[hybrid] outlook get_pool: {e}")
            pool = None
        if pool is not None:
            accs = getattr(pool, "accounts", None) or getattr(pool, "items", None) or []
            if isinstance(accs, dict):
                accs = list(accs.values())
            for acc in list(accs or []):
                if isinstance(acc, dict):
                    ae = str(acc.get("email") or acc.get("user") or "").strip().lower()
                    if ae == em:
                        tok = _outlook_blob_from_acc(acc)
                        if tok:
                            lg(f"[hybrid] mail_token from outlook dict pool email={em}")
                            return tok
                else:
                    ae = str(getattr(acc, "email", "") or "").strip().lower()
                    if ae == em:
                        tok = _outlook_blob_from_acc(acc)
                        if tok:
                            lg(f"[hybrid] mail_token from outlook pool email={em}")
                            return tok
    except Exception as exc:
        lg(f"[hybrid] outlook pool lookup skip: {exc}")

    # 4) config blobs
    try:
        import grok_register_ttk as engine

        cfg = getattr(engine, "config", {}) or {}
        for key in ("aol_accounts", "outlook_accounts", "aol_account_list", "outlook_account_list", "email_accounts"):
            blob = cfg.get(key) or ""
            lines = blob if isinstance(blob, list) else str(blob).splitlines()
            for line in lines:
                t = _norm_line_token(str(line))
                if t:
                    lg(f"[hybrid] mail_token from config.{key} email={em}")
                    return t
    except Exception as exc:
        lg(f"[hybrid] config pool lookup skip: {exc}")

    # 5) on-disk account files
    root_dir = _Path(__file__).resolve().parent
    for name in (
        "aol_accounts.txt",
        "outlook_accounts.txt",
        "accounts_aol.txt",
        "accounts_outlook.txt",
        "email_pool.txt",
    ):
        fp = root_dir / name
        if not fp.is_file():
            continue
        try:
            for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                t = _norm_line_token(line)
                if t:
                    lg(f"[hybrid] mail_token from {name} email={em}")
                    return t
        except Exception:
            pass

    lg(f"[hybrid] mail_token lookup MISS email={em}")
    return ""


'''
ht = ht[:start] + new_fn + ht[end:]
hp.write_text(ht, encoding="utf-8")
print("hybrid_register.py patched")

# syntax check
import ast
ast.parse(p.read_text(encoding="utf-8"))
ast.parse(hp.read_text(encoding="utf-8"))
print("AST OK")

# functional smoke: lookup eatonrempel
import importlib.util
spec = importlib.util.spec_from_file_location("hybrid_register", hp)
mod = importlib.util.module_from_spec(spec)
# avoid heavy import side effects - exec only the function is hard; import module
import os
os.chdir(ROOT)
logs=[]
tok = None
try:
    # light import may pull browser deps
    import hybrid_register as hr
    importlib.reload(hr)
    tok = hr._lookup_mail_token_from_pool("eatonrempel@outlook.com", log=lambda m: logs.append(m))
    print("lookup tok_len", len(tok or ""), "logs", logs[-3:])
    if tok:
        d=_json.loads(tok) if tok.strip().startswith("{") else {}
        print("has_rt", bool(d.get("refresh_token")), "rt_len", len(d.get("refresh_token") or ""))
except Exception as e:
    print("import/lookup smoke fail", e)
