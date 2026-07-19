from pathlib import Path
import py_compile
p = Path("hybrid_register.py")
t = p.read_text(encoding="utf-8")
old = "                    email, mail_token = get_email_and_token()\n"
new = "                    email, mail_token = get_email_and_token(log_callback=log)\n"
if old not in t:
    # already patched?
    if "get_email_and_token(log_callback=log)" in t:
        print("already patched")
    else:
        raise SystemExit("pattern missing")
else:
    t = t.replace(old, new, 1)
    # also note in changelog
    if "get_email_and_token(log_callback=log)" in t and "18r24c:" not in t:
        t = t.replace(
            "- 2026-07-19r24b:",
            "- 2026-07-19r24c: hybrid get_email_and_token 传入 log_callback，避免 Outlook acquire/preflight 静默卡住无日志。\n- 2026-07-19r24b:",
            1,
        )
    p.write_text(t, encoding="utf-8")
    print("patched get_email log_callback")
py_compile.compile(str(p), doraise=True)
print("ok")
