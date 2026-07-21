# 18r42d: save path normalize + refuse mail_token as SSO field
"""
18r42c: turnstile no-widget fail-fast (probe hasChallengeUi/iframe false -> short timeout; pair grok_register_ttk 18r42c);
18r42b: inputs-not-ready / chrome-error / reload-only always fail_reason=need_reregister (MT hybrid re-register);
  expand MT need_rereg heuristics for inputs not ready / chrome-error / reload-only stuck.
18r42a: pending sign-in recovery for chrome-error / reload pages (click reload or re-nav, fail-fast);
  stop spam-log of no-email-signin-btn (flag outside last_wait); treat reload-only candidates.
18r36b: skip/purge exhausted emails so burn cannot requeue dead-letter.
18r36a: pending dead-loop break — per-email attempt cap + exhausted archive + active-file dedupe.
  - timeout_no_sso / signup_unconfirmed re-register loops no longer infinite rotate+append
  - after MAX_PENDING_ATTEMPTS (default 3) move to accounts_pending_sso_exhausted.txt and remove active
  - compact_pending_sso_file keeps one best row per email (richest mail_token)
  - attempt counters in matrix_runs/pending_sso_attempts.json (survives job restart)
18r35k: MT re-register pending_sso result undoes fail -> record_pending (not hard-fail).
18r35j: pending load prefers mail_token; no-token accounts sink/archive so queue not blocked.
18r35i: MT pending path must run hybrid re-register on auth_error (was serial-only; MT only record_fail).

Pending SSO recovery helpers for grok-regkit hybrid.

18r28h: ONE login submit only (no boost second click); CF-stuck cannot skip 10s
  re-register via continue; remove long-wait sign-in re-entry; login fail NEVER
  re-login — only hybrid re-register.
18r28g: CF-stuck after first submit = inject Turnstile ONLY (no re-login click);
18r28f: login fail -> IMMEDIATE hybrid re-register (NO second login click / NO re-fill login);
  pair with grok_register_ttk.resolve_mailbox_provider so Outlook code fetch
  is not misrouted to AOL when UI email_provider=aol.
18r28e: fix sleep_with_cancel in _ensure_signin_turnstile; login fail after 1 Turnstile retry -> IMMEDIATE re-register (no more login clicks/refill);
  no-sso/sign-in stuck also fail_reason=need_reregister; outer always routes need_reregister/auth_error to hybrid.
18r28d: force_fresh Turnstile + pre-rereg mail_token from outlook_token_cache on refill/auth-error/cf-stuck (no stale already-passed short-circuit).
18r28c: reload hybrid_register before forced re-register; server hot-reload hybrid
18r28b: fill credentials WITHOUT auto-click login; one submit only after Turnstile OK; hybrid mail_token pool lookup
18r28: pending SSO sign-in MUST solve/inject Cloudflare Turnstile before login submit
and on CF stuck/re-fill; never blind re-click login while challenge pending.
18r24b: pending fail rotates account to end of accounts_registered_pending_sso.txt so count=1 matrix no longer stuck on same head row.
18r24: pending-sso sign-in prefers ?email=true deep-link; after 2 empty social-btn clicks force email form URL.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent

STATUS_SUCCESS = "success"
STATUS_FAIL = "fail"
STATUS_PENDING_SSO = "pending_sso"
STATUS_POOL_EMPTY = "pool_empty"
STATUS_STOPPED = "stopped"


# 18r36a: break infinite auth_error -> re-register -> timeout_no_sso -> burn loop
MAX_PENDING_ATTEMPTS = int(os.environ.get("PENDING_SSO_MAX_ATTEMPTS", "3") or "3")
PENDING_ATTEMPTS_PATH = ROOT / "matrix_runs" / "pending_sso_attempts.json"
PENDING_EXHAUSTED_PATH = ROOT / "accounts_pending_sso_exhausted.txt"


def _pending_attempts_load() -> dict:
    try:
        if PENDING_ATTEMPTS_PATH.is_file():
            data = json.loads(PENDING_ATTEMPTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _pending_attempts_save(data: dict) -> None:
    try:
        PENDING_ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_ATTEMPTS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(PENDING_ATTEMPTS_PATH)
    except Exception:
        pass


def bump_pending_attempt(email: str, reason: str = "", log: Callable[[str], None] | None = None) -> int:
    key = str(email or "").strip().lower()
    if not key:
        return 0
    data = _pending_attempts_load()
    item = data.get(key) if isinstance(data.get(key), dict) else {}
    n = int(item.get("n") or 0) + 1
    data[key] = {
        "n": n,
        "last_reason": str(reason or item.get("last_reason") or "")[:240],
        "updated_at": time.time(),
        "first_at": float(item.get("first_at") or time.time()),
    }
    _pending_attempts_save(data)
    if log:
        log(f"[pending-sso] attempt bump email={key} n={n}/{MAX_PENDING_ATTEMPTS} reason={reason}")
    return n


def get_pending_attempt(email: str) -> int:
    key = str(email or "").strip().lower()
    if not key:
        return 0
    data = _pending_attempts_load()
    item = data.get(key)
    if isinstance(item, dict):
        return int(item.get("n") or 0)
    return 0


def clear_pending_attempt(email: str, log: Callable[[str], None] | None = None) -> None:
    key = str(email or "").strip().lower()
    if not key:
        return
    data = _pending_attempts_load()
    if key in data:
        data.pop(key, None)
        _pending_attempts_save(data)
        if log:
            log(f"[pending-sso] attempt counter cleared email={key}")


def archive_pending_exhausted(
    email: str,
    *,
    reason: str = "exhausted",
    password: str = "",
    mail_token: str = "",
    log: Callable[[str], None] | None = None,
) -> int:
    """Move email out of active pending queue into exhausted dead-letter file."""
    import base64

    target = str(email or "").strip().lower()
    if not target:
        return 0
    _log = log or (lambda _m: None)
    active = ROOT / "accounts_registered_pending_sso.txt"
    moved_rows: list[str] = []
    keep: list[str] = []
    best_pw = str(password or "").strip()
    best_tok = str(mail_token or "").strip()

    if active.is_file():
        try:
            lines = active.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            _log(f"[pending-sso] exhausted read fail: {exc}")
            lines = []
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if not parsed:
                if str(ln).strip():
                    keep.append(ln)
                continue
            em = str(parsed.get("email") or "").strip().lower()
            if em != target:
                keep.append(ln)
                continue
            pw = str(parsed.get("password") or "").strip() or best_pw or "PENDING_NO_PW"
            tok = str(parsed.get("mail_token") or "").strip() or best_tok
            if pw and pw != "PENDING_NO_PW":
                best_pw = pw
            if tok and len(tok) >= len(best_tok):
                best_tok = tok
            note = str(parsed.get("note") or "pending_sso")
            tag = f"exhausted:{reason}" if reason else "exhausted"
            if tag not in note:
                note = f"{note}:{tag}" if note else tag
            if tok:
                b64 = "b64:" + base64.urlsafe_b64encode(tok.encode("utf-8")).decode("ascii")
                moved_rows.append(f"{parsed['email']}----{pw}----{note}----{b64}")
            else:
                moved_rows.append(f"{parsed['email']}----{pw}----{note}")
        try:
            tmp = active.with_suffix(active.suffix + ".tmp")
            body = "\n".join(keep)
            if keep:
                body += "\n"
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(active)
        except Exception as exc:
            _log(f"[pending-sso] exhausted active rewrite fail: {exc}")
            return 0

    for path2 in sorted(ROOT.glob("accounts_no_sso_*.txt")):
        try:
            lines = path2.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        kept2: list[str] = []
        changed = False
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if parsed and str(parsed.get("email") or "").strip().lower() == target:
                changed = True
                continue
            kept2.append(ln)
        if changed:
            try:
                body = "\n".join(kept2)
                if kept2:
                    body += "\n"
                path2.write_text(body, encoding="utf-8")
            except Exception:
                pass

    if not moved_rows:
        pw = best_pw or "PENDING_NO_PW"
        note = f"pending_sso:exhausted:{reason}"
        if best_tok:
            b64 = "b64:" + base64.urlsafe_b64encode(best_tok.encode("utf-8")).decode("ascii")
            moved_rows = [f"{target}----{pw}----{note}----{b64}"]
        else:
            moved_rows = [f"{target}----{pw}----{note}"]

    try:
        with PENDING_EXHAUSTED_PATH.open("a", encoding="utf-8") as fh:
            for row in moved_rows:
                fh.write(row + "\n")
        _log(
            f"[pending-sso] EXHAUSTED archive email={target} reason={reason} "
            f"rows={len(moved_rows)} file={PENDING_EXHAUSTED_PATH.name} active_remain={len(keep)}"
        )
    except Exception as exc:
        _log(f"[pending-sso] exhausted archive write fail email={target}: {exc}")
        return 0
    clear_pending_attempt(target, log=_log)
    return len(moved_rows)


def compact_pending_sso_file(log: Callable[[str], None] | None = None) -> dict:
    """Dedupe active pending file to one best row per email (richest mail_token)."""
    _log = log or (lambda _m: None)
    path2 = ROOT / "accounts_registered_pending_sso.txt"
    if not path2.is_file():
        return {"before": 0, "after": 0, "unique": 0}
    try:
        lines = path2.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        _log(f"[pending-sso] compact read fail: {exc}")
        return {"before": 0, "after": 0, "unique": 0}

    def _rank_line(parsed: dict) -> tuple:
        tok = str(parsed.get("mail_token") or "").strip()
        note = str(parsed.get("note") or "")
        return (
            1 if tok else 0,
            len(tok),
            1 if "b64:" in str(parsed.get("raw") or "") else 0,
            len(note),
        )

    best: dict[str, tuple] = {}
    order: list[str] = []
    before = 0
    for ln in lines:
        if not str(ln).strip():
            continue
        before += 1
        parsed = parse_pending_account_line(ln)
        if not parsed:
            key = f"__raw__{before}"
            best[key] = (ln, (0, 0, 0, 0))
            order.append(key)
            continue
        key = str(parsed.get("email") or "").strip().lower()
        if not key:
            continue
        rank = _rank_line(parsed)
        prev = best.get(key)
        if prev is None:
            best[key] = (ln, rank)
            order.append(key)
        elif rank >= prev[1]:
            best[key] = (ln, rank)

    new_lines = [best[k][0] for k in order if k in best]
    try:
        body = "\n".join(new_lines)
        if new_lines:
            body += "\n"
        tmp = path2.with_suffix(path2.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path2)
    except Exception as exc:
        _log(f"[pending-sso] compact write fail: {exc}")
        return {"before": before, "after": before, "unique": 0}
    info = {
        "before": before,
        "after": len(new_lines),
        "unique": len([k for k in order if not str(k).startswith("__raw__")]),
    }
    _log(
        f"[pending-sso] compact active file before={info['before']} "
        f"after={info['after']} unique~={info['unique']}"
    )
    return info


def maybe_exhaust_pending(
    email: str,
    *,
    reason: str,
    password: str = "",
    mail_token: str = "",
    log: Callable[[str], None] | None = None,
    force: bool = False,
) -> bool:
    """Bump attempt; if over cap (or force), archive exhausted and return True."""
    _log = log or (lambda _m: None)
    n = bump_pending_attempt(email, reason=reason, log=_log)
    if force or n >= MAX_PENDING_ATTEMPTS:
        archive_pending_exhausted(
            email,
            reason=f"{reason}:attempts={n}",
            password=password,
            mail_token=mail_token,
            log=_log,
        )
        return True
    return False



def result(status: str, **extra: Any) -> dict:
    out = {"status": status, "ok": status == STATUS_SUCCESS}
    out.update(extra)
    return out

def is_pool_empty_error(exc: BaseException | str) -> bool:
    msg = str(exc or "")
    low = msg.lower()
    keys = (
        "pool empty", "account pool empty", "configure aol_accounts", "no fresh email",
        "邮箱池", "获取邮箱失败", "account pool", "no available", "no idle", "empty pool",
        "池已空", "池为空", "没有可用邮箱", "无可用邮箱", "all accounts", "no accounts", "exhausted",
    )
    return any(k in msg or k in low for k in keys)


def _extract_sso_from_cookie_blob(blob: str) -> str:
    import re as _re
    blob = str(blob or "")
    if not blob:
        return ""
    for key in ("sso", "sso-rw"):
        m = _re.search(rf"(?:^|;\s*){key}=([^;]+)", blob)
        if m and len(m.group(1).strip()) >= 20:
            return m.group(1).strip()
    return ""


def _collect_sso_from_page(page, browser=None, log=None) -> str:
    """Harvest sso from browser cookie jar with multiple fallbacks."""
    log = log or (lambda _m: None)
    jar = {}
    if browser is not None:
        try:
            jar.update(dict(browser.export_cookies() or {}))
        except Exception as e:
            log(f"[pending-sso] export_cookies fail: {e}")
    cookies = []
    if page is not None:
        for kwargs in (
            {"all_domains": True, "all_info": True},
            {"all_domains": True},
            {},
        ):
            try:
                cookies = page.cookies(**kwargs) or []
                if cookies:
                    break
            except TypeError:
                try:
                    cookies = page.cookies() or []
                    break
                except Exception:
                    cookies = []
            except Exception:
                cookies = []
        for item in cookies or []:
            if isinstance(item, dict):
                n = str(item.get("name") or "")
                v = str(item.get("value") or "")
            else:
                n = str(getattr(item, "name", "") or "")
                v = str(getattr(item, "value", "") or "")
            if n and v:
                jar[n] = v
        try:
            doc = page.run_js("return document.cookie || ''") or ""
            sso_doc = _extract_sso_from_cookie_blob(doc)
            if sso_doc and "sso" not in jar:
                jar["sso"] = sso_doc
        except Exception:
            pass
        for runner_name in ("run_cdp", "run_cdp_loaded", "_run_cdp"):
            runner = getattr(page, runner_name, None)
            if not callable(runner):
                continue
            try:
                res = runner("Network.getAllCookies")
            except Exception:
                try:
                    res = runner("Network.getCookies")
                except Exception:
                    res = None
            if isinstance(res, dict):
                for item in res.get("cookies") or []:
                    n = str(item.get("name") or "")
                    v = str(item.get("value") or "")
                    if n and v:
                        jar[n] = v
            break
    sso = str(jar.get("sso") or jar.get("sso-rw") or "").strip()
    if sso and len(sso) >= 20:
        return sso
    return ""


def normalize_result(value: Any) -> dict:
    if isinstance(value, dict) and value.get("status"):
        return value
    if value is True:
        return result(STATUS_SUCCESS)
    if value is False:
        return result(STATUS_FAIL)
    return result(STATUS_FAIL, detail=str(value))


def parse_pending_account_line(line: str) -> dict | None:
    text = str(line or "").strip()
    if not text or text.startswith("#") or "----" not in text:
        return None
    parts = [p.strip() for p in text.split("----")]
    if len(parts) < 2:
        return None
    email, password = parts[0], parts[1]
    if not email or not password:
        return None
    note = parts[2] if len(parts) >= 3 else ""
    mail_token = ""
    # 18r27: optional 4th field is mailbox token (b64:… or raw JSON/app-password blob)
    if len(parts) >= 4:
        raw_tok = "----".join(parts[3:]).strip()
        mail_token = decode_pending_mail_token(raw_tok)
    return {
        "email": email,
        "password": password,
        "note": note,
        "mail_token": mail_token,
        "raw": text,
    }


def encode_pending_mail_token(mail_token: str) -> str:
    tok = str(mail_token or "").strip()
    if not tok:
        return ""
    import base64
    return "b64:" + base64.urlsafe_b64encode(tok.encode("utf-8")).decode("ascii")


def decode_pending_mail_token(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s.startswith("b64:"):
        import base64
        try:
            return base64.urlsafe_b64decode(s[4:].encode("ascii")).decode("utf-8")
        except Exception:
            return s[4:]
    return s



def is_pending_exhausted(email: str) -> bool:
    key = str(email or "").strip().lower()
    if not key:
        return False
    path = ROOT / "accounts_pending_sso_exhausted.txt"
    if not path.is_file():
        return False
    try:
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not str(ln).strip():
                continue
            if str(ln).split("----", 1)[0].strip().lower() == key:
                return True
    except Exception:
        return False
    return False


def purge_exhausted_from_active(log: Callable[[str], None] | None = None) -> int:
    """Remove any exhausted emails that re-entered active pending file."""
    _log = log or (lambda _m: None)
    active = ROOT / "accounts_registered_pending_sso.txt"
    if not active.is_file():
        return 0
    try:
        lines = active.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        _log(f"[pending-sso] purge_exhausted read fail: {exc}")
        return 0
    keep = []
    removed = 0
    for ln in lines:
        parsed = parse_pending_account_line(ln)
        if not parsed:
            if str(ln).strip():
                keep.append(ln)
            continue
        em = str(parsed.get("email") or "").strip().lower()
        if em and is_pending_exhausted(em):
            removed += 1
            continue
        keep.append(ln)
    if removed:
        try:
            body = "\n".join(keep)
            if keep:
                body += "\n"
            tmp = active.with_suffix(active.suffix + ".tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(active)
            _log(f"[pending-sso] purge_exhausted removed={removed} active_remain={len(keep)}")
        except Exception as exc:
            _log(f"[pending-sso] purge_exhausted write fail: {exc}")
            return 0
    return removed


def load_pending_sso_accounts(include_timestamped: bool = True) -> list[dict]:
    """Load pending SSO accounts.

    18r35j rules:
    - same email keeps the row WITH the longest mail_token (not first-seen bare row)
    - queue order: has_mail_token first, then original encounter order
    - bare no-token historical rows no longer block the head of the queue
    """
    best: dict[str, dict] = {}
    order: list[str] = []

    def _rank(item: dict) -> tuple:
        tok = str(item.get("mail_token") or "").strip()
        note = str(item.get("note") or "")
        return (
            1 if tok else 0,
            len(tok),
            1 if "b64:" in str(item.get("raw") or "") else 0,
            len(note),
        )

    def _add_from(path: Path) -> None:
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if not parsed:
                continue
            key = str(parsed.get("email") or "").strip().lower()
            if not key:
                continue
            if is_pending_exhausted(key):
                continue
            parsed["email"] = key
            parsed["source"] = path.name
            prev = best.get(key)
            if prev is None:
                best[key] = parsed
                order.append(key)
                continue
            # Prefer richer mail_token / longer token blob for the same mailbox.
            if _rank(parsed) > _rank(prev):
                # keep earliest source name for traceability
                parsed["source"] = prev.get("source") or parsed.get("source")
                best[key] = parsed

    _add_from(ROOT / "accounts_registered_pending_sso.txt")
    if include_timestamped:
        for pth in sorted(
            ROOT.glob("accounts_no_sso_*.txt"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            _add_from(pth)

    items = [best[k] for k in order if k in best]
    # Runnable accounts with mailbox credentials first; no-token sink to tail.
    items.sort(key=lambda it: (0 if str(it.get("mail_token") or "").strip() else 1,))
    return items


def archive_pending_no_mail_token(
    email: str,
    *,
    reason: str = "no_mail_token",
    log=None,
) -> int:
    """Move a no-mail_token pending row out of the active head file into archive.

    Keeps password history for manual review, but stops blocking recover queue.
    Does NOT delete success-path data; only rewrites pending files.
    """
    target = str(email or "").strip().lower()
    if not target:
        return 0
    _log = log or (lambda _m: None)
    active = ROOT / "accounts_registered_pending_sso.txt"
    archive = ROOT / "accounts_pending_no_mail_token_archive.txt"
    if not active.is_file():
        return 0
    try:
        lines = active.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        _log(f"[pending-sso] archive no_mail_token read fail: {exc}")
        return 0
    keep: list[str] = []
    archived_rows: list[str] = []
    moved = 0
    for ln in lines:
        parsed = parse_pending_account_line(ln)
        if not parsed:
            keep.append(ln)
            continue
        em = str(parsed.get("email") or "").strip().lower()
        tok = str(parsed.get("mail_token") or "").strip()
        if em == target and not tok:
            note = str(parsed.get("note") or "pending_sso")
            if reason and reason not in note:
                note = f"{note}:{reason}" if note else reason
            archived_rows.append(f"{parsed['email']}----{parsed['password']}----{note}")
            moved += 1
            continue
        keep.append(ln)
    if moved <= 0:
        return 0
    try:
        tmp = active.with_suffix(active.suffix + ".tmp")
        tmp.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        tmp.replace(active)
        if archived_rows:
            with archive.open("a", encoding="utf-8") as fh:
                for row in archived_rows:
                    fh.write(row + "\n")
        _log(
            f"[pending-sso] archived no_mail_token email={target} moved={moved} "
            f"archive={archive.name} active_remain={len(keep)}"
        )
    except Exception as exc:
        _log(f"[pending-sso] archive no_mail_token write fail email={target}: {exc}")
        return 0
    return moved


def remove_pending_sso_account(email: str, log: Callable[[str], None] | None = None) -> int:
    target = str(email or "").strip().lower()
    if not target:
        return 0
    removed = 0
    paths = [ROOT / "accounts_registered_pending_sso.txt"]
    paths.extend(sorted(ROOT.glob("accounts_no_sso_*.txt")))
    for path in paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            if log:
                log(f"[pending] read {path.name} fail: {exc}")
            continue
        kept: list[str] = []
        file_removed = 0
        for ln in lines:
            parsed = parse_pending_account_line(ln)
            if parsed and parsed["email"].lower() == target:
                file_removed += 1
                continue
            kept.append(ln)
        if file_removed:
            try:
                path.write_text(("\n".join(kept) + ("\n" if kept else "")), encoding="utf-8")
                removed += file_removed
                if log:
                    log(f"[pending] removed {target} x{file_removed} from {path.name}")
            except Exception as exc:
                if log:
                    log(f"[pending] write {path.name} fail: {exc}")
    return removed



def rotate_pending_sso_account_to_end(email: str, log: Callable[[str], None] | None = None) -> bool:
    """Move email line to end of primary pending file so next job picks another head."""
    target = str(email or "").strip().lower()
    if not target:
        return False
    path = ROOT / "accounts_registered_pending_sso.txt"
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        if log:
            log(f"[pending] rotate read fail: {exc}")
        return False
    keep: list[str] = []
    moved: list[str] = []
    for ln in lines:
        parsed = parse_pending_account_line(ln)
        if parsed and parsed["email"].lower() == target:
            moved.append(ln.strip() or (parsed.get("raw") or ln))
        else:
            keep.append(ln)
    if not moved:
        return False
    seen_m: set[str] = set()
    uniq_moved: list[str] = []
    for ln in moved:
        key = ln.strip().lower()
        if key in seen_m:
            continue
        seen_m.add(key)
        uniq_moved.append(ln)
    new_lines = [x for x in keep if str(x).strip()] + uniq_moved
    try:
        text = "\n".join(new_lines)
        if new_lines:
            text += "\n"
        path.write_text(text, encoding="utf-8")
    except Exception as exc:
        if log:
            log(f"[pending] rotate write fail: {exc}")
        return False
    if log:
        log(
            f"[pending] rotated {target} to end of {path.name} "
            f"(moved={len(uniq_moved)} remain={len(new_lines)})"
        )
    return True



def _probe_signin_turnstile(page) -> dict:
    js = r"""
