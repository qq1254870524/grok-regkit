# -*- coding: utf-8 -*-
"""18r30: multi-thread hybrid job + mail top=5 + web workers."""
from pathlib import Path
import re
import py_compile

# ---------- hybrid_register.py ----------
hp = Path("hybrid_register.py")
ht = hp.read_text(encoding="utf-8")

# Update function signature and implement multi-thread
old_sig = "def run_hybrid_registration_job(count, log_callback=None, controller=None):"
if "def run_hybrid_registration_job(count, log_callback=None, controller=None, workers=None):" not in ht:
    if old_sig not in ht:
        raise SystemExit("hybrid job sig missing")
    ht = ht.replace(old_sig, "def run_hybrid_registration_job(count, log_callback=None, controller=None, workers=None):", 1)
    print("hybrid sig updated")

# Inject multi-thread branch after initial setup (after proxy resolve + pre-mark)
# Strategy: replace the entire function with serial path extracted + MT path
# Safer: after `proxy = str(...)` and before `try: i=0`, add workers branch that runs MT and returns.

marker = '''    ua = str(engine.config.get("user_agent") or "")
    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    try:
        i = 0
        switch_mailbox_tries = 0
        max_switch_mailbox = max(8, int(count) * 3)
        while i < count:
'''

mt_insert = '''    ua = str(engine.config.get("user_agent") or "")
    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    # ---- 18r30 multi-thread ----
    try:
        from worker_coord import resolve_workers, preflight_email_pools
        _workers = resolve_workers(engine.config, workers)
    except Exception:
        try:
            _workers = max(1, int(workers if workers is not None else (engine.config.get("workers") or 1)))
        except Exception:
            _workers = 1
    log(f"[*] 混合模式 workers={_workers}")

    if bool(engine.config.get("email_preflight_on_start", True)):
        try:
            top_n = int(engine.config.get("mail_top_per_folder") or 5)
            preflight_email_pools(engine.config, log=log, top=top_n)
        except Exception as pf_exc:
            log(f"[!] email preflight: {pf_exc}")

    if _workers > 1:
        return _run_hybrid_registration_job_mt(
            count=count,
            log=log,
            controller=controller,
            workers=_workers,
            ua=ua,
            proxy=proxy,
            next_action=next_action,
            accounts_output_file=accounts_output_file,
            engine=engine,
        )

    try:
        i = 0
        switch_mailbox_tries = 0
        max_switch_mailbox = max(8, int(count) * 3)
        while i < count:
'''

if "_run_hybrid_registration_job_mt" not in ht:
    if marker not in ht:
        raise SystemExit("hybrid marker missing for mt insert")
    ht = ht.replace(marker, mt_insert, 1)
    print("hybrid mt branch inserted")
else:
    print("hybrid mt already")

# Append helper function before end of file or after run_hybrid_registration_job
if "def _run_hybrid_registration_job_mt" not in ht:
    helper = r'''


def _run_hybrid_registration_job_mt(
    *,
    count,
    log,
    controller,
    workers,
    ua,
    proxy,
    next_action,
    accounts_output_file,
    engine,
):
    """Multi-worker hybrid: each worker TLS browser + bound SOCKS5; email via pool.acquire (in_use)."""
    import threading
    from pathlib import Path as _Path
    from worker_coord import (
        JobCoordinator,
        bind_worker_proxy,
        clear_worker_proxy,
        worker_log,
    )

    wn = max(1, int(workers or 1))
    log(f"[*] 混合多线程启动 workers={wn} target={count}")
    max_switch = max(8, int(count) * 3)
    coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max_switch)
    accounts_file = _Path(accounts_output_file)

    def _worker(wid: int):
        wlog = worker_log(log, wid)
        coord.worker_enter()
        try:
            wproxy = bind_worker_proxy(engine, wid, log=wlog)
            if not wproxy:
                wproxy = proxy
            wlog(f"[*] hybrid worker start proxy={wproxy or '(direct)'}")
            while not controller.should_stop() and not coord.should_halt():
                slot = coord.claim_slot()
                if slot is None:
                    break
                wlog(f"--- [hybrid] 开始第 {slot}/{count} 个账号 (worker={wid}) ---")
                try:
                    raw = register_one_hybrid(
                        log=wlog,
                        proxy=wproxy,
                        user_agent=ua,
                        next_action=next_action,
                        accounts_file=accounts_file,
                        should_stop=controller.should_stop,
                        post_success=True,
                    )
                    res = normalize_result(raw)
                    status = str(res.get("status") or STATUS_FAIL)
                    if controller.should_stop() or status == STATUS_STOPPED:
                        wlog("[*] 当前账号因停止请求中断")
                        # reclaim slot so stats stay accurate
                        try:
                            coord.reclaim_slot()
                        except Exception:
                            pass
                        break
                    if status == STATUS_SUCCESS:
                        coord.record_success()
                    elif status == STATUS_PENDING_SSO and (
                        bool(res.get("rate_limited") or res.get("switch_mailbox"))
                        or "create_email_rate_limited" in str(res.get("detail") or "")
                    ):
                        coord.reclaim_slot()
                        coord.record_pending(rate_limited=True)
                        wlog(
                            f"[hybrid] rate-limited mailbox burned; IMMEDIATE switch next email "
                            f"email={res.get('email')} detail={res.get('detail')} "
                            f"(do not consume success target slot)"
                        )
                    elif status == STATUS_PENDING_SSO:
                        coord.record_pending(rate_limited=False)
                    elif status == STATUS_POOL_EMPTY:
                        coord.mark_pool_empty()
                        wlog("[*] 邮箱池已空，停止后续注册（不计为失败）")
                        break
                    else:
                        coord.record_fail()
                except Exception as exc:
                    coord.record_fail()
                    wlog(f"[hybrid] worker exception: {exc}")
                    try:
                        wlog(traceback.format_exc())
                    except Exception:
                        pass
                finally:
                    coord.log_stats()
                    engine.sleep_with_cancel(0.5, controller.should_stop)
        finally:
            try:
                engine.stop_browser(log_callback=wlog)
            except Exception:
                pass
            clear_worker_proxy(engine, log=wlog)
            coord.worker_leave()
            wlog("[*] hybrid worker exit")

    threads = []
    for i in range(wn):
        t = threading.Thread(target=_worker, args=(i + 1,), name=f"hybrid-w{i+1}", daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    snap = coord.snapshot()
    try:
        if controller.should_stop():
            engine.force_stop_registration(log_callback=log, reason="hybrid_mt_job_stopped")
        else:
            engine.stop_browser(log_callback=log)
    except Exception as stop_exc:
        log(f"[!] hybrid mt finally stop browser: {stop_exc}")
        try:
            engine.force_kill_registration_browsers(log_callback=log)
        except Exception:
            pass
    try:
        engine.wait_post_success_queue(timeout=15 if controller.should_stop() else 45, log_callback=log)
    except Exception:
        pass
    try:
        engine.cleanup_runtime_memory(log_callback=log, reason="混合多线程任务结束")
    except Exception:
        pass
    log(
        f"[*] 混合任务结束。成功 {snap['success']} | 失败 {snap['fail']} | "
        f"pending_sso {snap['pending_sso']} | 跳过(池空) {snap['skipped']} | workers={wn}"
    )
    return {
        "success": snap["success"],
        "fail": snap["fail"],
        "pending_sso": snap["pending_sso"],
        "skipped": snap["skipped"],
        "pool_empty": bool(snap["pool_empty"]),
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
        "workers": wn,
    }
'''
    # append after run_hybrid function return block - at end of file
    ht = ht.rstrip() + "\n" + helper + "\n"
    print("hybrid mt helper appended")

