from pathlib import Path
import ast
import time as _time

p = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
text = p.read_text(encoding="utf-8")

old_loop = '''def _post_success_worker_loop():
    """Background worker: NSFW / g2a / Sub2API / CPA（不阻塞下一号浏览器注册）。"""
    while True:
        job = _post_success_q.get()
        if job is None:
            _post_success_q.task_done()
            break
        log = job.get("log") or (lambda m: print(m, flush=True))
        email = job.get("email") or ""
        sso = job.get("sso") or ""
        try:
            try:
                load_config()
            except Exception:
                pass
            log(f"[bg] 后处理开始: {email}")
            if job.get("do_nsfw"):
                log(f"[bg] 开启 NSFW: {email}")
                try:
                    nsfw_ok, nsfw_msg = enable_nsfw_for_token(sso, log_callback=log)
                    if nsfw_ok:
                        log(f"[bg] NSFW 开启成功: {nsfw_msg}")
                    else:
                        log(f"[bg] NSFW 未开启: {nsfw_msg}")
                except Exception as nsfw_exc:
                    log(f"[bg] NSFW 异常: {nsfw_exc}")
            if job.get("do_g2a"):
                try:
                    bg_tries = int(config.get("grok2api_bg_max_http_tries", 6) or 6)
                except (TypeError, ValueError):
                    bg_tries = 6
                try:
                    bg_timeout = float(config.get("grok2api_bg_http_timeout_sec", 15) or 15)
                except (TypeError, ValueError):
                    bg_timeout = 15.0
                add_token_to_grok2api_pools(
                    sso,
                    email=email,
                    log_callback=log,
                    max_http_tries=bg_tries,
                    http_timeout=bg_timeout,
                )
            cpa_result = None
            if job.get("do_cpa") and config.get("cpa_export_enabled", True) and config.get("cpa_auto_add", True):
                try:
                    cpa_result = export_cpa_after_success(
                        email,
                        job.get("password") or "",
                        sso,
                        page=None,
                        cookies=job.get("cookies") or [],
                        log_callback=log,
                    )
                except Exception as cpa_exc:
                    log(f"[bg] CPA 导出未成功: {cpa_exc}")
                    cpa_result = {"ok": False, "error": str(cpa_exc)}
            if job.get("do_sub2api"):
                try:
                    from sub2api_client import import_after_success_prefer_cpa

                    import_after_success_prefer_cpa(
                        sso,
                        email=email,
                        password=job.get("password") or "",
                        cpa_result=cpa_result,
                        config=config,
                        log_callback=log,
                    )
                except Exception as sub2api_exc:
                    log(f"[bg] Sub2API 入池未成功（注册结果保留）: {sub2api_exc}")
                    try:
                        from sub2api_client import record_sub2api_import_failure

                        record_sub2api_import_failure(
                            email=email,
                            sso=sso,
                            password=job.get("password") or "",
                            error=str(sub2api_exc),
                            config=config,
                            log_callback=log,
                        )
                    except Exception as rec_exc:
                        log(f"[bg] Sub2API 失败落盘异常: {rec_exc}")
            try:
                from sub2api_client import log_pool_counts

                log_pool_counts(config=config, log_callback=log, email=email)
            except Exception:
                pass
            log(f"[bg] 后处理完成: {email}")
        except Exception as exc:
            log(f"[bg] 后处理异常 {email}: {exc}")
        finally:
            global _post_success_pending
            with _post_success_pending_lock:
                _post_success_pending = max(0, _post_success_pending - 1)
            _post_success_q.task_done()
'''