const input = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
const iframe = document.querySelector('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]');
const host = document.querySelector('.cf-turnstile, [data-sitekey], #hybrid-turnstile-host, #cf-challenge-running, #challenge-form');
let tok = '';
try { tok = String((input && input.value) || window.__hybrid_turnstile || ''); } catch (e) {}
try {
  if (!tok && window.turnstile && typeof turnstile.getResponse === 'function') {
    tok = String(turnstile.getResponse() || '');
  }
} catch (e) {}
let sitekey = '';
try {
  const el = document.querySelector('[data-sitekey]');
  if (el) sitekey = String(el.getAttribute('data-sitekey') || '');
} catch (e) {}
const body = String((document.body && document.body.innerText) || '').slice(0, 240).toLowerCase();
const challengeText = (
  body.includes('确认您是真人') || body.includes('verify you are human') ||
  body.includes('just a moment') || body.includes('checking your browser') ||
  body.includes('cloudflare') || body.includes('turnstile')
);
return {
  hasInput: !!input,
  hasIframe: !!iframe,
  hasHost: !!host,
  hasChallengeUi: !!(iframe || host || challengeText),
  tokLen: tok ? tok.length : 0,
  sitekey: sitekey,
  status: String(window.__hybrid_turnstile_status || ''),
  url: location.href
};
"""
    try:
        st = page.run_js(js) or {}
        return st if isinstance(st, dict) else {"raw": st}
    except Exception as exc:
        return {"error": str(exc)}


def _inject_turnstile_token(page, token: str) -> dict:
    js = r"""
