from pathlib import Path
p = Path("browser/token_harvester.py")
text = p.read_text(encoding="utf-8")
old = '''            # 18r8: any real CreateEmail evidence freezes further clicks (prevent dual-code).
            actual_n = int(st.get("actual_send_count") or 0)
            # 18r16: any real CreateEmail request already fired → freeze (防双发/验证码过多)
            hard_no_reclick = bool(
                st.get("sent")
                or actual_n >= 1
                or net_hits >= 1
                or (code_step and (st.get("seen") or net_hits >= 1 or bool(st.get("ok"))))
                or bool(st.get("ui_rate_limited"))
            )
            if st.get("ui_rate_limited"):
                self._lg(
                    f"[!] CreateEmail UI rate-limited body={st.get('ui_body_text')!r} "
                    f"email={email} actual_send={actual_n} net_hits={net_hits}"
                )
            if hard_no_reclick:
                self._lg(
                    f"[*] CreateEmail freeze-reclick reason={st.get('reason')} "
                    f"status={status_n} seen={st.get('seen')} net_hits={net_hits} "
                    f"raw={st.get('net_hits_raw')} actual_send={st.get('actual_send_count')} "
                    f"blocked_dup={st.get('blocked_duplicate_count')} "
                    f"sent={int(bool(st.get('sent')))} "
                    f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')} "
                    f"castle_len={st.get('castle_len') or (len(c) if c else 0)}"
                )
                if c:
                    self._lg(f"[*] native castle len={len(c)} head={c[:20]}")
                    return c
                time.sleep(0.45)
                continue
'''
new = '''            # 18r8/18r43b: freeze further clicks when CreateEmail already fired (防双发).
            actual_n = int(st.get("actual_send_count") or 0)
            reason_s = str(st.get("reason") or "")
            weak_reason = reason_s in {
                "seen_status_unknown",
                "not_seen",
                "no_data",
                "pending",
                "inflight",
                "maybe_inflight",
                "status_unknown",
            }
            strong_http = 200 <= status_n < 300
            # 18r43b: hard freeze on real send evidence; weak net_hits alone is soft-wait
            hard_no_reclick = bool(
                bool(st.get("ui_rate_limited"))
                or code_step
                or (bool(st.get("sent")) and (strong_http or actual_n >= 1 or bool(st.get("ok"))))
                or (strong_http and (actual_n >= 1 or bool(st.get("ok"))))
                or (actual_n >= 1 and strong_http and not weak_reason)
                or (net_hits >= 1 and strong_http and not weak_reason)
            )
            soft_no_reclick = bool(
                (not hard_no_reclick)
                and (net_hits >= 1 or actual_n >= 1)
            )
            if st.get("ui_rate_limited"):
                self._lg(
                    f"[!] CreateEmail UI rate-limited body={st.get('ui_body_text')!r} "
                    f"email={email} actual_send={actual_n} net_hits={net_hits}"
                )
            if hard_no_reclick or soft_no_reclick:
                # 18r43b: throttle freeze logs (was every 0.45s spam on seen_status_unknown)
                now_ts = time.time()
                last_fr = float(getattr(self, "_last_freeze_reclick_log_ts", 0.0) or 0.0)
                if (now_ts - last_fr) >= 4.0:
                    self._last_freeze_reclick_log_ts = now_ts
                    self._lg(
                        f"[*] CreateEmail freeze-reclick reason={reason_s} "
                        f"mode={'hard' if hard_no_reclick else 'soft'} "
                        f"status={status_n} seen={st.get('seen')} net_hits={net_hits} "
                        f"raw={st.get('net_hits_raw')} actual_send={st.get('actual_send_count')} "
                        f"blocked_dup={st.get('blocked_duplicate_count')} "
                        f"sent={int(bool(st.get('sent')))} "
                        f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')} "
                        f"castle_len={st.get('castle_len') or (len(c) if c else 0)}"
                    )
                if c:
                    self._lg(f"[*] native castle len={len(c)} head={c[:20]}")
                    return c
                # soft weak fire: wait briefly for castle/2xx then yield to hybrid protocol-rescue
                if soft_no_reclick and first_seen_ts and (time.time() - first_seen_ts >= 12.0):
                    self._lg(
                        f"[*] CreateEmail soft freeze timeout reason={reason_s} "
                        f"net_hits={net_hits} actual={actual_n} — return without extra click"
                    )
                    return c or ""
                time.sleep(0.45)
                continue
'''
if old not in text:
    raise SystemExit("OLD_BLOCK_NOT_FOUND")
text = text.replace(old, new, 1)
# header note
if "18r43b" not in text[:800]:
    text = text.replace(
        "2026-07-20r37: actual_send backfill from net_hits only on 2xx; weak status_unknown no dual-send inflation.\n",
        "2026-07-20r37: actual_send backfill from net_hits only on 2xx; weak status_unknown no dual-send inflation.\n"
        "2026-07-21r43b: freeze-reclick throttle 4s; hard freeze needs 2xx/ui_code/ok; soft net_hits wait then yield.\n",
        1,
    )
p.write_text(text, encoding="utf-8")
import py_compile
py_compile.compile(str(p), doraise=True)
print("TOKEN_HARVESTER_PATCHED_OK")