new_loop = '''def _post_success_worker_loop():
    """Background worker: NSFW / g2a / Sub2API / CPA（不阻塞下一号浏览器注册）。

    18r43h: never die on job errors; task_done exactly-once with ValueError guard
    so a single bad job cannot kill the drain pool (awaiting_pool stuck).
    """
    while True:
        job = None
        try:
            job = _post_success_q.get()
        except Exception:
            time.sleep(0.2)
            continue
        if job is None:
            try:
                _post_success_q.task_done()
            except ValueError:
                pass
            break
        log = job.get("log") if isinstance(job, dict) else None
        if not callable(log):
            log = (lambda m: print(m, flush=True))
        email = ""
        sso = ""
        try:
            email = str((job or {}).get("email") or "")
            sso = str((job or {}).get("sso") or "")
            try:
                load_config()
            except Exception:
                pass
            try:
                log(f"[bg] 后处理开始: {email}")
            except Exception:
                pass
            if job.get("do_nsfw"):
                try:
                    log(f"[bg] 开启 NSFW: {email}")
                except Exception:
                    pass
                try:
                    nsfw_ok, nsfw_msg = enable_nsfw_for_token(sso, log_callback=log)
                    if nsfw_ok:
                        log(f"[bg] NSFW 开启成功: {nsfw_msg}")
                    else:
                        log(f"[bg] NSFW 未开启: {nsfw_msg}")
                except Exception as nsfw_exc:
                    try:
                        log(f"[bg] NSFW 异常: {nsfw_msg if False else nsfw_exc}")
                    except Exception:
                        pass
            if job.get("do_g2a"):
                try:
                    bg_tries = int(config.get("grok2api_bg_max_http_tries", 6) or 6)
                except (TypeError, ValueError):
                    bg_tries = 6
                try:
                    bg_timeout = float(config.get("grok2api_bg_http_timeout_sec", 15) or 15)
                except (TypeError, ValueError):
                    bg_timeout = 15.0
                try:
                    add_token_to_grok2api_pools(
                        sso,
                        email=email,
                        log_callback=log,
                        max_http_tries=bg_tries,
                        http_timeout=bg_timeout,
                    )
                except Exception as g2a_exc:
                    try:
                        log(f"[bg] g2a 异常: {g2a_exc}")
                    except Exception:
                        pass
            cpa_result = None
            if job.get("do_cpa") and config.get("cpa_export_enabled", True) and config.get("cpa_auto_add", True):
                try:
                    cpa_result = export_cpa_after_success(
                        email,
                        job.get("password") or "",
                        sso,
                        page=None,
                        cookies=job.get("cookies") or [],
                        log_callback=log,
                    )
                except Exception as cpa_exc:
                    try:
                        log(f"[bg] CPA 导出未成功: {cpa_exc}")
                    except Exception:
                        pass
                    cpa_result = {"ok": False, "error": str(cpa_exc)}
            if job.get("do_sub2api"):
                try:
                    from sub2api_client import import_after_success_prefer_cpa

                    import_after_success_prefer_cpa(
                        sso,
                        email=email,
                        password=job.get("password") or "",
                        cpa_result=cpa_result,
                        config=config,
                        log_callback=log,
                    )
                except Exception as sub2api_exc:
                    try:
                        log(f"[bg] Sub2API 入池未成功（注册结果保留）: {sub2api_exc}")
                    except Exception:
                        pass
                    try:
                        from sub2api_client import record_sub2api_import_failure

                        record_sub2api_import_failure(
                            email=email,
                            sso=sso,
                            password=job.get("password") or "",
                            error=str(sub2api_exc),
                            config=config,
                            log_callback=log,
                        )
                    except Exception as rec_exc:
                        try:
                            log(f"[bg] Sub2API 失败落盘异常: {rec_exc}")
                        except Exception:
                            pass
            try:
                from sub2api_client import log_pool_counts

                log_pool_counts(config=config, log_callback=log, email=email)
            except Exception:
                pass
            try:
                log(f"[bg] 后处理完成: {email}")
            except Exception:
                pass
        except Exception as exc:
            try:
                log(f"[bg] 后处理异常 {email}: {exc}")
            except Exception:
                pass
        finally:
            global _post_success_pending
            try:
                with _post_success_pending_lock:
                    _post_success_pending = max(0, int(_post_success_pending or 0) - 1)
            except Exception:
                pass
            try:
                _post_success_q.task_done()
            except ValueError:
                pass
            except Exception:
                pass
'''

if old_loop not in text:
    raise SystemExit("old_loop not found exact match")
text2 = text.replace(old_loop, new_loop, 1)

old_ensure_vars = '''_post_success_worker_started = False
_post_success_worker_count = 0
_post_success_pending = 0
_post_success_pending_lock = threading.Lock()
'''
new_ensure_vars = '''_post_success_worker_started = False
_post_success_worker_count = 0
_post_success_threads = []  # 18r43h live Thread refs for dead-worker replace
_post_success_pending = 0
_post_success_pending_lock = threading.Lock()
'''
if old_ensure_vars not in text2:
    raise SystemExit("ensure vars block not found")
text2 = text2.replace(old_ensure_vars, new_ensure_vars, 1)

