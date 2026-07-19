from pathlib import Path

p = Path("grok_register_ttk.py")
t = p.read_text(encoding="utf-8")
old = '''def enable_nsfw_for_token(token, cf_clearance="", log_callback=None):
    proxies = get_proxies()
    user_agent = get_user_agent()
    try:
        with requests.Session(impersonate="chrome120", proxies=proxies) as session:
            cookie_parts = [f"sso={token}", f"sso-rw={token}"]
            if cf_clearance:
                cookie_parts.append(f"cf_clearance={cf_clearance}")
            session.headers.update(
                {
                    "user-agent": user_agent,
                    "cookie": "; ".join(cookie_parts),
                }
            )
            ok, message = set_tos_accepted(session, log_callback)
            if not ok:
                return False, message
            ok, message = set_birth_date(session, log_callback)
            if not ok:
                return False, message
            ok, message = update_nsfw_settings(session, log_callback)
            if not ok:
                return False, message
            return True, "成功开启 NSFW"
    except Exception as e:
        return False, f"异常: {str(e)}"'''

new = '''def enable_nsfw_for_token(token, cf_clearance="", log_callback=None):
    """Enable NSFW. Prefer current proxy; on SOCKS/proxy transport fail, retry direct."""
    user_agent = get_user_agent()
    cookie_parts = [f"sso={token}", f"sso-rw={token}"]
    if cf_clearance:
        cookie_parts.append(f"cf_clearance={cf_clearance}")
    cookie_hdr = "; ".join(cookie_parts)

    def _proxy_transport_fail(msg: str) -> bool:
        s = (msg or "").lower()
        keys = (
            "socks",
            "proxy",
            "curl: (97)",
            "curl: (7)",
            "curl: (28)",
            "cannot complete socks",
            "failed to perform",
            "connection refused",
            "tunnel",
            "proxy connect",
        )
        return any(k in s for k in keys)

    def _run(proxies, label: str):
        log = log_callback or (lambda m: None)
        log(f"[nsfw] try path={label} proxy={'yes' if proxies else 'direct'}")
        with requests.Session(impersonate="chrome120", proxies=proxies or None) as session:
            session.headers.update({"user-agent": user_agent, "cookie": cookie_hdr})
            ok, message = set_tos_accepted(session, log_callback)
            if not ok:
                return False, message
            ok, message = set_birth_date(session, log_callback)
            if not ok:
                return False, message
            ok, message = update_nsfw_settings(session, log_callback)
            if not ok:
                return False, message
            return True, f"成功开启 NSFW ({label})"

    try:
        proxies = get_proxies() or None
    except Exception:
        proxies = None
    attempts = []
    if proxies:
        attempts.append((proxies, "proxy"))
    attempts.append((None, "direct"))
    last_msg = ""
    seen = set()
    for proxies, label in attempts:
        if label in seen:
            continue
        seen.add(label)
        try:
            ok, message = _run(proxies, label)
            if ok:
                return True, message
            last_msg = message
            if label == "proxy":
                if log_callback:
                    log_callback(f"[nsfw] proxy path failed, fallback direct: {message}")
                continue
            return False, message
        except Exception as e:
            last_msg = str(e)
            if log_callback:
                log_callback(f"[nsfw] path={label} exception: {e}")
            if label == "proxy":
                continue
            return False, f"异常: {e}"
    return False, last_msg or "NSFW 开启失败"'''

if old not in t:
    raise SystemExit("OLD BLOCK NOT FOUND")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("patched enable_nsfw_for_token")

hp = Path("hybrid_register.py")
ht = hp.read_text(encoding="utf-8")
mark = "2026-07-19r25: NSFW socks fail -> direct fallback; Outlook early_no_new 110s"
if mark not in ht:
    lines = ht.splitlines(True)
    inserted = False
    for i, l in enumerate(lines[:50]):
        if "2026-07-19" in l:
            lines.insert(i, f"- {mark}\n")
            inserted = True
            break
    if not inserted:
        lines.insert(0, f"# {mark}\n")
    hp.write_text("".join(lines), encoding="utf-8")
    print("stamped hybrid header")

op = Path("outlook_mail.py")
ot = op.read_text(encoding="utf-8")
ot2 = ot.replace("early_no_new_s = 75.0", "early_no_new_s = 110.0", 1)
if ot2 == ot:
    print("outlook threshold already or missing")
else:
    op.write_text(ot2, encoding="utf-8")
    print("outlook early_no_new_s=110")

# hot-reload note: server reloads hybrid on register; outlook_mail needs importlib in hybrid use path
print("ok")
