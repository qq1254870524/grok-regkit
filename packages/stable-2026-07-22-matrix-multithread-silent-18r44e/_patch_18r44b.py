from pathlib import Path
import py_compile

th = Path(r"C:\Users\zhang\grok-regkit\browser\token_harvester.py")
t = th.read_text(encoding="utf-8")
if "18r44b: CreateEmail body-aware" not in t:
    if t.startswith('"""'):
        end = t.find('"""', 3)
        if end > 0:
            t = t[: end + 3] + "\n# 18r44b: CreateEmail body-aware OK; never treat bare code-step as sent\n" + t[end + 3 :]
        else:
            t = "# 18r44b: CreateEmail body-aware OK; never treat bare code-step as sent\n" + t
    else:
        t = "# 18r44b: CreateEmail body-aware OK; never treat bare code-step as sent\n" + t

needle = """  window.__hybrid_create_email_actual_sends = 0;
  window.__hybrid_create_email_blocked = 0;
  window.__hybrid_create_email_lock = false;"""
repl = """  window.__hybrid_create_email_actual_sends = 0;
  window.__hybrid_create_email_blocked = 0;
  window.__hybrid_create_email_lock = false;
  window.__hybrid_create_email_body = window.__hybrid_create_email_body || '';
  window.__hybrid_create_email_body_ok = true;"""
if "create_email_body_ok" not in t:
    if needle not in t:
        raise SystemExit("init needle missing")
    t = t.replace(needle, repl, 1)

old_mark = """  function markCreateEmailResponse(url, status, ok) {
    if (!isCreateEmailUrl(url)) return;
    window.__hybrid_create_email_status = Number(status || 0);
    window.__hybrid_create_email_ok = !!ok;
    window.__hybrid_create_email_inflight = false;
    if (ok || (Number(status) >= 200 && Number(status) < 300)) {
      window.__hybrid_create_email_sent_once = true;
    }
  }"""
new_mark = """  function markCreateEmailResponse(url, status, ok, bodyText) {
    if (!isCreateEmailUrl(url)) return;
    window.__hybrid_create_email_status = Number(status || 0);
    var body = String(bodyText || '');
    window.__hybrid_create_email_body = body.slice(0, 2000);
    var low = body.toLowerCase();
    var bodyBad = false;
    if (low) {
      if (low.indexOf('too many') >= 0 || low.indexOf('rate limit') >= 0 || low.indexOf('rate_limit') >= 0) bodyBad = true;
      if (body.indexOf('\u9a8c\u8bc1\u7801\u8fc7\u591a') >= 0 || body.indexOf('\u53d1\u9001\u5230\u6b64\u90ae\u7bb1\u7684\u9a8c\u8bc1\u7801\u8fc7\u591a') >= 0) bodyBad = true;
      if (low.indexOf('invalid_argument') >= 0 || low.indexOf('\"error\"') >= 0) {
        if (low.indexOf('\"error\":null') < 0 && low.indexOf('\"error\": null') < 0) bodyBad = true;
      }
    }
    window.__hybrid_create_email_body_ok = !bodyBad;
    var httpOk = !!ok || (Number(status) >= 200 && Number(status) < 300);
    window.__hybrid_create_email_ok = !!(httpOk && !bodyBad);
    window.__hybrid_create_email_inflight = false;
    if (window.__hybrid_create_email_ok) {
      window.__hybrid_create_email_sent_once = true;
    }
  }"""
if old_mark not in t:
    raise SystemExit("mark function missing")
t = t.replace(old_mark, new_mark, 1)

old_fetch = """      window.__hybrid_create_email_shared = p.then(async function(resp){
        try {
          markCreateEmailResponse(url, resp.status || 0, !!(resp.ok || (resp.status >= 200 && resp.status < 300)));
        } catch (e) {}
        return resp;
      });"""
new_fetch = """      window.__hybrid_create_email_shared = p.then(async function(resp){
        try {
          var bodyText = '';
          try {
            var cloned = resp.clone();
            bodyText = await cloned.text();
          } catch (e2) { bodyText = ''; }
          markCreateEmailResponse(
            url,
            resp.status || 0,
            !!(resp.ok || (resp.status >= 200 && resp.status < 300)),
            bodyText
          );
        } catch (e) {}
        return resp;
      });"""
if old_fetch not in t:
    raise SystemExit("fetch block missing")
t = t.replace(old_fetch, new_fetch, 1)

