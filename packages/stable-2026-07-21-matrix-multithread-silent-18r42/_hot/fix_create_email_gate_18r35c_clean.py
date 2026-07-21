# -*- coding: utf-8 -*-
"""18r35c clean patch: CreateEmail gate + MT/serial rate-limit switch."""
from pathlib import Path
import ast
import re
import shutil
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
p = ROOT / "grok_register_ttk.py"
t = p.read_text(encoding="utf-8")
orig = t

# --- 1 insert gate helpers before detect_page_create_email_rate_limit ---
needle = "def detect_page_create_email_rate_limit(page=None, log_callback=None) -> tuple[bool, str]:"
if "_CREATE_EMAIL_GATE" not in t:
    insert = '''# 18r35c: serialize CreateEmail across workers to cut IP-level rate limit
import threading as _rl_threading
_CREATE_EMAIL_GATE = _rl_threading.Lock()
_CREATE_EMAIL_LAST_TS = 0.0
_CREATE_EMAIL_MIN_GAP_SEC = 2.8


def _wait_create_email_gate(log_callback=None):
    """Stagger CreateEmail submissions so many workers do not fire at once."""
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


'''
    if needle not in t:
        raise SystemExit("detect fn missing")
    t = t.replace(needle, insert + needle, 1)

# --- 2 call gate immediately before run_js click that submits email ---
# Place right before: clicked = page.run_js(  inside fill_email (first occurrence after def)
fn = t.find("def fill_email_and_submit")
if fn < 0:
    raise SystemExit("fill_email missing")
# find the submit run_js - look for "submitButton.click" nearby and back to assignment
sub = t.find("submitButton.click()", fn)
if sub < 0:
    raise SystemExit("submitButton.click missing")
# find `clicked = page.run_js` or similar before sub
assign = t.rfind("clicked = ", fn, sub)
if assign < 0:
    assign = t.rfind("page.run_js(", fn, sub)
if assign < 0:
    raise SystemExit("clicked assign missing")
line_start = t.rfind("\n", 0, assign) + 1
indent = re.match(r"[ \t]*", t[line_start:assign]).group(0)
gate_line = f"{indent}_wait_create_email_gate(log_callback)  # 18r35c_gate_call\n"
# avoid double
if "18r35c_gate_call" not in t[fn:fn+25000]:
    t = t[:line_start] + gate_line + t[line_start:]

# --- 3 MT wrap fill_email ---
key = "def _register_one_browser(wlog):"
pos = t.find(key)
if pos < 0:
    raise SystemExit("MT fn missing")
# unique call pattern after MT fn
pat = re.compile(
    r"(?P<indent>[ \t]*)email, dev_token = fill_email_and_submit\(\n"
    r"(?P=indent)    log_callback=wlog, cancel_callback=controller\.should_stop\n"
    r"(?P=indent)\)\n",
    re.M,
)
m = pat.search(t, pos)
if not m:
    # looser
    pat2 = re.compile(
        r"(?P<indent>[ \t]*)email, dev_token = fill_email_and_submit\(\s*\n"
        r"[ \t]*log_callback=wlog,\s*cancel_callback=controller\.should_stop\s*\n"
        r"[ \t]*\)\s*\n",
        re.M,
    )
    m = pat2.search(t, pos)
if not m:
    raise SystemExit("MT fill_email pattern missing")
ind = m.group("indent")
wrapped = f'''{ind}try:
{ind}    email, dev_token = fill_email_and_submit(
{ind}        log_callback=wlog, cancel_callback=controller.should_stop
{ind}    )
{ind}except Exception as fill_exc:
{ind}    # 18r35c: rate-limit raised from fill_email (outside fill_code try)
{ind}    fmsg = str(fill_exc)
{ind}    _rl = any(
{ind}        k in fmsg
{ind}        for k in (
{ind}            "create_email_rate_limited",
{ind}            "RATE_LIMITED",
{ind}            "验证码过多",
{ind}            "too many verification",
{ind}            "too many codes",
{ind}        )
{ind}    )
{ind}    if _rl:
{ind}        _em = str(email or "")
{ind}        try:
{ind}            import re as _re_rl
{ind}            _m = _re_rl.search(r"email=([^\\s]+)", fmsg)
{ind}            if _m:
{ind}                _em = _m.group(1).strip()
{ind}        except Exception:
{ind}            pass
{ind}        if _em:
{ind}            try:
{ind}                from hybrid_register import handle_create_email_rate_limited
{ind}                handle_create_email_rate_limited(
{ind}                    _em,
{ind}                    "",
{ind}                    log=wlog,
{ind}                    source="browser_mt_fill_email",
{ind}                    evidence=fmsg[:300],
{ind}                    mail_token=str(dev_token or ""),
{ind}                )
{ind}            except Exception as _rl_exc:
{ind}                try:
{ind}                    from hybrid_register import remove_mailbox_from_pool
{ind}                    remove_mailbox_from_pool(
{ind}                        _em, reason="create_email_rate_limited", log=wlog
{ind}                    )
{ind}                except Exception:
{ind}                    wlog(f"[!] rate-limit cleanup fail: {{_rl_exc}}")
{ind}        wlog(
{ind}            f"[!] CreateEmail rate-limit -> switch mailbox "
{ind}            f"try={{mail_try}}/{{max_mail_retry}} email={{_em}}"
{ind}        )
{ind}        if mail_try >= max_mail_retry:
{ind}            raise Exception(
{ind}                f"create_email_rate_limited exhausted email={{_em}} {{fmsg}}"
{ind}            )
{ind}        try:
{ind}            restart_browser(log_callback=wlog)
{ind}        except Exception:
{ind}            pass
{ind}        try:
{ind}            sleep_with_cancel(1.5, controller.should_stop)
{ind}        except Exception:
{ind}            time.sleep(1.5)
{ind}        continue
{ind}    raise
'''
if "browser_mt_fill_email" not in t:
    t = t[: m.start()] + wrapped + t[m.end() :]

