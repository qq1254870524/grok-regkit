from pathlib import Path
p = Path("hybrid_register.py")
text = p.read_text(encoding="utf-8")
marker = "            # Accept browser_sent only with strong evidence (2xx / ok / code-step)"
idx = text.find(marker)
if idx < 0:
    raise SystemExit("marker not found")
# find end of wait-confirm block (ui rate-limit section)
end_marker = "            # 18r16: detect rate-limit message on page even when HTTP status looks 200"
end = text.find(end_marker, idx)
if end < 0:
    raise SystemExit("end marker not found")
new_block = r'''            # Accept browser_sent only with strong evidence (2xx / ok / code-step)
            # PLUS real send evidence. 18r37/18r43b: NEVER promote from weak status_unknown.
            # net_hits alone under seen_status_unknown is NOT dual-send lock / browser_sent.
            # 18r43b: dual_send_lock requires ui_code OR (2xx + non-weak reason + real send/ok).
            # Fake actual_send=1/net_hits=1 under unknown must NOT block protocol-rescue.
            reason = str(st.get("reason") or "")
            status_n = int(st.get("status") or 0)
            actual_send_hook = int(st.get("actual_send_count") or 0)
            net_hits_n = int(st.get("net_hits") or 0)
            ui_code_now = bool(st.get("ui_has_code") or st.get("ui_body_code"))
            weak_reasons = {
                "seen_status_unknown",
                "not_seen",
                "no_data",
                "pending",
                "inflight",
                "maybe_inflight",
                "status_unknown",
            }
            strong_http = 200 <= status_n < 300
            # 18r37: only backfill actual_send from net_hits when response is strong
            actual_send = actual_send_hook
            if actual_send <= 0 and net_hits_n > 0 and strong_http and reason not in weak_reasons:
                actual_send = net_hits_n
                st["actual_send_count"] = actual_send
            raw_sent = bool(st.get("sent")) and reason not in weak_reasons
            # Confirmed browser send: real success signals only
            confirmed_send = bool(
                ui_code_now
                or (
                    reason not in weak_reasons
                    and (
                        (raw_sent and (strong_http or actual_send >= 1))
                        or (strong_http and (actual_send >= 1 or bool(st.get("ok"))))
                    )
                )
            )
            network_fired = (net_hits_n >= 1) or (actual_send_hook >= 1) or (actual_send >= 1)
            # dual-send lock only when UI is on code step OR strong non-weak HTTP success
            dual_send_lock = bool(
                ui_code_now
                or (
                    confirmed_send
                    and strong_http
                    and reason not in weak_reasons
                    and (actual_send >= 1 or bool(st.get("ok")) or raw_sent)
                )
            )
            has_send_evidence = confirmed_send
            browser_sent = bool(confirmed_send)
            # 18r37: weak unknown + net hit -> short re-poll for 2xx/ui_code before deciding
            if (not browser_sent) and network_fired and reason in weak_reasons:
                log(
                    f"[hybrid] CreateEmail weak evidence wait-confirm "
                    f"reason={reason} status={status_n} net_hits={net_hits_n} "
                    f"actual_hook={actual_send_hook} (18r43b no promote without ui/2xx+ok)"
                )
                for _wc in range(8):
                    if stop():
                        return _result(STATUS_STOPPED)
                    time.sleep(1.5)
                    st2 = browser.create_email_status_via_browser()
                    reason2 = str(st2.get("reason") or "")
                    status2 = int(st2.get("status") or 0)
                    net2 = int(st2.get("net_hits") or 0)
                    act2 = int(st2.get("actual_send_count") or 0)
                    ui2 = bool(st2.get("ui_has_code") or st2.get("ui_body_code"))
                    strong2 = 200 <= status2 < 300
                    raw2 = bool(st2.get("sent")) and reason2 not in weak_reasons
                    ok2 = bool(st2.get("ok"))
                    # 18r43b: do not promote on bare 2xx without ok/send/ui_code
                    promote2 = bool(
                        ui2
                        or (
                            reason2 not in weak_reasons
                            and strong2
                            and (act2 >= 1 or raw2 or ok2)
                        )
                    )
                    if promote2:
                        st = st2
                        reason = reason2
                        status_n = status2
                        net_hits_n = net2
                        actual_send_hook = act2
                        actual_send = act2 if act2 > 0 else (net2 if strong2 and ok2 else 0)
                        ui_code_now = ui2
                        strong_http = strong2
                        raw_sent = raw2
                        confirmed_send = True
                        dual_send_lock = bool(
                            ui2
                            or (
                                strong2
                                and reason2 not in weak_reasons
                                and (act2 >= 1 or raw2 or ok2)
                            )
                        )
                        browser_sent = True
                        has_send_evidence = True
                        log(
                            f"[hybrid] CreateEmail wait-confirm OK "
                            f"status={status2} reason={reason2} ui_code={ui2} "
                            f"actual={actual_send} net_hits={net2} dual_lock={int(dual_send_lock)}"
                        )
                        break
                else:
                    log(
                        f"[hybrid] CreateEmail wait-confirm timeout "
                        f"reason={reason} status={status_n} net_hits={net_hits_n} "
                        f"— keep browser_sent=0 dual_send_lock=0 allow protocol-rescue path"
                    )

'''
text = text[:idx] + new_block + text[end:]
if "18r43b:" not in text[:500]:
    text = text.replace(
        "# 18r43a: non-session/mail_token never counts success or pool-import; burn pending_sso\n",
        "# 18r43b: dual_send_lock requires ui_code or 2xx+non-weak+ok/send; weak net_hits never block rescue\n# 18r43a: non-session/mail_token never counts success or pool-import; burn pending_sso\n",
        1,
    )
if "2026-07-21r43b" not in text:
    text = text.replace(
        "Changelog:\n- 2026-07-20r37:",
        "Changelog:\n- 2026-07-21r43b: dual_send_lock 仅 ui_code 或 2xx+非弱reason+ok/send；wait-confirm 不再因裸 2xx/假 actual_send 锁死 protocol-rescue；减少 early_no_new_mail 空烧。\n- 2026-07-20r37:",
        1,
    )
p.write_text(text, encoding="utf-8")
print("PATCHED", idx, end)
# syntax check
import py_compile
py_compile.compile("hybrid_register.py", doraise=True)
print("COMPILE_OK")
