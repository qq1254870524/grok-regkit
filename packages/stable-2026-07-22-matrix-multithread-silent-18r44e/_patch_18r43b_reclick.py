from pathlib import Path
p = Path("hybrid_register.py")
text = p.read_text(encoding="utf-8")
old = '''                        ui_code_now = bool(st.get("ui_has_code") or st.get("ui_body_code"))

                        raw_sent = bool(st.get("sent")) and reason not in {

                            "seen_status_unknown",

                            "not_seen",

                            "no_data",

                        }

                        browser_sent = bool(

                            raw_sent

                            and ((actual_send >= 1) or (net_hits_n >= 1) or ui_code_now)

                        )
'''
new = '''                        ui_code_now = bool(st.get("ui_has_code") or st.get("ui_body_code"))
                        status_n2 = int(st.get("status") or 0)
                        strong_http2 = 200 <= status_n2 < 300
                        weak2 = {
                            "seen_status_unknown",
                            "not_seen",
                            "no_data",
                            "pending",
                            "inflight",
                            "maybe_inflight",
                            "status_unknown",
                        }
                        raw_sent = bool(st.get("sent")) and reason not in weak2
                        # 18r43b: re-click confirm needs ui_code or strong non-weak send
                        browser_sent = bool(
                            ui_code_now
                            or (
                                reason not in weak2
                                and strong_http2
                                and (raw_sent or actual_send >= 1 or bool(st.get("ok")))
                            )
                        )
'''
if old not in text:
    # try compacted form without blank lines between
    import re
    m = re.search(r"ui_code_now = bool\(st\.get\(\"ui_has_code\"\).*?and \(\(actual_send >= 1\) or \(net_hits_n >= 1\) or ui_code_now\)\s*\)", text, re.S)
    if not m:
        raise SystemExit("re-click block not found")
    print("FOUND compact", m.start(), m.end())
    text = text[:m.start()] + new.strip() + "\n" + text[m.end():]
else:
    text = text.replace(old, new, 1)
    print("FOUND spaced")

# dual_send_lock on re-click confirm
old2 = '''                        if browser_sent:

                            confirmed_send = True

                            dual_send_lock = True

                            network_fired = True

                            log(f"[hybrid] CreateEmail re-click confirmed dual_send_lock=1 actual={actual_send}")
'''
new2 = '''                        if browser_sent:
                            confirmed_send = True
                            # 18r43b: dual lock only for ui_code or strong HTTP success
                            dual_send_lock = bool(
                                ui_code_now
                                or (
                                    strong_http2
                                    and reason not in weak2
                                    and (actual_send >= 1 or raw_sent or bool(st.get("ok")))
                                )
                            )
                            network_fired = True
                            log(
                                f"[hybrid] CreateEmail re-click confirmed "
                                f"dual_send_lock={int(dual_send_lock)} actual={actual_send} "
                                f"status={status_n2} reason={reason}"
                            )
'''
if old2 in text:
    text = text.replace(old2, new2, 1)
    print("RECLICK_LOCK_PATCHED")
else:
    m2 = text.find("CreateEmail re-click confirmed dual_send_lock=1")
    print("reclick log idx", m2)
    if m2 < 0:
        raise SystemExit("reclick dual lock not found")

p.write_text(text, encoding="utf-8")
import py_compile
py_compile.compile("hybrid_register.py", doraise=True)
print("COMPILE_OK")
