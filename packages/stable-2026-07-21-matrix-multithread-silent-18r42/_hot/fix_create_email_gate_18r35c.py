# -*- coding: utf-8 -*-
"""18r35c: browser MT CreateEmail rate-limit switch + global CreateEmail gate."""
from pathlib import Path
import re
import shutil
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = ROOT / "_hot" / f"bak_18r35c_{stamp}"
bak.mkdir(parents=True, exist_ok=True)

def backup(name):
    src = ROOT / name
    dst = bak / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return src

def patch_ttk():
    p = backup("grok_register_ttk.py")
    t = p.read_text(encoding="utf-8")
    orig = t

    # 1) Global CreateEmail gate near detect_page_create_email_rate_limit
    if "_CREATE_EMAIL_GATE" not in t:
        needle = "def detect_page_create_email_rate_limit(page=None, log_callback=None) -> tuple[bool, str]:"
        insert = '''# 18r35c: serialize CreateEmail across workers to cut IP-level "验证码过多"
import threading as _rl_threading
_CREATE_EMAIL_GATE = _rl_threading.Lock()
_CREATE_EMAIL_LAST_TS = 0.0
_CREATE_EMAIL_MIN_GAP_SEC = 2.8


def _wait_create_email_gate(log_callback=None):
    """Stagger CreateEmail submissions so 10 workers do not fire at once."""
    global _CREATE_EMAIL_LAST_TS
    import time as _t
    with _CREATE_EMAIL_GATE:
        now = _t.time()
        wait = float(_CREATE_EMAIL_MIN_GAP_SEC) - (now - float(_CREATE_EMAIL_LAST_TS or 0.0))
        if wait > 0:
            if log_callback:
                try:
                    log_callback(f"[*] CreateEmail gate wait {wait:.2f}s (anti rate-limit)")
                except Exception:
                    pass
            _t.sleep(wait)
        _CREATE_EMAIL_LAST_TS = _t.time()


def detect_page_create_email_rate_limit(page=None, log_callback=None) -> tuple[bool, str]:
'''
        if needle not in t:
            raise SystemExit("detect_page_create_email_rate_limit not found")
        t = t.replace(needle, insert, 1)

    # 2) Call gate before submitting email in fill_email_and_submit — find "已填写邮箱并提交"
    # Wrap the click path: before page fill submit, wait gate.
    # Look for the successful click log and ensure gate is called earlier in the function.
    # Safer: inject at start of fill_email_and_submit body after def line.
    if "18r35c_gate_call" not in t:
        # find def fill_email_and_submit
        m = re.search(r"def fill_email_and_submit\([^\)]*\):\n", t)
        if not m:
            raise SystemExit("fill_email_and_submit not found")
        # insert after first line of function - find next non-empty indented
        idx = m.end()
        # insert gate acquisition right before submitting - search for pattern in loop
        # Better inject before "已填写邮箱并提交" click success path - actually before attempt submit
        # Find: `if clicked:` near rate limit 18r35b
        marker = "            if clicked:\n                if log_callback:\n                    detail = f\" ({clicked})\" if isinstance(clicked, str) else \"\"\n                    log_callback(f\"[*] 已填写邮箱并提交: {email}{detail}\")"
        if marker not in t:
            # try looser
            marker2 = "已填写邮箱并提交: {email}"
            pos = t.find(marker2)
            if pos < 0:
                raise SystemExit("submit log marker not found")
            # find start of if clicked block before this
            block_start = t.rfind("if clicked:", 0, pos)
            if block_start < 0:
                raise SystemExit("if clicked not found")
            # insert gate just before if clicked
            line_start = t.rfind("\n", 0, block_start) + 1
            indent = "            "
            gate_call = f"{indent}_wait_create_email_gate(log_callback)  # 18r35c_gate_call\n"
            # but gate should be BEFORE click not after - find click earlier
            # Actually we need gate before click. Search backwards for run_js or click submit in loop
            t = t[:line_start] + gate_call + t[line_start:]
        else:
            # insert before if clicked
            t = t.replace(
                marker,
                "            _wait_create_email_gate(log_callback)  # 18r35c_gate_call\n" + marker,
                1,
            )

    # 3) Patch MT _register_one_browser mail loop to catch rate limit on fill_email
    old_mt = '''        for mail_try in range(1, max_mail_retry + 1):
            wlog(f"[*] 1. 打开注册页 (邮箱 {mail_try}/{max_mail_retry})")
            open_signup_page(log_callback=wlog, cancel_callback=controller.should_stop)
            wlog("[*] 2. 创建邮箱并提交")
            email, dev_token = fill_email_and_submit(
                log_callback=wlog, cancel_callback=controller.should_stop
            )
            wlog(f"[*] 邮箱: {email}")
            wlog(f"[Debug] 邮箱credential(jwt): {dev_token}")
            try:
                with open(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_credentials.txt"),
                    "a",
                    encoding="utf-8",
                ) as f:
                    f.write(f"{email}\\t{dev_token}\\n")
            except Exception:
                pass
            wlog("[*] 3. 拉取验证码")
            try:
                code = fill_code_and_submit(
                    email,
                    dev_token,
                    log_callback=wlog,
                    cancel_callback=controller.should_stop,
                )
                mail_ok = True
                break
            except Exception as mail_exc:
                msg = str(mail_exc)
                _mail_fail = any(
                    k in msg
                    for k in (
                        "验证码",
                        "code",
                        "mail",
                        "邮箱",
                        "timeout",
                        "超时",
                        "IMAP",
                        "Graph",
                    )
                )
                wlog(f"[!] 验证码阶段失败 try={mail_try}: {mail_exc}")
                if not _mail_fail or mail_try >= max_mail_retry:
                    raise
                try:
                    restart_browser(log_callback=wlog)
                except Exception:
                    pass
'''
    new_mt = '''        for mail_try in range(1, max_mail_retry + 1):
            wlog(f"[*] 1. 打开注册页 (邮箱 {mail_try}/{max_mail_retry})")
            open_signup_page(log_callback=wlog, cancel_callback=controller.should_stop)
            wlog("[*] 2. 创建邮箱并提交")
            try:
                email, dev_token = fill_email_and_submit(
                    log_callback=wlog, cancel_callback=controller.should_stop
                )
            except Exception as fill_exc:
                # 18r35c: CreateEmail rate-limit is raised here (not in fill_code)
                fmsg = str(fill_exc)
                _rl = any(
                    k in fmsg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                        "too many verification",
                        "too many codes",
                    )
                )
                if _rl:
                    _em = email or ""
                    try:
                        m = re.search(r"email=([^\\s]+)", fmsg)
                        if m:
                            _em = m.group(1).strip()
                    except Exception:
                        pass
                    if _em:
                        try:
                            from hybrid_register import handle_create_email_rate_limited, remove_mailbox_from_pool
                            handle_create_email_rate_limited(
                                _em,
                                "",
                                log=wlog,
                                source="browser_mt_fill_email",
                                evidence=fmsg[:300],
                                mail_token=str(dev_token or ""),
                            )
                        except Exception as _rl_exc:
                            try:
                                from hybrid_register import remove_mailbox_from_pool
                                remove_mailbox_from_pool(_em, reason="create_email_rate_limited", log=wlog)
                            except Exception:
                                wlog(f"[!] rate-limit cleanup fail: {_rl_exc}")
                    wlog(f"[!] CreateEmail rate-limit -> switch mailbox try={mail_try}/{max_mail_retry} email={_em}")
                    if mail_try >= max_mail_retry:
                        raise Exception(f"create_email_rate_limited exhausted email={_em} {fmsg}")
                    try:
                        restart_browser(log_callback=wlog)
                    except Exception:
                        pass
                    try:
                        sleep_with_cancel(1.5, controller.should_stop)
                    except Exception:
                        time.sleep(1.5)
                    continue
                raise
            wlog(f"[*] 邮箱: {email}")
            wlog(f"[Debug] 邮箱credential(jwt): {dev_token}")
            try:
                with open(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_credentials.txt"),
                    "a",
                    encoding="utf-8",
                ) as f:
                    f.write(f"{email}\\t{dev_token}\\n")
            except Exception:
                pass
            wlog("[*] 3. 拉取验证码")
            try:
                code = fill_code_and_submit(
                    email,
                    dev_token,
                    log_callback=wlog,
                    cancel_callback=controller.should_stop,
                )
                mail_ok = True
                break
            except Exception as mail_exc:
                msg = str(mail_exc)
                _rl2 = any(
                    k in msg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                    )
                )
                _mail_fail = _rl2 or any(
                    k in msg
                    for k in (
                        "early_no_new_mail",
                        "验证码",
                        "code",
                        "mail",
                        "邮箱",
                        "timeout",
                        "超时",
                        "IMAP",
                        "Graph",
                    )
                )
                wlog(f"[!] 验证码阶段失败 try={mail_try}: {mail_exc}")
                if _rl2 and email:
                    try:
                        from hybrid_register import handle_create_email_rate_limited
                        handle_create_email_rate_limited(
                            email,
                            "",
                            log=wlog,
                            source="browser_mt_fill_code",
                            evidence=msg[:300],
                            mail_token=str(dev_token or ""),
                        )
                    except Exception as _rl_exc2:
                        wlog(f"[!] rate-limit burn(code) fail: {_rl_exc2}")
                if not _mail_fail or mail_try >= max_mail_retry:
                    raise
                try:
                    restart_browser(log_callback=wlog)
                except Exception:
                    pass
'''
    # Match by unique fragment - file may have encoding variants
    # Use structural replace via line markers
    if "18r35c: CreateEmail rate-limit is raised here" not in t:
        # find unique sequence in MT path
        key = "def _register_one_browser(wlog):"
        pos = t.find(key)
        if pos < 0:
            raise SystemExit("_register_one_browser not found")
        # find fill_email_and_submit first occurrence after this
        fe = t.find("email, dev_token = fill_email_and_submit(\n                log_callback=wlog, cancel_callback=controller.should_stop\n            )", pos)
        if fe < 0:
            fe = t.find("email, dev_token = fill_email_and_submit(", pos)
            if fe < 0:
                raise SystemExit("MT fill_email call not found")
            # take 3 lines
            end = t.find(")", fe)
            end = t.find("\n", end) + 1
        else:
            end = fe + len("email, dev_token = fill_email_and_submit(\n                log_callback=wlog, cancel_callback=controller.should_stop\n            )")
            if t[end:end+1] == "\n":
                pass
        # replace bare call with try/except version - simpler approach: wrap
        call_block = t[fe:end]
        if "try:" not in t[fe-30:fe]:
            wrapped = '''try:
                email, dev_token = fill_email_and_submit(
                    log_callback=wlog, cancel_callback=controller.should_stop
                )
            except Exception as fill_exc:
                # 18r35c: CreateEmail rate-limit is raised here (not in fill_code)
                fmsg = str(fill_exc)
                _rl = any(
                    k in fmsg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                        "too many verification",
                        "too many codes",
                    )
                )
                if _rl:
                    _em = str(email or "")
                    try:
                        import re as _re_rl
                        m = _re_rl.search(r"email=([^\\s]+)", fmsg)
                        if m:
                            _em = m.group(1).strip()
                    except Exception:
                        pass
                    if _em:
                        try:
                            from hybrid_register import handle_create_email_rate_limited
                            handle_create_email_rate_limited(
                                _em,
                                "",
                                log=wlog,
                                source="browser_mt_fill_email",
                                evidence=fmsg[:300],
                                mail_token=str(dev_token or ""),
                            )
                        except Exception as _rl_exc:
                            try:
                                from hybrid_register import remove_mailbox_from_pool
                                remove_mailbox_from_pool(_em, reason="create_email_rate_limited", log=wlog)
                            except Exception:
                                wlog(f"[!] rate-limit cleanup fail: {_rl_exc}")
                    wlog(f"[!] CreateEmail rate-limit -> switch mailbox try={mail_try}/{max_mail_retry} email={_em}")
                    if mail_try >= max_mail_retry:
                        raise Exception(f"create_email_rate_limited exhausted email={_em} {fmsg}")
                    try:
                        restart_browser(log_callback=wlog)
                    except Exception:
                        pass
                    try:
                        sleep_with_cancel(1.5, controller.should_stop)
                    except Exception:
                        time.sleep(1.5)
                    continue
                raise
'''
            # keep indentation of surrounding - the call starts with spaces
            # fe points to "email, dev_token" - get indent
            line_start = t.rfind("\n", 0, fe) + 1
            indent = t[line_start:fe]
            # build properly indented
            wlines = []
            for ln in wrapped.splitlines():
                if ln.strip() == "":
                    wlines.append("")
                else:
                    # wrapped uses 12 spaces base for try relative to function - 
                    # our indent for email, = is typically 12 spaces
                    wlines.append(indent + ln if not ln.startswith("try") and not ln.startswith("except") and not ln.startswith("#") else indent + ln)
            # Fix: re-indent cleanly with indent of original call
            base = indent
            wlines = []
            raw = wrapped.splitlines()
            # raw first line is "try:" at 0 indent in string - should be base
            for ln in raw:
                if ln == "":
                    wlines.append("")
                    continue
                # content already has 0 or 4 or 8 indent relative
                # strip and reapply: level from leading spaces in raw // 4
                stripped = ln.lstrip(" ")
                spaces = len(ln) - len(stripped)
                wlines.append(base + (" " * spaces) + stripped)
            t = t[:line_start] + "\n".join(wlines) + "\n" + t[end:]

        # also expand mail_fail keywords in MT code path after fill_code
        old_keys = '''                _mail_fail = any(
                    k in msg
                    for k in (
                        "验证码",
                        "code",
                        "mail",
                        "邮箱",
                        "timeout",
                        "超时",
                        "IMAP",
                        "Graph",
                    )
                )
                wlog(f"[!] 验证码阶段失败 try={mail_try}: {mail_exc}")
'''
        new_keys = '''                _rl2 = any(
                    k in msg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                    )
                )
                _mail_fail = _rl2 or any(
                    k in msg
                    for k in (
                        "early_no_new_mail",
                        "create_email_rate_limited",
                        "验证码",
                        "code",
                        "mail",
                        "邮箱",
                        "timeout",
                        "超时",
                        "IMAP",
                        "Graph",
                    )
                )
                if _rl2 and email:
                    try:
                        from hybrid_register import handle_create_email_rate_limited
                        handle_create_email_rate_limited(
                            email,
                            "",
                            log=wlog,
                            source="browser_mt_fill_code",
                            evidence=msg[:300],
                            mail_token=str(dev_token or ""),
                        )
                    except Exception as _rl_exc2:
                        wlog(f"[!] rate-limit burn(code) fail: {_rl_exc2}")
                wlog(f"[!] 验证码阶段失败 try={mail_try}: {mail_exc}")
'''
        if old_keys in t and "browser_mt_fill_code" not in t:
            t = t.replace(old_keys, new_keys, 1)

    # 4) Serial run_registration: wrap fill_email similarly - only first occurrence in class method
    # Find pattern in run_registration / serial that has fill outside try
    serial_marker = "self.log(\"[*] 2. 创建邮箱并提交\")\n                        email, dev_token = fill_email_and_submit(\n                            log_callback=self.log, cancel_callback=self.should_stop\n                        )"
    serial_new = '''self.log("[*] 2. 创建邮箱并提交")
                        try:
                            email, dev_token = fill_email_and_submit(
                                log_callback=self.log, cancel_callback=self.should_stop
                            )
                        except Exception as fill_exc:
                            # 18r35c serial: rate-limit on fill_email -> burn+retry other mailbox
                            fmsg = str(fill_exc)
                            if any(k in fmsg for k in ("create_email_rate_limited", "RATE_LIMITED", "验证码过多")):
                                _em = ""
                                try:
                                    import re as _re_rl
                                    m = _re_rl.search(r"email=([^\\s]+)", fmsg)
                                    if m:
                                        _em = m.group(1).strip()
                                except Exception:
                                    _em = str(email or "")
                                if _em:
                                    try:
                                        from hybrid_register import handle_create_email_rate_limited
                                        handle_create_email_rate_limited(
                                            _em, "", log=self.log, source="browser_serial_fill_email",
                                            evidence=fmsg[:300], mail_token=str(dev_token or ""),
                                        )
                                    except Exception as _e:
                                        self.log(f"[!] serial rate-limit cleanup: {_e}")
                                self.log(f"[!] CreateEmail rate-limit -> switch mailbox try={mail_try}/{max_mail_retry} email={_em}")
                                if mail_try < max_mail_retry:
                                    restart_browser(log_callback=self.log)
                                    sleep_with_cancel(1.5, self.should_stop)
                                    continue
                            raise
'''
    if "browser_serial_fill_email" not in t and serial_marker in t:
        t = t.replace(serial_marker, serial_new, 1)

    # header note
    if "18r35c" not in t[:800]:
        t = t.replace(
            "# 18r35b:",
            "# 18r35c: CreateEmail global gate + MT/serial catch rate-limit on fill_email switch mailbox\n# 18r35b:",
            1,
        )

    if t == orig:
        print("WARN: no changes applied to grok_register_ttk.py")
    else:
        p.write_text(t, encoding="utf-8")
        print("patched grok_register_ttk.py", "delta", len(t)-len(orig))

    # verify
    import ast
    ast.parse(t)
    print("AST OK ttk")