# --- 4 expand MT code-stage mail_fail keywords (first after MT wrap) ---
# find after browser_mt_fill_email block
pos2 = t.find("browser_mt_fill_email")
old = '''                _mail_fail = any(
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
new = '''                _rl2 = any(
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
if "browser_mt_fill_code" not in t and old in t[pos2:]:
    t = t[:pos2] + t[pos2:].replace(old, new, 1)

# --- 5 serial class path wrap ---
serial_pat = re.compile(
    r'(?P<indent>[ \t]*)self\.log\("\[\*\] 2\. 创建邮箱并提交"\)\n'
    r"(?P=indent)email, dev_token = fill_email_and_submit\(\n"
    r"(?P=indent)    log_callback=self\.log, cancel_callback=self\.should_stop\n"
    r"(?P=indent)\)\n",
)
sm = serial_pat.search(t)
if sm and "browser_serial_fill_email" not in t:
    ind = sm.group("indent")
    s_wrapped = f'''{ind}self.log("[*] 2. 创建邮箱并提交")
{ind}try:
{ind}    email, dev_token = fill_email_and_submit(
{ind}        log_callback=self.log, cancel_callback=self.should_stop
{ind}    )
{ind}except Exception as fill_exc:
{ind}    # 18r35c serial: rate-limit on fill_email -> burn+retry other mailbox
{ind}    fmsg = str(fill_exc)
{ind}    if any(
{ind}        k in fmsg
{ind}        for k in ("create_email_rate_limited", "RATE_LIMITED", "验证码过多")
{ind}    ):
{ind}        _em = str(email or "")
{ind}        try:
{ind}            import re as _re_rl
{ind}            _m = _re_rl.search(r"email=([^\\s]+)", fmsg)
{ind}            if _m:
{ind}                _em = _m.group(1).strip()
{ind}        except Exception:
{ind}            pass
{ind}        if _em:
{ind}            try:
{ind}                from hybrid_register import handle_create_email_rate_limited
{ind}                handle_create_email_rate_limited(
{ind}                    _em,
{ind}                    "",
{ind}                    log=self.log,
{ind}                    source="browser_serial_fill_email",
{ind}                    evidence=fmsg[:300],
{ind}                    mail_token=str(dev_token or ""),
{ind}                )
{ind}            except Exception as _e:
{ind}                self.log(f"[!] serial rate-limit cleanup: {{_e}}")
{ind}        self.log(
{ind}            f"[!] CreateEmail rate-limit -> switch mailbox "
{ind}            f"try={{mail_try}}/{{max_mail_retry}} email={{_em}}"
{ind}        )
{ind}        if mail_try < max_mail_retry:
{ind}            restart_browser(log_callback=self.log)
{ind}            sleep_with_cancel(1.5, self.should_stop)
{ind}            continue
{ind}    raise
'''
    t = t[: sm.start()] + s_wrapped + t[sm.end() :]

# header
if "18r35c" not in t[:1200]:
    # prepend near top after first comment block
    t = "# 18r35c: CreateEmail gate + MT/serial catch rate-limit on fill_email\n" + t

if t == orig:
    print("NO CHANGE")
else:
    p.write_text(t, encoding="utf-8")
    print("wrote", len(t) - len(orig), "delta")

ast.parse(t)
print("AST OK")
# sanity markers
for s in ["_CREATE_EMAIL_GATE", "18r35c_gate_call", "browser_mt_fill_email", "browser_serial_fill_email", "browser_mt_fill_code"]:
    print(s, s in t)

(ROOT / "CHANGELOG_18r35c_create_email_gate.md").write_text(
'''# 18r35c CreateEmail rate-limit hardfix

## Symptom
browser×socks5×outlook workers=10 hit `验证码过多` on many distinct mailboxes.
18r35b detect worked (fail-fast) but MT raised from fill_email outside fill_code try,
so no mailbox switch; slots hard-failed.

## Causes
1. Simultaneous CreateEmail from 10 workers → proxy/IP rate limit as per-email UI.
2. MT path did not catch fill_email rate-limit → no retry.
3. Limited mailboxes not always burned before next acquire.

## Fix
1. `_wait_create_email_gate` (~2.8s) serializes CreateEmail clicks globally.
2. MT/serial wrap fill_email → handle_create_email_rate_limited → switch mailbox.
3. Code-stage also burns on rate-limit keywords.

## Reload
Restart registration job (or web server) so Python reloads grok_register_ttk.
''',
encoding="utf-8",
)
print("changelog ok")