const token = String(arguments[0] || '');
const out = {ok:false, synced:0, nodes:0, tokenLen: token.length};
if (!token || token.length < 20) { out.reason='token_too_short'; return out; }
const nodes = Array.from(document.querySelectorAll(
  'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"], input[name="cf_turnstile_response"]'
));
out.nodes = nodes.length;
function setNode(n){
  try {
    const proto = n.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) desc.set.call(n, token); else n.value = token;
    n.setAttribute('value', token);
    n.dispatchEvent(new Event('input', {bubbles:true}));
    n.dispatchEvent(new Event('change', {bubbles:true}));
    out.synced += 1;
  } catch (e) { out.err = String(e); }
}
if (!nodes.length) {
  try {
    const inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'cf-turnstile-response';
    inp.value = token;
    (document.querySelector('form') || document.body).appendChild(inp);
    nodes.push(inp);
    out.nodes = 1;
    out.created = true;
  } catch (e) { out.createErr = String(e); }
}
nodes.forEach(setNode);
try { window.__hybrid_turnstile = token; window.__hybrid_turnstile_status = 'injected'; } catch (e) {}
// Some Next forms read from a React state via hidden field name variants.
try {
  document.querySelectorAll('[name*="turnstile" i], [id*="turnstile" i]').forEach(n => {
    if (n && (n.tagName === 'INPUT' || n.tagName === 'TEXTAREA')) setNode(n);
  });
} catch (e) {}
out.ok = out.synced > 0;
out.finalLen = 0;
try {
  const v = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
  out.finalLen = v ? String(v.value||'').length : 0;
} catch (e) {}
return out;
"""
    try:
        st = page.run_js(js, token) or {}
        return st if isinstance(st, dict) else {"raw": st}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _click_signin_submit(page) -> dict:
    js = r"""
const out = {clicked:false, submit:false, enter:false, btn:''};
function isVisible(node){
  if(!node) return false;
  const s=getComputedStyle(node);
  if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
  const r=node.getBoundingClientRect();
  return r.width>0 && r.height>0;
}
function isDisabled(node){
  if(!node) return true;
  if(node.disabled) return true;
  return (node.getAttribute('aria-disabled')||'').toLowerCase()==='true';
}
function txt(n){
  return ((n.innerText||n.textContent||n.value||'')+' '+(n.getAttribute('aria-label')||'')).replace(/\s+/g,' ').trim();
}
const btns = Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]'));
for (const b of btns){
  if(!isVisible(b)||isDisabled(b)) continue;
  const t = txt(b).toLowerCase();
  if(!t) continue;
  if(t.includes('返回')||t.includes('back')||t.includes('注册')||t.includes('sign up')||t.includes('忘记')||t.includes('forgot')) continue;
  if(t.includes('您正在登录')||t.includes('logging in')||t.includes('loading')||t.includes('请稍候')) continue;
  if(t.includes('登录')||t.includes('log in')||t.includes('sign in')||t.includes('continue')||t.includes('下一步')||t.includes('next')||t.includes('继续')){
    try { b.focus(); b.click(); out.clicked=true; out.btn=txt(b); break; } catch(e) { out.err=String(e); }
  }
}
try {
  const form = document.querySelector('form');
  if (form && form.requestSubmit) { form.requestSubmit(); out.submit=true; }
  else if (form) { form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})); out.submit=true; }
} catch(e) { out.submitErr=String(e); }
try {
  const pw=document.querySelector('input[type="password"]');
  if (pw) {
    pw.focus();
    pw.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
    pw.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
    out.enter=true;
  }
} catch(e) {}
return out;
"""
    try:
        st = page.run_js(js) or {}
        return st if isinstance(st, dict) else {"raw": st}
    except Exception as exc:
        return {"clicked": False, "error": str(exc)}



def _read_page_turnstile_token(page) -> str:
    js = r"""
let tok = '';
try { if (window.__hybrid_turnstile) tok = String(window.__hybrid_turnstile || ''); } catch (e) {}
if (!tok) {
  const n = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
  tok = String((n && n.value) || '');
}
try {
  if (!tok && window.turnstile && typeof turnstile.getResponse === 'function') {
    tok = String(turnstile.getResponse() || '');
  }
} catch (e) {}
return tok || '';
"""
    try:
        return str(page.run_js(js) or "").strip()
    except Exception:
        return ""


def _ensure_signin_turnstile(
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
    try:
        from grok_register_ttk import sleep_with_cancel as _swc
    except Exception:
        def _swc(sec, _stop=None):
            import time as _t
            end = _t.time() + float(sec or 0)
            while _t.time() < end:
                if _stop and _stop():
                    break
                _t.sleep(min(0.2, max(0.0, end - _t.time())))
    sleep_with_cancel = _swc
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

    token = ""
    # 18r42c: if page has sitekey/input but no challenge UI/iframe, do not burn 80s+
    try:
        if (not bool(probe0.get("hasIframe")) and not bool(probe0.get("hasHost"))
                and not bool(probe0.get("hasChallengeUi")) and int(probe0.get("tokLen") or 0) < 80):
            timeout = min(float(timeout), 18.0)
            log(f"[pending-sso] turnstile shortened timeout={timeout} reason={reason} (no challenge UI)")
    except Exception:
        pass

    # Prefer BrowserTokenSession helper (inject widget + turnstilePatch path).
    try:
        if browser is not None and hasattr(browser, "get_turnstile_token"):
            log(f"[pending-sso] turnstile solve via BrowserTokenSession reason={reason} timeout={timeout}")
            token = str(
                browser.get_turnstile_token(
                    timeout=int(timeout),
                    inject=True,
                    cancel_callback=stop,
                )
                or ""
            ).strip()
            if token:
                out["method"] = "browser.get_turnstile_token"
    except TypeError:
        try:
            token = str(browser.get_turnstile_token(timeout=int(timeout), inject=True) or "").strip()
            if token:
                out["method"] = "browser.get_turnstile_token"
        except Exception as exc:
            log(f"[pending-sso] browser.get_turnstile_token fail: {exc}")
    except Exception as exc:
        log(f"[pending-sso] browser.get_turnstile_token fail: {exc}")

    if (not token or len(token) < 80) and not stop():
        try:
            from grok_register_ttk import getTurnstileToken

            log(f"[pending-sso] turnstile solve via getTurnstileToken reason={reason}")
            token = str(getTurnstileToken(log_callback=log, cancel_callback=stop) or "").strip()
            if token:
                out["method"] = (out.get("method") or "") + "+getTurnstileToken"
        except TypeError:
            try:
                from grok_register_ttk import getTurnstileToken

                token = str(getTurnstileToken(log_callback=log) or "").strip()
                if token:
                    out["method"] = (out.get("method") or "") + "+getTurnstileToken"
            except Exception as exc:
                log(f"[pending-sso] getTurnstileToken fail: {exc}")
        except Exception as exc:
            log(f"[pending-sso] getTurnstileToken fail: {exc}")

    # Poll injected widget token if helpers returned short/empty.
    if (not token or len(token) < 80) and not stop():
        # 18r42c: default poll shorter when helpers already failed (token still empty)
        poll_cap = 16.0 if (not token) else 45.0
        deadline = time.time() + max(6.0, min(poll_cap, float(timeout)))
        while time.time() < deadline and not stop():
            pr = _probe_signin_turnstile(page)
            try:
                if int(pr.get("tokLen") or 0) >= 80:
                    # read full token
                    try:
                        token = str(
                            page.run_js(
                                """
let tok='';
try{ if(window.__hybrid_turnstile) tok=String(window.__hybrid_turnstile||''); }catch(e){}
if(!tok){
  const n=document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
  tok=String((n&&n.value)||'');
}
try{ if(!tok && window.turnstile && turnstile.getResponse) tok=String(turnstile.getResponse()||''); }catch(e){}
return tok;
"""
                            )
                            or ""
                        ).strip()
                    except Exception:
                        token = ""
                    if token:
                        out["method"] = (out.get("method") or "") + "+poll"
                        break
            except Exception:
                pass
            sleep_with_cancel(0.8, stop)

    if not token or len(token) < 80:
        probe1 = _probe_signin_turnstile(page)
        out.update({"ok": False, "detail": "token_missing", "probe": probe1, "token_len": len(token or "")})
        log(f"[pending-sso] turnstile FAIL reason={reason} token_len={len(token or '')} probe={probe1}")
        return out

    inj = _inject_turnstile_token(page, token)
    out["inject"] = inj
    out["token_len"] = len(token)
    out["ok"] = bool(inj.get("ok") or int(inj.get("finalLen") or 0) >= 80)
    log(
        f"[pending-sso] turnstile OK reason={reason} method={out.get('method')} "
        f"token_len={out['token_len']} inject={inj}"
    )
    # Do not log full token (huge); length + inject status is enough for ops, user asked no desense for accounts
    # but turnstile JWT is not needed in full in every line — still log head for debug if short enough path fails
    if not out["ok"]:
        log(f"[pending-sso] turnstile inject weak; token_head={token[:24]}")
    return out


def recover_one_pending_sso(
    *,
    email: str,
    password: str,
    log: Callable[[str], None],
    proxy: str = "",
    should_stop: Optional[Callable[[], bool]] = None,
    post_success: bool = True,
    accounts_file: Path | None = None,
) -> dict:
    """Browser sign-in for a verified account and harvest sso/sso-rw cookies."""
    from browser.token_harvester import BrowserTokenSession
    from grok_register_ttk import (
        _get_page,
        open_signup_page,
        schedule_post_registration,
        sleep_with_cancel,
    )

    stop = should_stop or (lambda: False)
    email = str(email or "").strip()
    password = str(password or "").strip()
    if not email or not password:
        return result(STATUS_FAIL, detail="missing email/password", email=email)
    if stop():
        return result(STATUS_STOPPED, email=email)

    signin_url = "https://accounts.x.ai/sign-in?redirect=grok-com"
    t0 = time.time()
    log(f"[pending-sso] start recover email={email}")

    wait_inputs_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pick(sel) {
  return Array.from(document.querySelectorAll(sel)).find(n => isVisible(n) && !n.disabled) || null;
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]');
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]');
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'))
  .filter(n => isVisible(n) && !n.disabled)
  .map(buttonText).filter(Boolean).slice(0, 8);
return {
  url: location.href,
  title: document.title || '',
  email: !!emailInput,
  pw: !!pwInput,
  ready: !!(emailInput && pwInput),
  emailOnly: !!(emailInput && !pwInput),
  buttons: buttons,
  body: (document.body && document.body.innerText || '').slice(0, 180).replace(/\s+/g, ' ')
};
"""

    advance_email_step_js = r"""
const email = String(arguments[0] || '');
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pickAll(sel) {
  return Array.from(document.querySelectorAll(sel)).filter(n => isVisible(n) && !n.disabled);
}
function pick(sel) {
  return pickAll(sel)[0] || null;
}
function setVal(input, value) {
  if (!input) return false;
  try { input.removeAttribute('readonly'); } catch (e) {}
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('blur', { bubbles: true }));
  return String(input.value || '').trim() === String(value || '').trim();
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function isBusyText(t) {
  const s = String(t || '').toLowerCase();
  return (
    s.includes('您正在登录') ||
    s.includes('正在登录') ||
    s.includes('signing in') ||
    s.includes('logging in') ||
    s.includes('loading') ||
    s.includes('please wait') ||
    s.includes('请稍候') ||
    s.includes('处理中') ||
    s.includes('submitting')
  );
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]')
  || pickAll('input').find(n => {
      const t = ((n.name||'') + ' ' + (n.id||'') + ' ' + (n.placeholder||'') + ' ' + (n.getAttribute('aria-label')||'')).toLowerCase();
      return t.includes('email') || t.includes('user') || t.includes('邮箱') || t.includes('账号');
    }) || null;
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]');
const out = {
  url: location.href,
  email: !!emailInput,
  pw: !!pwInput,
  emailFilled: false,
  clicked: false,
  btn: '',
  reason: ''
};
if (pwInput) {
  out.reason = 'password_already_ready';
  return out;
}
if (!emailInput) {
  out.reason = 'no_email_input';
  return out;
}
out.emailFilled = setVal(emailInput, email);
out.emailVal = String(emailInput.value || '');
if (!out.emailFilled) {
  out.reason = 'email_fill_mismatch';
  return out;
}
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(n => isVisible(n) && !n.disabled);
const btn = buttons.find(n => {
  const t = buttonText(n);
  const low = t.toLowerCase().replace(/\s+/g, '');
  if (!t || isBusyText(t)) return false;
  if (n.getAttribute('aria-disabled') === 'true') return false;
  if (n.getAttribute('aria-busy') === 'true') return false;
  if (String(n.getAttribute('type') || '').toLowerCase() === 'submit') return true;
  return (
    low.includes('下一步') ||
    low.includes('继续') ||
    low.includes('繼續') ||
    low.includes('next') ||
    low.includes('continue') ||
    low === '登录' ||
    (low.includes('登录') && !low.includes('正在') && !low.includes('邮箱登录'))
  );
}) || null;
if (btn) {
  out.btn = buttonText(btn);
  try { btn.focus(); btn.click(); out.clicked = true; out.reason = 'email_next_clicked'; }
  catch (e) { out.reason = 'click_err:' + String(e); }
} else {
  out.reason = 'no_next_button';
  try {
    emailInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    emailInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    out.clicked = true;
    out.btn = 'ENTER_ON_EMAIL';
    out.reason = 'email_enter';
  } catch (e) {
    out.reason = 'no_next_and_enter_fail:' + String(e);
  }
}
return out;
"""

    click_email_signin_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function score(node) {
  const t = buttonText(node);
  const compact = t.replace(/\s+/g, '').toLowerCase();
  if (!t) return -1;
  if (compact.includes('使用邮箱登录') || compact.includes('用邮箱登录')) return 100;
  if (compact.includes('邮箱') && compact.includes('登录')) return 95;
  if (compact.includes('continuewithemail') || compact.includes('signinwithemail') || compact.includes('sign-inwithemail')) return 92;
  if (compact.includes('email') && (compact.includes('sign') || compact.includes('log'))) return 90;
  return -1;
}
const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div[tabindex], span[role="button"]'))
  .filter(n => isVisible(n));