old_ensure = '''def ensure_post_success_worker(log_callback=None, workers=None):
    """Start N background post-success workers (G2A/Sub2/CPA/NSFW).

    18r43a: default 6 workers so awaiting_pool keeps up with register workers=20.
    Safe to call repeatedly; only starts missing workers up to target count.
    """
    global _post_success_worker_started, _post_success_worker_count
    try:
        n = int(workers) if workers is not None else 0
    except Exception:
        n = 0
    if n <= 0:
        try:
            n = int((config or {}).get("post_success_workers") or 0)
        except Exception:
            n = 0
    if n <= 0:
        try:
            reg_w = int((config or {}).get("workers") or (config or {}).get("thread_count") or 0)
        except Exception:
            reg_w = 0
        if reg_w >= 10:
            n = _POST_SUCCESS_DEFAULT_WORKERS
        elif reg_w >= 4:
            n = 3
        else:
            n = 1
    n = max(1, min(16, int(n)))
    with _post_success_worker_lock:
        while _post_success_worker_count < n:
            idx = _post_success_worker_count + 1
            th = threading.Thread(
                target=_post_success_worker_loop,
                name=f"post-success-worker-{idx}",
                daemon=True,
            )
            th.start()
            _post_success_worker_count += 1
        _post_success_worker_started = _post_success_worker_count > 0
        if log_callback:
            log_callback(
                f"[*] 后处理后台线程已启动 workers={_post_success_worker_count} "
                f"（g2a/Sub2API/CPA/NSFW 可异步；awaiting_pool 并行排空）"
            )
'''

new_ensure = '''def ensure_post_success_worker(log_callback=None, workers=None):
    """Start N background post-success workers (G2A/Sub2/CPA/NSFW).

    18r43a: default 6 workers so awaiting_pool keeps up with register workers=20.
    18r43h: prune dead threads and replace so awaiting_pool keeps draining.
    Safe to call repeatedly; only starts missing workers up to target count.
    """
    global _post_success_worker_started, _post_success_worker_count, _post_success_threads
    try:
        n = int(workers) if workers is not None else 0
    except Exception:
        n = 0
    if n <= 0:
        try:
            n = int((config or {}).get("post_success_workers") or 0)
        except Exception:
            n = 0
    if n <= 0:
        try:
            reg_w = int((config or {}).get("workers") or (config or {}).get("thread_count") or 0)
        except Exception:
            reg_w = 0
        if reg_w >= 10:
            n = _POST_SUCCESS_DEFAULT_WORKERS
        elif reg_w >= 4:
            n = 3
        else:
            n = 1
    n = max(1, min(16, int(n)))
    with _post_success_worker_lock:
        alive = []
        for th in list(_post_success_threads or []):
            try:
                if th is not None and th.is_alive():
                    alive.append(th)
            except Exception:
                pass
        _post_success_threads = alive
        _post_success_worker_count = len(alive)
        started_now = 0
        while _post_success_worker_count < n:
            idx = _post_success_worker_count + 1
            th = threading.Thread(
                target=_post_success_worker_loop,
                name=f"post-success-worker-{idx}",
                daemon=True,
            )
            th.start()
            _post_success_threads.append(th)
            _post_success_worker_count += 1
            started_now += 1
        _post_success_worker_started = _post_success_worker_count > 0
        if log_callback and started_now > 0:
            log_callback(
                f"[*] 后处理后台线程已启动 workers={_post_success_worker_count} "
                f"（+{started_now}；g2a/Sub2API/CPA/NSFW 可异步；awaiting_pool 并行排空）"
            )
'''

if old_ensure not in text2:
    raise SystemExit("old_ensure not found")
text2 = text2.replace(old_ensure, new_ensure, 1)

if not text2.startswith("# 18r43h:"):
    text2 = "# 18r43h: post_success task_done guard + auto-replace dead drain workers\n" + text2
if "2026-07-21r43h" not in text2:
    text2 = text2.replace(
        "Changelog:\n",
        "Changelog:\n- 2026-07-21r43h: post-success worker 永不因单任务异常退出；task_done 防双调用；ensure 替换死线程，避免 awaiting_pool 卡住。\n",
        1,
    )

# fix silly nsfw line if present
text2 = text2.replace(
    'log(f"[bg] NSFW 异常: {nsfw_msg if False else nsfw_exc}")',
    'log(f"[bg] NSFW 异常: {nsfw_exc}")',
)

ast.parse(text2)
p.write_text(text2, encoding="utf-8")
print("patched_ok", p.stat().st_size)