old_xhr = """          if (isCreateEmailUrl(xhr.__u)) {
            markCreateEmailResponse(xhr.__u, xhr.status || 0, xhr.status >= 200 && xhr.status < 300);
          }"""
new_xhr = """          if (isCreateEmailUrl(xhr.__u)) {
            var xt = '';
            try { xt = String(xhr.responseText || ''); } catch (e3) { xt = ''; }
            markCreateEmailResponse(xhr.__u, xhr.status || 0, xhr.status >= 200 && xhr.status < 300, xt);
          }"""
if old_xhr not in t:
    raise SystemExit("xhr block missing")
t = t.replace(old_xhr, new_xhr, 1)

old_ret = """return {
  ok: !!window.__hybrid_create_email_ok,
  status: Number(window.__hybrid_create_email_status||0),
  seen: !!window.__hybrid_create_email_seen,
  castle_len: Number((window.__hybrid_castle||'').length||0),
  net_hits: uniq.length,
  net_hits_raw: hits.length,
  actual_send_count: Number(window.__hybrid_create_email_actual_sends||0),
  blocked_duplicate_count: Number(window.__hybrid_create_email_blocked||0),
  inflight: !!window.__hybrid_create_email_inflight,
  sent_once: !!window.__hybrid_create_email_sent_once,
  net_urls: uniq.slice(0, 5).map(n => String((n&&n.url)||'').slice(0, 160))
};"""
new_ret = """return {
  ok: !!window.__hybrid_create_email_ok,
  status: Number(window.__hybrid_create_email_status||0),
  seen: !!window.__hybrid_create_email_seen,
  castle_len: Number((window.__hybrid_castle||'').length||0),
  net_hits: uniq.length,
  net_hits_raw: hits.length,
  actual_send_count: Number(window.__hybrid_create_email_actual_sends||0),
  blocked_duplicate_count: Number(window.__hybrid_create_email_blocked||0),
  inflight: !!window.__hybrid_create_email_inflight,
  sent_once: !!window.__hybrid_create_email_sent_once,
  body_ok: (window.__hybrid_create_email_body_ok !== false),
  body_text: String(window.__hybrid_create_email_body||'').slice(0, 400),
  net_urls: uniq.slice(0, 5).map(n => String((n&&n.url)||'').slice(0, 160))
};"""
if old_ret not in t:
    raise SystemExit("status return missing")
t = t.replace(old_ret, new_ret, 1)

old_sent = """        if ok and 200 <= status < 300:
            data[\"sent\"] = True
            data[\"reason\"] = f\"ok_status={status}\"
        elif ok and status == 0 and ui_code_step:
            data[\"sent\"] = True
            data[\"reason\"] = \"ok_status_unknown_but_code_step\"
        elif seen and 200 <= status < 300:
            data[\"sent\"] = True
            data[\"reason\"] = f\"seen_status={status}\"
        elif seen and status == 0 and ui_code_step:
            data[\"sent\"] = True
            data[\"reason\"] = \"seen_status_unknown_code_step\"
        elif seen and status == 0:"""
new_sent = """        body_ok = True
        if isinstance(raw, dict) and \"body_ok\" in raw:
            body_ok = bool(raw.get(\"body_ok\"))
        data[\"body_ok\"] = body_ok
        if isinstance(raw, dict) and raw.get(\"body_text\"):
            data[\"net_body_text\"] = str(raw.get(\"body_text\") or \"\")[:400]
        # 18r44b: require real 2xx + body_ok; bare code-step is NOT send evidence
        if ok and 200 <= status < 300 and body_ok:
            data[\"sent\"] = True
            data[\"reason\"] = f\"ok_status={status}\"
        elif ok and 200 <= status < 300 and not body_ok:
            data[\"sent\"] = False
            data[\"reason\"] = f\"ok_status={status}_body_bad\"
        elif seen and 200 <= status < 300 and body_ok:
            data[\"sent\"] = True
            data[\"reason\"] = f\"seen_status={status}\"
        elif seen and 200 <= status < 300 and not body_ok:
            data[\"sent\"] = False
            data[\"reason\"] = f\"seen_status={status}_body_bad\"
        elif seen and status == 0 and ui_code_step:
            data[\"sent\"] = False
            data[\"reason\"] = \"seen_status_unknown_code_step\"
        elif ok and status == 0 and ui_code_step:
            data[\"sent\"] = False
            data[\"reason\"] = \"ok_status_unknown_but_code_step\"
        elif seen and status == 0:"""