let best = null, bestScore = -1;
for (const n of nodes) {
  const s = score(n);
  if (s > bestScore) { best = n; bestScore = s; }
}
if (!best || bestScore < 0) {
  return {clicked:false, reason:'no-email-signin-btn', candidates: nodes.map(buttonText).filter(Boolean).slice(0,12)};
}
try { best.scrollIntoView({block:'center'}); } catch (e) {}
try { best.focus(); } catch (e) {}
try { best.click(); } catch (e) { return {clicked:false, reason:String(e), text:buttonText(best)}; }
return {clicked:true, score:bestScore, text:buttonText(best)};
"""

    fill_js = r"""const email = String(arguments[0] || '');
const password = String(arguments[1] || '');
const doClick = !!arguments[2];

function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function pickAll(sel) {
  return Array.from(document.querySelectorAll(sel)).filter(n => isVisible(n) && !n.disabled);
}
function pick(sel) {
  return pickAll(sel)[0] || null;
}
function setVal(input, value) {
  if (!input) return false;
  try { input.removeAttribute('readonly'); } catch (e) {}
  input.focus();
  try { input.click(); } catch (e) {}
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  const tracker = input._valueTracker;
  if (tracker) tracker.setValue('');
  if (nativeSetter) nativeSetter.call(input, value);
  else input.value = value;
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('blur', { bubbles: true }));
  return String(input.value || '').trim() === String(value || '').trim();
}
function buttonText(node) {
  return [node.innerText, node.textContent, node.getAttribute('value'), node.getAttribute('aria-label'), node.getAttribute('name')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function isBusyText(t) {
  const s = String(t || '').toLowerCase();
  return (
    s.includes('您正在登录') ||
    s.includes('正在登录') ||
    s.includes('signing in') ||
    s.includes('logging in') ||
    s.includes('loading') ||
    s.includes('please wait') ||
    s.includes('请稍候') ||
    s.includes('处理中') ||
    s.includes('submitting')
  );
}
function isSubmitCandidate(node) {
  if (!node || node.disabled) return false;
  const t = buttonText(node);
  const low = t.toLowerCase();
  if (!t || isBusyText(t)) return false;
  if (node.getAttribute('aria-disabled') === 'true') return false;
  if (node.getAttribute('aria-busy') === 'true') return false;
  if (String(node.getAttribute('type') || '').toLowerCase() === 'submit') return true;
  return (
    low.includes('sign in') ||
    low.includes('log in') ||
    low === '登录' ||
    (low.includes('登录') && !low.includes('正在')) ||
    low.includes('繼續') ||
    low.includes('继续') ||
    low.includes('next') ||
    low.includes('continue') ||
    low.includes('submit')
  );
}
const emailInput = pick('input[type="email"], input[name="email"], input[autocomplete="username"], input[autocomplete="email"], input[data-testid*="email" i], input[placeholder*="email" i], input[placeholder*="邮箱"]')
  || pickAll('input').find(n => {
      const t = ((n.name||'') + ' ' + (n.id||'') + ' ' + (n.placeholder||'') + ' ' + (n.getAttribute('aria-label')||'')).toLowerCase();
      return t.includes('email') || t.includes('user') || t.includes('邮箱') || t.includes('账号');
    }) || null;
const pwInput = pick('input[type="password"], input[name="password"], input[autocomplete="current-password"], input[data-testid*="password" i]')
  || pickAll('input[type="password"]')[0] || null;
const out = {
  url: location.href,
  email: !!emailInput,
  pw: !!pwInput,
  filled: false,
  clicked: false,
  btn: '',
  emailVal: emailInput ? String(emailInput.value||'') : '',
  pwLen: pwInput ? String(pwInput.value||'').length : 0
};
if (!emailInput || !pwInput) {
  out.reason = 'inputs_not_ready';
  return out;
}
out.emailFilled = setVal(emailInput, email);
out.pwFilled = setVal(pwInput, password);
out.filled = !!(out.emailFilled && out.pwFilled);
out.emailVal = String(emailInput.value || '');
out.pwLen = String(pwInput.value || '').length;
if (!out.filled) {
  out.reason = 'fill_mismatch';
  return out;
}
const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]')).filter(isVisible);
const btn = buttons.find(isSubmitCandidate) || null;
if (btn) {
  out.btn = buttonText(btn);
}
// 18r28b: do NOT auto-click login here; Turnstile must be solved first, then _click_signin_submit.
out.doClick = doClick;
if (doClick) {
  if (btn) {
    if (isBusyText(out.btn)) {
      out.reason = 'busy_button';
      out.clicked = false;
    } else {
      try { btn.focus(); btn.click(); out.clicked = true; out.reason = 'clicked'; } catch (e) { out.clickErr = String(e); }
    }
  } else {
    try {
      if (pw) {
        pw.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
        pw.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
        out.clicked = true;
        out.btn = 'ENTER_ON_PASSWORD';
        out.reason = 'enter';
      } else {
        out.reason = 'no_submit_button';
      }
    } catch (e) {
      out.clickErr = String(e);
      out.reason = 'enter_fail';
    }
  }
} else {
  out.clicked = false;
  out.reason = 'fill_only_wait_turnstile';
}

return out;
"""

    try:
        with BrowserTokenSession(log=log) as browser:
            if stop():
                return result(STATUS_STOPPED, email=email)
            # BrowserTokenSession.__enter__ already started Chromium.  Reuse its blank tab
            # and navigate directly to sign-in; never bootstrap through the sign-up route.
            log("[pending-sso] browser ready; direct-to-sign-in (no sign-up navigation)")
            page = _get_page()
            if page is None:
                return result(STATUS_FAIL, email=email, detail="no browser page")

            # 18r24: prefer email=true deep-link so we skip flaky "使用邮箱登录" social landing.
            signin_email_url = signin_url
            if "email=" not in str(signin_url):
                signin_email_url = (
                    str(signin_url)
                    + ("&" if "?" in str(signin_url) else "?")
                    + "email=true"
                )
            nav_targets = [signin_email_url, signin_url]
            for nav_try in range(1, 5):
                if stop():
                    return result(STATUS_STOPPED, email=email)
                target = nav_targets[(nav_try - 1) % len(nav_targets)]
                try:
                    page.get(target)
                    try:
                        page.wait.doc_loaded()
                    except Exception:
                        pass
                    sleep_with_cancel(1.2, stop)
                    cur = str(getattr(page, "url", "") or "")
                    log(f"[pending-sso] navigate sign-in try={nav_try} target={target} url={cur}")
                    # if already on email form path, stop retrying nav
                    if "email=true" in cur or "sign-in" in cur or "accounts.x.ai" in cur:
                        # probe once whether email input exists
                        try:
                            probe = page.run_js(wait_inputs_js) or {}
                        except Exception:
                            probe = {}
                        if isinstance(probe, dict) and (probe.get("email") or probe.get("pw") or probe.get("ready")):
                            log(f"[pending-sso] sign-in inputs visible after nav: {probe}")
                            break
                        if nav_try >= 2 and "email=true" in cur:
                            break
                except Exception as nav_exc:
                    if stop():
                        return result(STATUS_STOPPED, email=email)
                    log(f"[pending-sso] navigate sign-in fail try={nav_try}: {nav_exc}")
                    if nav_try >= 4:
                        return result(STATUS_FAIL, email=email, detail=str(nav_exc))
                    sleep_with_cancel(1.0, stop)

            ready = False
            wait_deadline = time.time() + 55
            last_wait = {}
            email_btn_clicks = 0
            email_next_clicks = 0
            email_btn_logged = False
            error_page_recovers = 0
            click_reload_js = r"""
(() => {
  const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]'));
  const textOf = (n) => String((n.innerText || n.textContent || n.value || n.getAttribute('aria-label') || '')).replace(/\s+/g, ' ').trim();
  const reload = nodes.find((n) => /重新加载|reload|refresh|重试|try again/i.test(textOf(n)));
  if (!reload) return {clicked:false, reason:'no-reload-btn', candidates: nodes.map(textOf).filter(Boolean).slice(0,8)};
  try { reload.scrollIntoView({block:'center'}); } catch (e) {}
  try { reload.click(); } catch (e) { return {clicked:false, reason:String(e)}; }
  return {clicked:true, text:textOf(reload)};
})()
"""
            while time.time() < wait_deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    cur_url = str(getattr(page, "url", "") or "")
                except Exception:
                    cur_url = ""
                # chrome-error / blank recover: click reload or re-nav (fail-fast)
                if (
                    "chrome-error://" in cur_url
                    or cur_url.startswith("chrome://")
                    or cur_url in ("", "about:blank", "data:,")
                ):
                    error_page_recovers += 1
                    log(f"[pending-sso] error/blank page recover#{error_page_recovers} url={cur_url}")
                    recovered = False
                    try:
                        rr = page.run_js(click_reload_js) or {}
                    except Exception as rr_exc:
                        rr = {"clicked": False, "error": str(rr_exc)}
                    if isinstance(rr, dict) and rr.get("clicked"):
                        log(f"[pending-sso] clicked page reload btn: {rr.get('text')}")
                        recovered = True
                        sleep_with_cancel(1.5, stop)
                    else:
                        try:
                            target = signin_email_url if error_page_recovers % 2 == 1 else signin_url
                            page.get(target)
                            try:
                                page.wait.doc_loaded()
                            except Exception:
                                pass
                            recovered = True
                            sleep_with_cancel(1.2, stop)
                        except Exception as renav_exc:
                            log(f"[pending-sso] error-page re-nav fail: {renav_exc}")
                    if error_page_recovers >= 4:
                        return result(
                            STATUS_FAIL,
                            email=email,
                            detail=f"sign-in chrome-error stuck url={cur_url} recovers={error_page_recovers}",
                            fail_reason="need_reregister",
                        )
                    if recovered:
                        continue
                try:
                    last_wait = page.run_js(wait_inputs_js) or {}
                except Exception as wait_exc:
                    last_wait = {"error": str(wait_exc)}
                if isinstance(last_wait, dict) and last_wait.get("ready"):
                    ready = True
                    log(f"[pending-sso] pw ready state={last_wait}")
                    break
                # xAI sign-in first screen only shows social + "使用邮箱登录"; click it.
                if (
                    isinstance(last_wait, dict)
                    and not last_wait.get("email")
                    and not last_wait.get("pw")
                    and email_btn_clicks < 4
                ):
                    try:
                        click_r = page.run_js(click_email_signin_js) or {}
                    except Exception as click_exc:
                        click_r = {"clicked": False, "error": str(click_exc)}
                    # reload-only interstitial: click 重新加载 then re-nav
                    try:
                        cands = []
                        if isinstance(click_r, dict):
                            cands = list(click_r.get("candidates") or [])
                        cand_text = " ".join(str(x) for x in cands)
                        if (not click_r.get("clicked")) and (
                            "重新加载" in cand_text or "reload" in cand_text.lower()
                        ):
                            error_page_recovers += 1
                            try:
                                rr = page.run_js(click_reload_js) or {}
                            except Exception as rr_exc:
                                rr = {"clicked": False, "error": str(rr_exc)}
                            log(
                                f"[pending-sso] reload-only candidates recover#{error_page_recovers} rr={rr}"
                            )
                            if not (isinstance(rr, dict) and rr.get("clicked")):
                                try:
                                    page.get(signin_email_url)
                                    try:
                                        page.wait.doc_loaded()
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                            sleep_with_cancel(1.2, stop)
                            if error_page_recovers >= 4:
                                return result(
                                    STATUS_FAIL,
                                    email=email,
                                    detail=(
                                        f"sign-in reload-only stuck recovers={error_page_recovers} "
                                        f"cands={cands[:6]}"
                                    ),
                                    fail_reason="need_reregister",
                                )
                            continue
                    except Exception as cand_exc:
                        log(f"[pending-sso] reload-only handle fail: {cand_exc}")
                    if isinstance(click_r, dict) and click_r.get("clicked"):
                        email_btn_clicks += 1
                        log(
                            f"[pending-sso] clicked email sign-in btn#{email_btn_clicks}: {click_r.get('text')}"
                        )
                        sleep_with_cancel(1.0, stop)
                        # 18r24: after 2 empty clicks, force email=true deep link
                        if email_btn_clicks >= 2:
                            try:
                                force_u = signin_url
                                if "email=" not in str(force_u):
                                    force_u = (
                                        str(force_u)
                                        + ("&" if "?" in str(force_u) else "?")
                                        + "email=true"
                                    )
                                log(
                                    f"[pending-sso] force email=true deep-link after empty clicks -> {force_u}"
                                )
                                page.get(force_u)
                                try:
                                    page.wait.doc_loaded()
                                except Exception:
                                    pass
                                sleep_with_cancel(1.2, stop)
                            except Exception as force_exc:
                                log(f"[pending-sso] force email=true fail: {force_exc}")
                        continue
                    elif email_btn_clicks == 0 and isinstance(click_r, dict):
                        # log once for diagnostics (candidates, no secrets)
                        if not email_btn_logged:
                            log(f"[pending-sso] email sign-in btn not found yet: {click_r}")
                            email_btn_logged = True
                # Two-step login: email field first, then click 下一步 / Continue, then password appears.
                if (
                    isinstance(last_wait, dict)
                    and last_wait.get("email")
                    and not last_wait.get("pw")
                    and email_next_clicks < 5
                ):
                    try:
                        step_r = page.run_js(advance_email_step_js, email) or {}
                    except Exception as step_exc:
                        step_r = {"clicked": False, "error": str(step_exc)}
                    email_next_clicks += 1
                    log(f"[pending-sso] email next #{email_next_clicks}: {step_r}")
                    sleep_with_cancel(1.2 if email_next_clicks == 1 else 0.9, stop)
                    continue
                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                if "sign-up" in cur:
                    try:
                        page.get(signin_url)
                    except Exception:
                        pass
                sleep_with_cancel(0.8, stop)
            log(f"[pending-sso] wait inputs ready={ready} state={last_wait}")
            if not ready:
                # 18r42b: cannot reach email/pw form (chrome-error / proxy / reload) -> re-register path
                lw = last_wait if isinstance(last_wait, dict) else {}
                lw_url = str(lw.get("url") or "")
                stuck_net = (
                    "chrome-error://" in lw_url
                    or lw_url.startswith("chrome://")
                    or "chromewebdata" in lw_url
                    or (not lw.get("email") and not lw.get("pw"))
                )
                return result(
                    STATUS_FAIL,
                    email=email,
                    detail=f"sign-in inputs not ready: {last_wait}",
                    remove_pending=True if stuck_net else False,
                    fail_reason="need_reregister",
                )

            # 18r28: solve Turnstile on sign-in BEFORE first credential submit.
            ts_pre = _ensure_signin_turnstile(
                page, browser, log, stop, reason="before-fill", timeout=80.0
            )
            log(
                f"[pending-sso] before-fill turnstile ok={ts_pre.get('ok')} "
                f"len={ts_pre.get('token_len')} method={ts_pre.get('method')}"
            )

            fill_state = {}
            for fill_try in range(1, 5):
                if stop():
                    return result(STATUS_STOPPED, email=email)
                try:
                    fill_state = page.run_js(fill_js, email, password) or {}
                except Exception as fill_exc:
                    log(f"[pending-sso] fill/sign-in js fail try={fill_try}: {fill_exc}")
                    fill_state = {"error": str(fill_exc)}
                # Re-inject token after fill (DOM rebuild may drop hidden field).
                try:
                    tok_keep = ""
                    try:
                        tok_keep = _read_page_turnstile_token(page)
                    except Exception:
                        tok_keep = ""
                    if len(tok_keep) >= 80:
                        inj_keep = _inject_turnstile_token(page, tok_keep)
                        if isinstance(fill_state, dict):
                            fill_state["turnstile_reinject"] = inj_keep
                    elif ts_pre.get("ok"):
                        # token lost from DOM; re-solve once
                        ts_again = _ensure_signin_turnstile(
                            page, browser, log, stop, reason=f"after-fill-{fill_try}", timeout=50.0
                        )
                        if isinstance(fill_state, dict):
                            fill_state["turnstile_resolves"] = {
                                "ok": ts_again.get("ok"),
                                "len": ts_again.get("token_len"),
                            }
                except Exception as inj_exc:
                    log(f"[pending-sso] turnstile reinject after fill fail: {inj_exc}")
                log(f"[pending-sso] fill state try={fill_try} {fill_state}")
                if isinstance(fill_state, dict) and fill_state.get("filled"):
                    break
                sleep_with_cancel(1.0, stop)
            if not (isinstance(fill_state, dict) and fill_state.get("filled")):
                return result(STATUS_FAIL, email=email, detail=f"fill failed: {fill_state}")

            page_state_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const body = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 240);
const low = body.toLowerCase();
let err = '';
if ((low.includes('密码') || low.includes('password')) && (low.includes('错误') || low.includes('不正确') || low.includes('invalid') || low.includes('wrong') || low.includes('incorrect'))) err = 'bad_password';
else if (low.includes('incorrect') || low.includes('invalid password') || low.includes('wrong password') || low.includes('密码错误') || low.includes('密码不正确')) err = 'bad_password';
else if (low.includes('过多') || low.includes('too many') || low.includes('rate') || low.includes('try again later') || low.includes('稍后')) err = 'rate_limit';
else if ((low.includes('验证') || low.includes('verify') || low.includes('challenge')) && (low.includes('人机') || low.includes('captcha') || low.includes('turnstile') || low.includes('cloudflare'))) err = 'captcha';
else if (low.includes('不存在') || low.includes('no account') || low.includes('not found') || low.includes('找不到') || low.includes('未能找到')) err = 'account_missing';
else if (low.includes('an error occurred') || low.includes('出错了') || low.includes('发生错误') || low.includes('something went wrong') || low.includes('unable to sign') || low.includes('无法登录') || low.includes('登录失败')) err = 'auth_error';
return {
  url: location.href,
  title: document.title || '',
  body: body,
  err: err,
  hasPw: !!Array.from(document.querySelectorAll('input[type="password"]')).find(isVisible),
  cookie: document.cookie || ''
};
"""

            # 18r28h: solve Turnstile once, then EXACTLY ONE login submit.
            # Old path: click_after_ts + submit boost = double 登录 click (user saw "又重新登录").
            ts_res = _ensure_signin_turnstile(
                page, browser, log, stop, reason="pre-submit", timeout=75.0
            )
            click_after_ts = {"clicked": False, "submit": False}
            if ts_res.get("ok"):
                try:
                    click_after_ts = _click_signin_submit(page) or {}
                    log(f"[pending-sso] ONE login submit after turnstile: {click_after_ts}")
                except Exception as click_ts_exc:
                    log(f"[pending-sso] click after turnstile fail: {click_ts_exc}")
                    click_after_ts = {"clicked": False, "error": str(click_ts_exc)}
            else:
                log(
                    f"[pending-sso] pre-submit turnstile not ok; still ONE submit attempt "
                    f"detail={ts_res.get('detail')}"
                )
                try:
                    click_after_ts = _click_signin_submit(page) or {}
                    log(f"[pending-sso] ONE login submit without ts ok: {click_after_ts}")
                except Exception as click_ts_exc:
                    log(f"[pending-sso] ONE login submit fail: {click_ts_exc}")
                    click_after_ts = {"clicked": False, "error": str(click_ts_exc)}

            # 18r28h: NO second boost click/requestSubmit/Enter — already submitted once.
            submit_ts = time.time()
            _auth_ts_retried = False
            _login_submit_done = True
            _block_login_refill = True
            log(
                f"[pending-sso] login_submit_done=1 block_refill=1 "
                f"clicked={bool(click_after_ts.get('clicked') or click_after_ts.get('submit'))} "
                f"email={email} (fail path = hybrid re-register only, never re-login)"
            )

            # Hard wait: do NOT re-fill immediately; re-fill used to interrupt in-flight login.
            try:
                sleep_with_cancel(2.5, stop)
            except Exception:
                pass

            sso = ""
            deadline = time.time() + 120
            last_url = ""
            last_err = ""
            last_body = ""
            visited_accounts = False
            visited_grok = False
            refill_tries = 0
            cf_solve_tries = 0
            last_cf_solve_ts = 0.0
            harvest_rounds = 0
            last_refill_ts = 0.0
            # 18r28h defaults (also set true right after ONE submit)
            _login_submit_done = True
            _block_login_refill = True
            left_signin_once = False
            cf_seen = False
            post_submit_quiet_until = submit_ts + 12.0  # first 12s: observe only

            loading_js = r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const body = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').slice(0, 280);