hp.write_text(ht, encoding="utf-8")
py_compile.compile(str(hp), doraise=True)
print("hybrid COMPILE OK")

# ---------- outlook_mail.py GRAPH_TOP ----------
op = Path("outlook_mail.py")
ot = op.read_text(encoding="utf-8")
ot2 = ot.replace(
    "GRAPH_TOP = 20  # 2026-07-18m speed: recent per folder; still ALL folders, not full mailbox",
    "GRAPH_TOP = 5  # 18r30: ALL folders, newest 5 only (faster; still full folder scan)",
)
if ot2 == ot:
    # try any GRAPH_TOP = N
    ot2 = re.sub(r"GRAPH_TOP\s*=\s*\d+", "GRAPH_TOP = 5", ot, count=1)
    print("outlook GRAPH_TOP regex", ot != ot2)
else:
    print("outlook GRAPH_TOP = 5")
op.write_text(ot2, encoding="utf-8")
py_compile.compile(str(op), doraise=True)

# ---------- aol_mail.py TOP ----------
ap = Path("aol_mail.py")
at = ap.read_text(encoding="utf-8")
at2 = at.replace(
    "TOP = 25  # 2026-07-18m speed: fewer messages per folder",
    "TOP = 5  # 18r30: ALL folders, newest 5 only",
)
if at2 == at:
    # only replace inside get_oai_code - careful
    at2 = re.sub(
        r"(def get_oai_code\([\s\S]*?)TOP\s*=\s*\d+",
        r"\1TOP = 5",
        at,
        count=1,
    )
    print("aol TOP regex", at != at2)
else:
    print("aol TOP = 5")
# also default fetch_recent top_per_folder default 30 -> 5
at2 = at2.replace(
    "def fetch_recent(self, top_per_folder: int = 30)",
    "def fetch_recent(self, top_per_folder: int = 5)",
)
ap.write_text(at2, encoding="utf-8")
py_compile.compile(str(ap), doraise=True)
print("aol COMPILE OK")

# ---------- pending multi-thread (light) ----------
pp = Path("pending_sso_recovery.py")
pt = pp.read_text(encoding="utf-8")
old_p = "def run_pending_sso_recovery_job(count=0, log_callback=None, controller=None):"
new_p = "def run_pending_sso_recovery_job(count=0, log_callback=None, controller=None, workers=None):"
if new_p not in pt:
    pt = pt.replace(old_p, new_p, 1)
    # After proxy resolve, before for loop, insert workers note (serial stays default for pending safety)
    # Multi-thread pending is riskier (same file mutations). Use workers only when >1 with lock on file ops.
    # For v1: log workers but keep serial if workers>1 with a simple parallel claim.
    insert_after = '''    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

    try:
        if not pending:
'''
    insert = '''    proxy = str(engine.config.get("proxy") or resolved_proxy or "")

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
'''
    if "_run_pending_sso_recovery_job_mt" not in pt:
        if insert_after not in pt:
            raise SystemExit("pending insert marker missing")
        pt = pt.replace(insert_after, insert, 1)
        helper = r'''


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
                    if status == STATUS_SUCCESS:
                        coord.record_success()
                    elif status == STATUS_STOPPED:
                        break
                    else:
                        coord.record_fail()
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
'''
        pt = pt.rstrip() + "\n" + helper + "\n"
        print("pending mt added")
    pp.write_text(pt, encoding="utf-8")
    py_compile.compile(str(pp), doraise=True)
    print("pending COMPILE OK")
else:
    print("pending already has workers sig")

print("ALL PART A OK")