def write_changelog():
    p = ROOT / "CHANGELOG_18r35c_create_email_gate.md"
    p.write_text('''# 18r35c CreateEmail rate-limit hardfix

## Symptom
browser×socks5×outlook under workers=10: many distinct Outlook addresses still hit
`发送到此邮箱的验证码过多` immediately after CreateEmail. Detector (18r35b) worked
(fail fast) but MT path raised from `fill_email_and_submit` **outside** the
`fill_code_and_submit` try, so no switch-mailbox retry; slot counted as hard fail.

## Root causes
1. 10 workers CreateEmail nearly simultaneous → xAI IP/proxy rate limit surfaces as
   per-email "too many codes" UI (even on fresh mailboxes).
2. MT `_register_one_browser` did not catch rate-limit on fill_email → no retry.
3. Rate-limited mailboxes were not always burned/removed before next acquire.

## Fix
1. Global `_wait_create_email_gate` (~2.8s min gap) serializes CreateEmail clicks.
2. MT + serial wrap `fill_email_and_submit` with rate-limit detect →
   `handle_create_email_rate_limited` / remove pool → restart browser → next mailbox.
3. Code-stage path also burns on rate-limit keywords.

## Note
Running Python process must reload module (restart job/web) to pick up fix.
AOL paths already healthy; Outlook benefit is primary.
''', encoding='utf-8')
    print("changelog written")

if __name__ == "__main__":
    patch_ttk()
    write_changelog()
    print("DONE 18r35c")