const low = body.toLowerCase();
const hasCf = !!(document.querySelector('#challenge-form, #cf-challenge-running, .cf-browser-verification, iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]')
  || low.includes('checking your browser') || low.includes('just a moment') || low.includes('verify you are human')
  || low.includes('正在验证') || low.includes('人机验证') || low.includes('请完成验证'));
// NOTE: page heading itself is often "您正在登录" — do NOT treat that alone as loading.
const loadingText = low.includes('logging in') || low.includes('signing in') || low.includes('请稍候') || low.includes('please wait') || (low.includes('loading') && !low.includes('log in'));
const busyBtn = Array.from(document.querySelectorAll('button,[role="button"]')).some(b => {
  if (!isVisible(b)) return false;
  const ariaBusy = (b.getAttribute('aria-busy') || '').toLowerCase() === 'true';
  if (ariaBusy || b.disabled) return true;
  const t = ((b.innerText || b.textContent || '') + '').replace(/\s+/g,' ').trim().toLowerCase();
  // only spinner-like exclusive labels
  if (!t) return false;
  if (t === 'loading' || t === '请稍候' || t === 'logging in' || t === 'signing in') return true;
  return false;
});
return {
  url: location.href,
  body: body,
  hasCf: hasCf,
  loading: loadingText || busyBtn,
  hasPw: !!Array.from(document.querySelectorAll('input[type="password"]')).find(isVisible),
  title: document.title || ''
};
"""

            while time.time() < deadline:
                if stop():
                    return result(STATUS_STOPPED, email=email)
                harvest_rounds += 1
                now = time.time()

                sso = _collect_sso_from_page(page, browser=browser, log=log)
                if sso and len(sso) >= 20:
                    log(f"[pending-sso] sso harvested len={len(sso)} round={harvest_rounds}")
                    break

                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                if cur and cur != last_url:
                    log(f"[pending-sso] url={cur}")
                    last_url = cur

                try:
                    pst = page.run_js(page_state_js) or {}
                except Exception as pst_exc:
                    pst = {"error": str(pst_exc)}

                try:
                    loadst = page.run_js(loading_js) or {}
                except Exception:
                    loadst = {}

                page_err = ""
                body = ""
                if isinstance(pst, dict):
                    page_err = str(pst.get("err") or "").strip()
                    body = str(pst.get("body") or "")
                    if body and body != last_body and (page_err or harvest_rounds <= 4 or harvest_rounds % 6 == 0):
                        log(f"[pending-sso] page body={body}")
                        last_body = body
                    body_low = body.lower()
                    if (not page_err) and body and (
                        "an error occurred" in body_low
                        or "something went wrong" in body_low
                        or "无法登录" in body
                        or "登录失败" in body
                        or "出错了" in body
                    ):
                        page_err = "auth_error"
                    if page_err and page_err != last_err:
                        log(f"[pending-sso] page_err={page_err} body={body}")
                        last_err = page_err
                        # 18r28b: generic "An error occurred" is often CF/token race, not real bad password.
                        # Retry once with fresh Turnstile + single submit before hard-fail.
                        body_l = str(body or "").lower()
                        generic_auth = (
                            page_err == "auth_error"
                            and (
                                "an error occurred" in body_l
                                or "出错了" in str(body or "")
                                or "发生错误" in str(body or "")
                                or "something went wrong" in body_l
                            )
                        )
                        # 18r28e: at most ONE fresh-Turnstile login retry; then leave sign-in
                        # immediately for hybrid re-register. Never keep clicking 登录.
                        # 18r28f: ANY login page_err after first submit -> IMMEDIATE re-register.
                        # Do NOT click 登录 again (user: 登录失败改走注册，不要又重新登录).
                        # First login already solved Turnstile; second login only burns time / CF.
                        if page_err in {"bad_password", "account_missing", "auth_error", "need_reregister"}:
                            log(
                                f"[pending-sso] page_err={page_err} -> IMMEDIATE re-register "
                                f"(NO second login click) email={email} body={body[:240]}"
                            )
                            _block_login_refill = True
                            _auth_ts_retried = True
                            return result(
                                STATUS_FAIL,
                                email=email,
                                detail=f"sign-in page_err={page_err}",
                                remove_pending=True,
                                fail_reason=(
                                    page_err
                                    if page_err in {"bad_password", "account_missing"}
                                    else "auth_error"
                                ),
                            )

                    cookie_doc = str(pst.get("cookie") or "")
                    sso_doc = _extract_sso_from_cookie_blob(cookie_doc)
                    if sso_doc:
                        sso = sso_doc
                        log(f"[pending-sso] sso from document.cookie len={len(sso)}")
                        break

                has_cf = bool(isinstance(loadst, dict) and loadst.get("hasCf")) or page_err == "captcha"
                is_loading = bool(isinstance(loadst, dict) and loadst.get("loading"))
                # 18r28h: after first login submit, CF stuck must NOT loop forever / skip re-register.
                # Old bug: `continue` here bypassed the 10s IMMEDIATE re-register rule, so browser
                # kept sitting on sign-in and looked like "又重新登录".
                if has_cf and ("sign-in" in (cur or "")) and not sso:
                    cf_seen = True
                    elapsed_sub = now - submit_ts
                    if harvest_rounds == 1 or harvest_rounds % 5 == 0:
                        log(
                            f"[pending-sso] cloudflare/captcha detected round={harvest_rounds} "
                            f"elapsed={elapsed_sub:.1f}s url={cur}"
                        )
                    # Only ONE inject-only CF assist, and only inside first 10s window.
                    if (
                        elapsed_sub < 10.0
                        and cf_solve_tries < 1
                        and (now - last_cf_solve_ts) >= 3.0
                        and not stop()
                    ):
                        cf_solve_tries += 1
                        last_cf_solve_ts = now
                        log(f"[pending-sso] active turnstile inject-only try={cf_solve_tries}/1 (cf stuck, no re-login)")
                        ts_cf = _ensure_signin_turnstile(
                            page, browser, log, stop, reason=f"cf-stuck-{cf_solve_tries}", timeout=45.0, force_fresh=True
                        )
                        if ts_cf.get("ok"):
                            try:
                                tok = _read_page_turnstile_token(page)
                                inj = _inject_turnstile_token(page, tok)
                                log(
                                    f"[pending-sso] cf turnstile inject-only (NO re-login click) "
                                    f"try={cf_solve_tries} tok_len={len(tok or '')} inj={inj}"
                                )
                            except Exception as inj_exc:
                                log(f"[pending-sso] cf turnstile inject-only fail: {inj_exc}")
                            post_submit_quiet_until = time.time() + 4.0
                        sleep_with_cancel(1.2, stop)
                        continue
                    if elapsed_sub >= 10.0 and not is_loading:
                        log(
                            f"[pending-sso] CF/sign-in stuck after first submit "
                            f"elapsed={elapsed_sub:.1f}s cf_tries={cf_solve_tries} "
                            f"-> IMMEDIATE re-register (NO re-login) email={email}"
                        )
                        return result(
                            STATUS_FAIL,
                            email=email,
                            detail="cf/sign-in stuck after first submit -> re-register",
                            remove_pending=True,
                            fail_reason="auth_error",
                        )
                    # still within quiet/loading: wait, do not click login
                    sleep_with_cancel(1.2, stop)
                    continue
                elif has_cf:
                    cf_seen = True

                left_signin = bool(cur) and ("sign-in" not in cur)
                on_consent = bool(cur) and ("consent" in cur or "authorize" in cur or "set-cookie" in cur or "auth" in cur)
                if left_signin or on_consent:
                    left_signin_once = True

                # Only after confirmed leave-sign-in, materialize cookies on accounts/grok.
                if left_signin_once and (not sso) and (left_signin or on_consent):
                    if not visited_accounts:
                        visited_accounts = True
                        try:
                            log("[pending-sso] left sign-in -> open accounts.x.ai to materialize sso cookies")
                            page.get("https://accounts.x.ai/")
                            try:
                                page.wait.doc_loaded()
                            except Exception:
                                pass
                            sleep_with_cancel(1.5, stop)
                            sso = _collect_sso_from_page(page, browser=browser, log=log)
                            if sso:
                                log(f"[pending-sso] sso after accounts.x.ai len={len(sso)}")
                                break
                        except Exception as acc_exc:
                            log(f"[pending-sso] open accounts.x.ai fail: {acc_exc}")
                    if (not sso) and (not visited_grok):
                        visited_grok = True
                        try:
                            log("[pending-sso] left sign-in -> open grok.com to materialize session cookies")
                            page.get("https://grok.com/")
                            try:
                                page.wait.doc_loaded()
                            except Exception:
                                pass
                            sleep_with_cancel(1.8, stop)
                            sso = _collect_sso_from_page(page, browser=browser, log=log)
                            if sso:
                                log(f"[pending-sso] sso after grok.com len={len(sso)}")
                                break
                        except Exception as grok_exc:
                            log(f"[pending-sso] open grok.com fail: {grok_exc}")

                # Still on sign-in: wait quietly after submit; re-fill only if settled and no progress.
                if ("sign-in" in (cur or "")) and (not sso):
                    quiet = now < post_submit_quiet_until
                    if quiet or is_loading:
                        if harvest_rounds <= 3 or harvest_rounds % 4 == 0:
                            log(
                                f"[pending-sso] post-submit wait quiet={quiet} loading={is_loading} "
                                f"cf={cf_seen} elapsed={now - submit_ts:.1f}s url={cur}"
                            )
                        sleep_with_cancel(1.2, stop)
                        continue

                    # 18r28f: NEVER re-click 登录 after the first Turnstile-backed submit.
                    # Idle sign-in without SSO = credential/session fail -> hybrid re-register.
                    # (Old re-fill path caused: login fail then login again then login again.)
                    if (now - submit_ts) >= 10.0 and not sso and not is_loading:
                        # If CF challenge UI is actively up without token, solve once then ONE submit only when never submitted? 
                        # First submit already happened; do not login again.
                        log(
                            f"[pending-sso] still on sign-in after first submit "
                            f"elapsed={now-submit_ts:.1f}s cf={cf_seen} -> IMMEDIATE re-register "
                            f"(NO re-fill login) email={email}"
                        )
                        return result(
                            STATUS_FAIL,
                            email=email,
                            detail="sign-in stuck after first submit -> re-register",
                            remove_pending=True,
                            fail_reason="auth_error",
                        )
                    # 18r28h: DO NOT long-wait probe then navigate back to sign-in
                    # (that looked exactly like "登录失败后又重新登录").
                    # 10s rule above already returns auth_error -> hybrid re-register.

                sleep_with_cancel(1.0, stop)

            if not sso:
                try:
                    pst = page.run_js(page_state_js) or {}
                except Exception:
                    pst = {}
                log(f"[pending-sso] no sso after sign-in email={email} last_fill={fill_state} last_page={pst}")
                # 18r28e: login could not mint SSO -> outer must re-register, not only rotate pending
                fr = "auth_error"
                try:
                    body_n = str((pst or {}).get("body") or "")
                    err_n = str((pst or {}).get("err") or "")
                    if err_n in {"bad_password", "account_missing"}:
                        fr = err_n
                    elif "错误的邮箱地址或密码" in body_n or (
                        "密码" in body_n and ("错误" in body_n or "不正确" in body_n)
                    ):
                        fr = "bad_password"
                except Exception:
                    pass
                return result(
                    STATUS_FAIL,
                    email=email,
                    detail=f"no sso after sign-in page={pst}",
                    remove_pending=True,
                    fail_reason=fr,
                )

            try:
                from protocol.sso_util import (
                    is_session_sso,
                    is_wrapper_sso,
                    materialize_sso_via_browser,
                    materialize_sso_via_http,
                )
                if is_wrapper_sso(sso) or not is_session_sso(sso):
                    log(f"[pending-sso] materialize wrapper sso len={len(sso)}")
                    sess_sso = ""
                    try:
                        page2 = _get_page()
                        sess_sso = materialize_sso_via_browser(page2, sso, log=log, timeout=40)
                    except Exception:
                        sess_sso = ""
                    if not sess_sso or not is_session_sso(sess_sso):
                        try:
                            sess_sso = materialize_sso_via_http(
                                sso,
                                proxy=proxy,
                                log=log,
                            ) or sess_sso
                        except Exception:
                            pass
                    if sess_sso and is_session_sso(sess_sso):
                        sso = sess_sso
                        log(f"[pending-sso] session sso ready len={len(sso)}")
            except Exception as mat_exc:
                log(f"[pending-sso] sso materialize: {mat_exc}")

            out_path = accounts_file or (
                ROOT / f"accounts_pending_sso_recovered_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            )
            _sso_ok = True
            try:
                from protocol.sso_util import is_mail_token_blob, is_session_sso, normalize_sso_token
                sso = normalize_sso_token(sso)
                if is_mail_token_blob(sso) or not is_session_sso(sso):
                    _sso_ok = False
                    log(f"[!] refuse save non-session SSO email={email} sso_len={len(sso or '')}")
            except Exception:
                pass
            if not (_sso_ok and sso):
                log(f"[pending-sso] skip save: no importable session SSO email={email}")
                return result(
                    STATUS_FAIL,
                    email=email,
                    detail="recovered_token_not_session_sso",
                    remove_pending=False,
                    fail_reason="need_reregister",
                )
            try:
                line = f"{email}----{password}----{sso}\n"
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(line)
                log(f"[pending-sso] saved recovered account -> {out_path.name}")
            except Exception as save_exc:
                log(f"[pending-sso] save recovered fail: {save_exc}")

            try:
                remove_pending_sso_account(email, log=log)
            except Exception as rm_exc:
                log(f"[pending-sso] remove pending entry fail: {rm_exc}")

            jar_full = {}
            try:
                jar_full = dict(browser.export_cookies() or {})
            except Exception:
                jar_full = {}
            jar_full["sso"] = sso
            jar_full["sso-rw"] = jar_full.get("sso-rw") or sso
            cookie_list = [{"name": k, "value": v} for k, v in jar_full.items()]

            if post_success:
                try:
                    schedule_post_registration(
                        email, password, sso, page=None, cookies=cookie_list, log_callback=log
                    )
                except Exception as post_exc:
                    log(f"[pending-sso] post_success: {post_exc}")

            log(f"[pending-sso][+] recovered email={email} sso_len={len(sso)} elapsed={time.time()-t0:.1f}s")
            return result(STATUS_SUCCESS, email=email, sso_len=len(sso), accounts_file=str(out_path))

    except Exception as exc:
        if stop():
            log("[pending-sso] stopped during recover")
            return result(STATUS_STOPPED, email=email)
        log(f"[pending-sso] exception: {exc}")
        import traceback
        try:
            log(traceback.format_exc())
        except Exception:
            pass
        return result(STATUS_FAIL, email=email, detail=str(exc))


def run_pending_sso_recovery_job(count=0, log_callback=None, controller=None, workers=None):
    """Recover SSO for pending accounts via browser sign-in."""
    import grok_register_ttk as engine

    log = log_callback or engine.cli_log
    if controller is None:
        controller = engine.CliStopController()

    try:
        compact_pending_sso_file(log=log_callback or (lambda _m: None))
        purge_exhausted_from_active(log=log_callback or (lambda _m: None))
    except Exception as _c_exc:
        try:
            (log_callback or (lambda _m: None))(f"[pending-sso] compact on start fail: {_c_exc}")
        except Exception:
            pass
    pending = load_pending_sso_accounts(include_timestamped=True)
    try:
        _tok_n = sum(1 for it in pending if str(it.get("mail_token") or "").strip())
        _notok_n = len(pending) - _tok_n
        (log_callback or print)(
            f"[pending-sso] queue loaded total={len(pending)} with_mail_token={_tok_n} "
            f"no_mail_token={_notok_n} (token-first order)"
        )
        if pending:
            head = pending[0]
            (log_callback or print)(
                f"[pending-sso] queue head email={head.get('email')} "
                f"mail_token_len={len(str(head.get('mail_token') or ''))} "
                f"note={head.get('note')}"
            )
    except Exception as _qexc:
        (log_callback or print)(f"[pending-sso] queue stats fail: {_qexc}")
    if count and count > 0:
        pending = pending[: int(count)]

    success_count = 0
    fail_count = 0
    skipped = 0
    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_pending_sso_recovered_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] pending_sso 二次补 SSO 启动，待处理: {len(pending)}（count限制={count or 'all'}）")
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")

    mode = str(engine.config.get("proxy_mode", "direct") or "direct")
    try:
        resolved_proxy = engine.apply_resolved_proxy_to_config(log_callback=log, fetch_live=True)
    except Exception as proxy_exc:
        log(f"[!] 获取/解析代理失败: {proxy_exc}")
        raise
    if resolved_proxy:
        log(f"[*] 代理模式: {mode} | {resolved_proxy}")
    else:
        log(f"[*] 代理模式: {mode or 'direct'}（直连）")
    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    try:
        from worker_coord import resolve_workers
        _workers = resolve_workers(engine.config, workers)
    except Exception:
        _workers = 1
    if _workers > 1:
        log(f"[*] pending_sso multi-thread workers={_workers} (account list pre-sliced; no dual claim)")
        return _run_pending_sso_recovery_job_mt(
            pending=pending,
            count=count,
            log=log,
            controller=controller,
            workers=_workers,
            proxy=proxy,
            accounts_output_file=accounts_output_file,
            engine=engine,
        )

    try:
        if not pending:
            log("[*] pending_sso 列表为空，无需恢复")
        for i, item in enumerate(pending):
            if controller.should_stop():
                break
            email = item.get("email") or ""
            password = item.get("password") or ""
            log(f"--- [pending-sso] 开始第 {i + 1}/{len(pending)} 个账号 email={email} source={item.get('source')} ---")
            raw = recover_one_pending_sso(
                email=email,
                password=password,
                log=log,
                proxy=proxy,
                should_stop=controller.should_stop,
                post_success=True,
                accounts_file=Path(accounts_output_file),
            )
            res = normalize_result(raw)
            status = res.get("status")
            detail = str(res.get("detail") or "")
            fail_reason = str(res.get("fail_reason") or "")
            if not fail_reason:
                low = detail.lower()
                if "bad_password" in low or "page_err=bad_password" in low:
                    fail_reason = "bad_password"
                elif "account_missing" in low or "page_err=account_missing" in low:
                    fail_reason = "account_missing"
                elif (
                    "auth_error" in low
                    or "page_err=auth_error" in low
                    or "an error occurred" in low
                    or "no sso after sign-in" in low
                    or "turnstile_retry_failed" in low
                    or "after_turnstile_retry" in low
                ):
                    fail_reason = "auth_error"
            if controller.should_stop() or status == STATUS_STOPPED:
                log("[*] 当前 pending 恢复因停止请求中断，统计保持不变")
                break
            if status == STATUS_SUCCESS:
                success_count += 1
            else:
                fail_count += 1
                # 18r24b: always rotate failed head to end so next round / count=1 is not stuck.
                try:
                    rotate_pending_sso_account_to_end(email, log=log)
                except Exception as rot_exc:
                    log(f"[pending] rotate after fail error: {rot_exc}")
                # 18r28e: 登录失败（含 no-sso）一律改走 hybrid 重注册，禁止再回到登录死循环。
                # 关键：accounts_registered_pending_sso 仅在最终成功后才移出；
                # 若重注册失败仍保留原 pending，避免数据丢失。
                need_rereg = (
                    fail_reason in {"bad_password", "account_missing", "auth_error", "need_reregister"}
                    or res.get("remove_pending")
                    or ("no sso after sign-in" in detail.lower())
                    or ("sign-in page_err" in detail.lower())
                )
                if need_rereg:
                    if not fail_reason:
                        fail_reason = "auth_error"
                    log(
                        f"[pending-sso] {fail_reason or 'auth_fail'} -> 暂保留 pending，"
                        f"改走注册流程 email={email}（成功后再移出）"
                    )
                    if not controller.should_stop():
                        try:
                            import importlib
                            import hybrid_register as _hr
                            importlib.reload(_hr)
                            register_one_hybrid = _hr.register_one_hybrid
                            log(
                                f"[pending-sso] login failed -> STOP further sign-in; "
                                f"re-register via hybrid start (reason={fail_reason or detail}) email={email}"
                            )
                            # Close pending sign-in browser before hybrid opens a fresh signup session
                            try:
                                engine.stop_browser(log_callback=log)
                                log("[pending-sso] closed sign-in browser before hybrid re-register")
                            except Exception as sb_exc:
                                log(f"[pending-sso] stop sign-in browser before rereg: {sb_exc}")
                            re_accounts = Path(accounts_output_file)
                            # also keep a dedicated re-register success sink
                            try:
                                re_accounts = ROOT / f"accounts_reregistered_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt"
                            except Exception:
                                re_accounts = ROOT / f"accounts_reregistered_{time.strftime('%Y%m%d_%H%M%S')}.txt"
                            # 18r27: always re-register the SAME pending mailbox (not a fresh pool pull).
                            forced_mail_token = str(item.get("mail_token") or "").strip()
                            forced_xai_password = str(password or "").strip()
                            if not forced_mail_token:
                                try:
                                    from hybrid_register import _lookup_mail_token_from_pool as _lt
                                    forced_mail_token = str(_lt(email, log=log) or "").strip()
                                    log(
                                        f"[pending-sso] pre-rereg mail_token lookup "
                                        f"email={email} len={len(forced_mail_token)}"
                                    )
                                except Exception as lkp_exc:
                                    log(f"[pending-sso] pre-rereg mail_token lookup fail: {lkp_exc}")
                                    forced_mail_token = ""
                            if not forced_mail_token:
                                log(
                                    f"[pending-sso] skip forced re-register missing mail_token "
                                    f"email={email} -> archive no_mail_token (unblocks queue; no IMAP/Graph creds)"
                                )
                                try:
                                    archive_pending_no_mail_token(
                                        email,
                                        reason="no_mail_token_cannot_reregister",
                                        log=log,
                                    )
                                except Exception as arc_exc:
                                    log(f"[pending-sso] archive no_mail_token fail: {arc_exc}")
                                rr = {
                                    "status": "fail",
                                    "ok": False,
                                    "email": email,
                                    "detail": "skip_reregister_no_mail_token_archived",
                                    "fail_reason": "no_mail_token",
                                }
                            else:
                                log(
                                    f"[pending-sso] re-register forced_email={email} "
                                    f"mail_token_len={len(forced_mail_token)} "
                                    f"xai_password_len={len(forced_xai_password)} "
                                    f"note={str(item.get('note') or '')}"
                                )
                                rr = register_one_hybrid(
                                    log=log,
                                    proxy=proxy,
                                    should_stop=controller.should_stop,
                                    accounts_file=re_accounts,
                                    post_success=True,
                                    forced_email=email,
                                    forced_mail_token=forced_mail_token,
                                    forced_xai_password=forced_xai_password,
                                )
                            rr = normalize_result(rr)
                            rr_status = rr.get("status")
                            rr_email = str(rr.get("email") or "").strip()
                            log(
                                f"[pending-sso] re-register result status={rr_status} "
                                f"detail={rr.get('detail')} email={rr_email or email}"
                            )
                            if rr_status == STATUS_SUCCESS:
                                success_count += 1
                                fail_count = max(0, fail_count - 1)
                                # Only drop pending when the recovered/registered email matches.
                                if rr_email.lower() == str(email or "").strip().lower() or not rr_email:
                                    try:
                                        remove_pending_sso_account(email, log=log)
                                        clear_pending_attempt(email, log=log)
                                        log(f"[pending-sso] re-register success -> 移出 pending email={email}")
                                    except Exception as rm_exc:
                                        log(f"[pending-sso] remove pending after re-register success fail: {rm_exc}")
                                else:
                                    log(
                                        f"[pending-sso] re-register success email={rr_email} "
                                        f"!= pending {email}; keep original pending line"
                                    )
                            elif rr_status == STATUS_PENDING_SSO:
                                detail_rr = str(rr.get("detail") or "")
                                log(
                                    f"[pending-sso] re-register got pending_sso again detail={detail_rr} "
                                    f"email={rr_email or email}"
                                )
                                try:
                                    exhausted = maybe_exhaust_pending(
                                        email,
                                        reason=detail_rr or "re_register_pending_sso",
                                        password=str(password or ""),
                                        mail_token=str(item.get("mail_token") or ""),
                                        log=log,
                                    )
                                    if exhausted:
                                        log(
                                            f"[pending-sso] email exhausted after re-register pending_sso "
                                            f"email={email} detail={detail_rr}"
                                        )
                                    else:
                                        try:
                                            rotate_pending_sso_account_to_end(email, log=log)
                                        except Exception:
                                            pass
                                        try:
                                            compact_pending_sso_file(log=log)
                                        except Exception:
                                            pass
                                        log(
                                            f"[pending-sso] kept in queue after pending_sso "
                                            f"attempts={get_pending_attempt(email)}/{MAX_PENDING_ATTEMPTS} email={email}"
                                        )
                                except Exception as ex_exc:
                                    log(f"[pending-sso] exhaust check fail: {ex_exc}")
                            elif rr_status == STATUS_STOPPED:
                                log("[pending-sso] re-register stopped; pending kept")
                                break
                            elif rr_status == STATUS_POOL_EMPTY:
                                skipped += 1
                                log("[pending-sso] re-register pool empty")
                        except Exception as reg_exc:
                            log(f"[pending-sso] re-register exception: {reg_exc}")
                            try:
                                log(traceback.format_exc())
                            except Exception:
                                pass
            log(f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count} | pending_sso 0 | 跳过(池空) {skipped}")
            engine.sleep_with_cancel(1, controller.should_stop)
    except KeyboardInterrupt:
        controller.stop()
        log("[!] 收到 Ctrl+C，正在停止")
    except Exception as exc:
        log(f"[!] pending_sso 恢复任务异常: {exc}")
        try:
            log(traceback.format_exc())
        except Exception:
            pass
    finally:
        try:
            if controller.should_stop():
                engine.force_stop_registration(log_callback=log, reason="pending_sso_job_stopped")
            else:
                engine.stop_browser(log_callback=log)
        except Exception as stop_exc:
            log(f"[!] pending finally stop browser: {stop_exc}")
        try:
            engine.wait_post_success_queue(timeout=15 if controller.should_stop() else 45, log_callback=log)
        except Exception:
            pass
        try:
            engine.cleanup_runtime_memory(log_callback=log, reason="pending_sso 恢复任务结束")
        except Exception:
            pass
        log(f"[*] pending_sso 恢复结束。成功 {success_count} | 失败 {fail_count} | pending_sso 0 | 跳过(池空) {skipped}")

    return {
        "success": success_count,
        "fail": fail_count,
        "pending_sso": 0,
        "skipped": skipped,
        "pool_empty": False,
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
        "job": "pending_sso_recovery",
    }



def _run_pending_sso_recovery_job_mt(
    *,
    pending,
    count,
    log,
    controller,
    workers,
    proxy,
    accounts_output_file,
    engine,
):
    """Parallel pending SSO recovery: list is pre-partitioned per worker (no shared pop race)."""
    import threading
    from pathlib import Path as _Path
    from worker_coord import JobCoordinator, bind_worker_proxy, clear_worker_proxy, worker_log

    items = list(pending or [])
    wn = max(1, min(int(workers or 1), max(1, len(items))))
    log(f"[*] pending_sso MT start workers={wn} items={len(items)}")
    coord = JobCoordinator(len(items), log=log)
    accounts_file = _Path(accounts_output_file)
    # partition round-robin so no two workers share the same email
    buckets = [[] for _ in range(wn)]
    for idx, item in enumerate(items):
        buckets[idx % wn].append(item)

    def _worker(wid: int, my_items):
        wlog = worker_log(log, wid)
        coord.worker_enter()
        try:
            wproxy = bind_worker_proxy(engine, wid, log=wlog) or proxy
            for j, item in enumerate(my_items):
                if controller.should_stop():
                    break
                email = item.get("email") or ""
                password = item.get("password") or ""
                wlog(
                    f"--- [pending-sso] worker={wid} {j+1}/{len(my_items)} "
                    f"email={email} source={item.get('source')} ---"
                )
                try:
                    raw = recover_one_pending_sso(
                        email=email,
                        password=password,
                        log=wlog,
                        proxy=wproxy,
                        should_stop=controller.should_stop,
                        post_success=True,
                        accounts_file=accounts_file,
                    )
                    res = normalize_result(raw)
                    status = res.get("status")
                    detail = str(res.get("detail") or "")
                    fail_reason = str(res.get("fail_reason") or "")
                    if status == STATUS_SUCCESS:
                        coord.record_success()
                    elif status == STATUS_STOPPED:
                        break
                    else:
                        coord.record_fail()
                        # 18r35i: MT must also hybrid re-register (serial path already does).
                        if not fail_reason:
                            low = detail.lower()
                            if "bad_password" in low or "page_err=bad_password" in low:
                                fail_reason = "bad_password"
                            elif "account_missing" in low or "page_err=account_missing" in low:
                                fail_reason = "account_missing"
                            elif (
                                "auth_error" in low
                                or "page_err=auth_error" in low
                                or "an error occurred" in low
                                or "no sso after sign-in" in low
                                or "turnstile_retry_failed" in low
                                or "inputs not ready" in low
                                or "chrome-error" in low
                                or "reload-only" in low
                                or "chromewebdata" in low
                            ):
                                fail_reason = (
                                    "need_reregister"
                                    if (
                                        "inputs not ready" in low
                                        or "chrome-error" in low
                                        or "reload-only" in low
                                        or "chromewebdata" in low
                                    )
                                    else "auth_error"
                                )
                        need_rereg = (
                            fail_reason
                            in {"bad_password", "account_missing", "auth_error", "need_reregister"}
                            or res.get("remove_pending")
                            or ("no sso after sign-in" in detail.lower())
                            or ("sign-in page_err" in detail.lower())
                            or ("inputs not ready" in detail.lower())
                            or ("chrome-error" in detail.lower())
                            or ("reload-only" in detail.lower())
                            or ("chromewebdata" in detail.lower())
                        )
                        if need_rereg and not controller.should_stop():
                            try:
                                rotate_pending_sso_account_to_end(email, log=wlog)
                            except Exception as rot_exc:
                                wlog(f"[pending] rotate after fail error: {rot_exc}")
                            wlog(
                                f"[pending-sso] {fail_reason or 'auth_fail'} -> MT hybrid re-register "
                                f"email={email} (success 后再移出 pending)"
                            )
                            try:
                                import importlib
                                import hybrid_register as _hr
                                importlib.reload(_hr)
                                register_one_hybrid = _hr.register_one_hybrid
                                try:
                                    engine.stop_browser(log_callback=wlog)
                                    wlog("[pending-sso] closed sign-in browser before hybrid re-register")
                                except Exception as sb_exc:
                                    wlog(f"[pending-sso] stop sign-in browser before rereg: {sb_exc}")
                                try:
                                    re_accounts = ROOT / (
                                        f"accounts_reregistered_{engine.now_beijing('%Y%m%d_%H%M%S')}_w{wid}.txt"
                                    )
                                except Exception:
                                    import time as _t
                                    re_accounts = ROOT / (
                                        f"accounts_reregistered_{_t.strftime('%Y%m%d_%H%M%S')}_w{wid}.txt"
                                    )
                                forced_mail_token = str(item.get("mail_token") or "").strip()
                                forced_xai_password = str(password or "").strip()
                                if not forced_mail_token:
                                    try:
                                        from hybrid_register import _lookup_mail_token_from_pool as _lt
                                        forced_mail_token = str(_lt(email, log=wlog) or "").strip()
                                        wlog(
                                            f"[pending-sso] pre-rereg mail_token lookup "
                                            f"email={email} len={len(forced_mail_token)}"
                                        )
                                    except Exception as lkp_exc:
                                        wlog(f"[pending-sso] pre-rereg mail_token lookup fail: {lkp_exc}")
                                        forced_mail_token = ""
                                if not forced_mail_token:
                                    wlog(
                                        f"[pending-sso] skip forced re-register missing mail_token "
                                        f"email={email} -> archive no_mail_token (unblocks queue)"
                                    )
                                    try:
                                        archive_pending_no_mail_token(
                                            email,
                                            reason="no_mail_token_cannot_reregister",
                                            log=wlog,
                                        )
                                    except Exception as arc_exc:
                                        wlog(f"[pending-sso] archive no_mail_token fail: {arc_exc}")
                                    # MT path previously fell through without rr; keep explicit fail marker on item
                                    try:
                                        item["fail_reason"] = "no_mail_token"
                                        item["detail"] = "skip_reregister_no_mail_token_archived"
                                    except Exception:
                                        pass
                                else:
                                    wlog(
                                        f"[pending-sso] re-register forced_email={email} "
                                        f"mail_token_len={len(forced_mail_token)} "
                                        f"xai_password_len={len(forced_xai_password)}"
                                    )
                                    rr = register_one_hybrid(
                                        log=wlog,
                                        proxy=wproxy,
                                        should_stop=controller.should_stop,
                                        accounts_file=re_accounts,
                                        post_success=True,
                                        forced_email=email,
                                        forced_mail_token=forced_mail_token,
                                        forced_xai_password=forced_xai_password,
                                    )
                                    rr = normalize_result(rr)
                                    rr_status = rr.get("status")
                                    rr_email = str(rr.get("email") or "").strip()
                                    wlog(
                                        f"[pending-sso] re-register result status={rr_status} "
                                        f"detail={rr.get('detail')} email={rr_email or email}"
                                    )
                                    if rr_status == STATUS_SUCCESS:
                                        # convert prior fail into success for this worker slot
                                        try:
                                            coord.record_success()
                                            # undo one fail if API allows; otherwise leave both
                                            if hasattr(coord, "undo_fail"):
                                                coord.undo_fail()
                                            elif hasattr(coord, "record_fail_adjust"):
                                                coord.record_fail_adjust(-1)
                                            else:
                                                # best-effort: success already counted; fail remains inflated
                                                wlog("[pending-sso] note: fail counter not decremented (no undo_fail)")
                                        except Exception as adj_exc:
                                            wlog(f"[pending-sso] success adjust: {adj_exc}")
                                        if rr_email.lower() == str(email or "").strip().lower() or not rr_email:
                                            try:
                                                remove_pending_sso_account(email, log=wlog)
                                                clear_pending_attempt(email, log=wlog)
                                                wlog(f"[pending-sso] re-register success -> 移出 pending email={email}")
                                            except Exception as rm_exc:
                                                wlog(f"[pending-sso] remove pending after success fail: {rm_exc}")
                                    elif rr_status == STATUS_PENDING_SSO:
                                        # 18r36a: count attempts; exhaust dead-letter after cap
                                        try:
                                            if hasattr(coord, "undo_fail"):
                                                coord.undo_fail()
                                            if hasattr(coord, "record_pending"):
                                                coord.record_pending(
                                                    rate_limited=("rate_limit" in str(rr.get("detail") or "").lower()
                                                                  or "create_email_rate" in str(rr.get("detail") or "").lower())
                                                )
                                            detail_rr = str(rr.get("detail") or "")
                                            exhausted = maybe_exhaust_pending(
                                                email,
                                                reason=detail_rr or "re_register_pending_sso",
                                                password=str(password or ""),
                                                mail_token=str(item.get("mail_token") or ""),
                                                log=wlog,
                                            )
                                            if exhausted:
                                                wlog(
                                                    f"[pending-sso] email exhausted after re-register pending_sso "
                                                    f"email={email} detail={detail_rr}"
                                                )
                                            else:
                                                try:
                                                    rotate_pending_sso_account_to_end(email, log=wlog)
                                                except Exception:
                                                    pass
                                                try:
                                                    compact_pending_sso_file(log=wlog)
                                                except Exception:
                                                    pass
                                                wlog(
                                                    f"[pending-sso] re-register pending_sso detail={detail_rr} "
                                                    f"email={rr_email or email} "
                                                    f"attempts={get_pending_attempt(email)}/{MAX_PENDING_ATTEMPTS} kept"
                                                )
                                        except Exception as pend_adj:
                                            wlog(f"[pending-sso] pending adjust fail: {pend_adj}")
                                    elif rr_status == STATUS_STOPPED:
                                        wlog("[pending-sso] re-register stopped; pending kept")
                                        break
                            except Exception as reg_exc:
                                wlog(f"[pending-sso] re-register exception: {reg_exc}")
                                try:
                                    import traceback as _tb
                                    wlog(_tb.format_exc())
                                except Exception:
                                    pass
                except Exception as exc:
                    coord.record_fail()
                    wlog(f"[pending-sso] exception email={email}: {exc}")
                coord.log_stats()
                engine.sleep_with_cancel(1, controller.should_stop)
        finally:
            try:
                engine.stop_browser(log_callback=wlog)
            except Exception:
                pass
            clear_worker_proxy(engine, log=wlog)
            coord.worker_leave()

    threads = []
    for i in range(wn):
        if not buckets[i]:
            continue
        t = threading.Thread(
            target=_worker, args=(i + 1, buckets[i]), name=f"pending-w{i+1}", daemon=True
        )
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    snap = coord.snapshot()
    try:
        if controller.should_stop():
            engine.force_stop_registration(log_callback=log, reason="pending_mt_stopped")
        else:
            engine.stop_browser(log_callback=log)
    except Exception:
        pass
    try:
        engine.wait_post_success_queue(timeout=15 if controller.should_stop() else 45, log_callback=log)
    except Exception:
        pass
    log(f"[*] pending_sso 恢复结束。成功 {snap['success']} | 失败 {snap['fail']} | workers={wn}")
    return {
        "success": snap["success"],
        "fail": snap["fail"],
        "pending_sso": 0,
        "skipped": snap["skipped"],
        "pool_empty": False,
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
        "job": "pending_sso_recovery",
        "workers": wn,
    }

