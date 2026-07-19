from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
t = p.read_text(encoding="utf-8")
# add first_pure_signin_at init
a = "    last_signin_nudge_at = 0.0\n    signin_nudge_count = 0\n"
b = "    last_signin_nudge_at = 0.0\n    signin_nudge_count = 0\n    first_pure_signin_at = None\n"
if "first_pure_signin_at" not in t:
    if a not in t:
        raise SystemExit('init anchor missing')
    t = t.replace(a, b, 1)
# fix dwell logic block
old = '''                        # first pure-signing-in: dwell >= 18s before navigating away
                        dwell_ok = True
                        if signin_nudge_count == 0 and info.get("pureSigningIn") and not info.get("hasLast"):
                            # use final_no_submit_since as dwell anchor when available
                            anchor = final_no_submit_since or (now2 - 0.0)
                            if final_no_submit_since and (now2 - final_no_submit_since) < 18:
                                dwell_ok = False
                                if log_callback:
                                    log_callback(
                                        f"[*] SSO pure signing-in dwell {(now2 - final_no_submit_since):.1f}s/18s "
                                        f"url={info.get('url')}"
                                    )
                                last_signin_nudge_at = now2
                        if dwell_ok:
'''
new = '''                        # first pure-signing-in: dwell >= 18s before navigating away
                        dwell_ok = True
                        if signin_nudge_count == 0 and info.get("pureSigningIn") and not info.get("hasLast"):
                            if first_pure_signin_at is None:
                                first_pure_signin_at = now2
                            stayed = now2 - float(first_pure_signin_at)
                            if stayed < 18.0:
                                dwell_ok = False
                                if log_callback:
                                    log_callback(
                                        f"[*] SSO pure signing-in dwell {stayed:.1f}s/18s "
                                        f"url={info.get('url')}"
                                    )
                                last_signin_nudge_at = now2
                        if dwell_ok:
'''
if old not in t:
    raise SystemExit('dwell block missing')
t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
print('dwell anchor ok')
# syntax check
import py_compile
py_compile.compile(str(p), doraise=True)
print('syntax ok')