if old_sent not in t:
    raise SystemExit("sent logic missing")
t = t.replace(old_sent, new_sent, 1)

th.write_text(t, encoding="utf-8")
py_compile.compile(str(th), doraise=True)
print("token_harvester OK")

hr = Path(r"C:\Users\zhang\grok-regkit\hybrid_register.py")
h = hr.read_text(encoding="utf-8")
if not h.lstrip().startswith("# 18r44b:"):
    h = "# 18r44b: CreateEmail never promote on bare ui_code (stale OTP page)\n" + h
if "2026-07-22r44b" not in h:
    h = h.replace(
        "Changelog:\n",
        "Changelog:\n- 2026-07-22r44b: CreateEmail 禁止仅凭 ui_code 晋升 browser_sent；配合 token_harvester body-aware OK，修 pending 恢复假成功->early_no_new_mail 空烧。\n",
        1,
    )

old_cs = """            confirmed_send = bool(
                ui_code_now
                or (
                    reason not in weak_reasons
                    and (
                        (raw_sent and (strong_http or actual_send >= 1))
                        or (strong_http and (actual_send >= 1 or bool(st.get(\"ok\"))))
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
                    and (actual_send >= 1 or bool(st.get(\"ok\")) or raw_sent)
                )
            )"""
new_cs = """            # 18r44b: bare ui_code must NOT confirm send — recovery OTP page often stale
            body_ok_flag = st.get(\"body_ok\", True)
            if body_ok_flag is None:
                body_ok_flag = True
            body_ok_flag = bool(body_ok_flag)
            confirmed_send = bool(
                reason not in weak_reasons
                and strong_http
                and body_ok_flag
                and (
                    (raw_sent and actual_send >= 1)
                    or (actual_send >= 1 and bool(st.get(\"ok\")))
                    or (raw_sent and bool(st.get(\"ok\")))
                )
            )
            network_fired = (net_hits_n >= 1) or (actual_send_hook >= 1) or (actual_send >= 1)
            # dual-send lock only on confirmed real send (not bare OTP UI)
            dual_send_lock = bool(
                confirmed_send
                and strong_http
                and body_ok_flag
                and reason not in weak_reasons
                and (actual_send >= 1 or bool(st.get(\"ok\")) or raw_sent)
            )"""
if old_cs not in h:
    raise SystemExit("confirmed_send block missing")
h = h.replace(old_cs, new_cs, 1)

old_p2 = """                    # 18r43b: do not promote on bare 2xx without ok/send/ui_code
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
                            f\"[hybrid] CreateEmail wait-confirm OK \"
                            f\"status={status2} reason={reason2} ui_code={ui2} \"
                            f\"actual={actual_send} net_hits={net2} dual_lock={int(dual_send_lock)}\"
                        )
                        break"""
new_p2 = """                    # 18r44b: require strong 2xx + ok/send; bare ui_code never promotes
                    body2 = st2.get(\"body_ok\", True)
                    if body2 is None:
                        body2 = True
                    body2 = bool(body2)
                    promote2 = bool(
                        reason2 not in weak_reasons
                        and strong2
                        and body2
                        and (act2 >= 1 or raw2)
                        and (ok2 or raw2)
                    )
                    if promote2:
                        st = st2
                        reason = reason2
                        status_n = status2
                        net_hits_n = net2
                        actual_send_hook = act2
                        actual_send = act2 if act2 > 0 else (net2 if strong2 and ok2 and body2 else 0)
                        ui_code_now = ui2
                        strong_http = strong2
                        raw_sent = raw2
                        confirmed_send = True
                        dual_send_lock = bool(
                            strong2
                            and body2
                            and reason2 not in weak_reasons
                            and (act2 >= 1 or raw2 or ok2)
                        )
                        browser_sent = True
                        has_send_evidence = True
                        log(
                            f\"[hybrid] CreateEmail wait-confirm OK \"
                            f\"status={status2} reason={reason2} ui_code={ui2} body_ok={int(body2)} \"
                            f\"actual={actual_send} net_hits={net2} dual_lock={int(dual_send_lock)}\"
                        )
                        break"""
if old_p2 not in h:
    raise SystemExit("promote2 block missing")
h = h.replace(old_p2, new_p2, 1)

hr.write_text(h, encoding="utf-8")
py_compile.compile(str(hr), doraise=True)
print("hybrid_register OK")
print("ALL_PATCHED")