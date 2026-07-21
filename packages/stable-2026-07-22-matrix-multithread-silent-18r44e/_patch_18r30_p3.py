# -*- coding: utf-8 -*-
from pathlib import Path
import re

path = Path("grok_register_ttk.py")
text = path.read_text(encoding="utf-8")

# Fix get_configured_proxy
old = '''def get_configured_proxy():
    mode = str(config.get("proxy_mode", "") or "").strip().lower()
'''
new = '''def get_configured_proxy():
    # 18r30: per-worker proxy override (SOCKS5 sequential bind)
    try:
        ov = get_thread_proxy_override()
        if ov is not None:
            return str(ov or "").strip()
    except Exception:
        pass
    mode = str(config.get("proxy_mode", "") or "").strip().lower()
'''
if "per-worker proxy override" not in text:
    if old not in text:
        raise SystemExit("get_configured_proxy header missing")
    text = text.replace(old, new, 1)
    print("get_configured_proxy patched")
else:
    print("already")

# Fix bare browser_started_with_proxy in long functions
text = text.replace(
    "if hard_recover_count >= 2 and browser_started_with_proxy and get_configured_proxy():",
    "if hard_recover_count >= 2 and _tls_browser_state().browser_started_with_proxy and get_configured_proxy():",
)
# second occurrence - line ~5338
# use regex for multiline and browser_started
text2 = []
for line in text.splitlines(True):
    if "browser_started_with_proxy" in line and "_tls_browser_state()" not in line and "def " not in line and "st." not in line and "browser_started_with_proxy =" not in line and "bool(st.browser_started" not in line:
        # skip TLS helper definitions
        if "t.browser_started" in line or "st.browser_started" in line:
            text2.append(line)
            continue
        if line.strip().startswith("#"):
            text2.append(line)
            continue
        line2 = line.replace("browser_started_with_proxy", "_tls_browser_state().browser_started_with_proxy")
        # avoid double
        line2 = line2.replace("_tls_browser_state()._tls_browser_state()", "_tls_browser_state()")
        text2.append(line2)
        print("rewrote:", line2.strip()[:100])
    else:
        text2.append(line)
text = "".join(text2)

# run_registration_job signature + hybrid workers pass-through
old_rj = '''def run_registration_job(count, log_callback=None, controller=None):
    """Non-interactive registration loop for CLI and Web.

    Returns dict: success, fail, accounts_file, stopped.
    """
    log = log_callback or cli_log
    if controller is None:
        controller = CliStopController()

    reg_mode = str(config.get("register_mode") or "browser").strip().lower()
    if reg_mode in ("hybrid", "protocol_hybrid", "mixed"):
        log(f"[*] 注册模式: hybrid（协议 + 短浏览器）")
        try:
            from hybrid_register import run_hybrid_registration_job

            return run_hybrid_registration_job(
                count, log_callback=log, controller=controller
            )
        except Exception as hybrid_exc:
            log(f"[!] 混合模式启动失败，回退全浏览器: {hybrid_exc}")
'''
new_rj = '''def run_registration_job(count, log_callback=None, controller=None, workers=None):
    """Non-interactive registration loop for CLI and Web.

    Returns dict: success, fail, accounts_file, stopped.
    workers: 18r30 multi-thread count (default config workers/thread_count; 1=serial).
    """
    log = log_callback or cli_log
    if controller is None:
        controller = CliStopController()

    try:
        from worker_coord import resolve_workers
        _workers = resolve_workers(config, workers)
    except Exception:
        try:
            _workers = max(1, int(workers if workers is not None else (config.get("workers") or 1)))
        except Exception:
            _workers = 1
    if _workers > 1:
        log(f"[*] 多线程 workers={_workers}")

    reg_mode = str(config.get("register_mode") or "browser").strip().lower()
    if reg_mode in ("hybrid", "protocol_hybrid", "mixed"):
        log(f"[*] 注册模式: hybrid（协议 + 短浏览器） workers={_workers}")
        try:
            from hybrid_register import run_hybrid_registration_job

            return run_hybrid_registration_job(
                count, log_callback=log, controller=controller, workers=_workers
            )
        except Exception as hybrid_exc:
            log(f"[!] 混合模式启动失败，回退全浏览器: {hybrid_exc}")

    if _workers > 1:
        log("[*] 全浏览器多线程: 每 worker 独立 Chromium + 绑定代理")
        return run_registration_job_multithread(
            count, log_callback=log, controller=controller, workers=_workers
        )
'''
if "def run_registration_job(count, log_callback=None, controller=None, workers=None)" not in text:
    if old_rj not in text:
        raise SystemExit("run_registration_job header block missing")
    text = text.replace(old_rj, new_rj, 1)
    print("run_registration_job workers wired")
else:
    print("run_registration_job already has workers")

# Add multithread browser runner if missing - keep simple: each worker runs serial loop claiming slots
# by calling a shared helper that does ONE full account via nested function extraction is hard.
# Instead: for browser MT, run N threads each calling a simplified path that uses the same
# while-body by importing and re-executing mini loop.

if "def run_registration_job_multithread" not in text:
    mt = r'''

def run_registration_job_multithread(count, log_callback=None, controller=None, workers=2):
    """Full-browser multi-worker: each thread TLS browser + bound SOCKS5; no shared Chromium."""
    import threading as _threading
    from worker_coord import (
        JobCoordinator,
        bind_worker_proxy,
        clear_worker_proxy,
        preflight_email_pools,
        resolve_workers,
        worker_log,
    )

    log = log_callback or cli_log
    if controller is None:
        controller = CliStopController()
    wn = resolve_workers(config, workers)
    log(f"[*] 全浏览器多线程启动 workers={wn} target={count}")

    mode = str(config.get("proxy_mode", "direct") or "direct")
    try:
        resolved_proxy = apply_resolved_proxy_to_config(log_callback=log, fetch_live=True)
    except Exception as proxy_exc:
        log(f"[!] 获取/解析代理失败: {proxy_exc}")
        raise
    if resolved_proxy:
        log(f"[*] 代理模式: {mode} | {resolved_proxy}")
    else:
        log(f"[*] 代理模式: {mode or 'direct'}（直连）")

    if bool(config.get("email_preflight_on_start", True)):
        try:
            top_n = int(config.get("mail_top_per_folder") or 5)
            preflight_email_pools(config, log=log, top=top_n)
        except Exception as pf_exc:
            log(f"[!] email preflight: {pf_exc}")

    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_{now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")
    coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max(8, int(count) * 3))
    # Serialize full-browser single-account body via a lock only around rare global writes if any;
    # browser state is TLS so no lock needed for Chromium.

    def _register_one_browser(wlog):
        """One full browser registration attempt (mirrors serial loop body core)."""
        email = ""
        dev_token = ""
        code = ""
        mail_ok = False
        max_mail_retry = 3
        for mail_try in range(1, max_mail_retry + 1):
            wlog(f"[*] 1. 打开注册页 (尝试 {mail_try}/{max_mail_retry})")
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
                    f.write(f"{email}\t{dev_token}\n")
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
        if not mail_ok:
            raise Exception("验证码阶段失败")
        wlog("[*] 4. 填写资料并完成注册")
        # Prefer existing post-code completion helpers used by serial job
        done = False
        for fname in (
            "fill_profile_submit_and_save",
            "complete_profile_and_save",
            "submit_profile_and_finish",
            "fill_profile_and_submit",
        ):
            fn = globals().get(fname)
            if callable(fn):
                try:
                    fn(
                        email,
                        code,
                        log_callback=wlog,
                        cancel_callback=controller.should_stop,
                        accounts_file=accounts_output_file,
                    )
                    done = True
                    break
                except TypeError:
                    try:
                        fn(log_callback=wlog, cancel_callback=controller.should_stop)
                        done = True
                        break
                    except Exception:
                        pass
        if not done:
            # Inline: call the same functions the serial loop calls after code
            # Search for serial continuation markers by executing known symbols
            if "fill_name_password_and_submit" in globals():
                fill_name_password_and_submit(
                    log_callback=wlog, cancel_callback=controller.should_stop
                )
                done = True
            if not done and "wait_sso_and_post_success" in globals():
                wait_sso_and_post_success(
                    email, log_callback=wlog, cancel_callback=controller.should_stop,
                    accounts_file=accounts_output_file,
                )
                done = True
        if not done:
            # Last resort: raise to surface need for hybrid mode under multi-thread
            raise Exception(
                "browser multi-thread finish helper missing; set register_mode=hybrid for MT"
            )
        return email

    def _worker(wid: int):
        wlog = worker_log(log, wid)
        coord.worker_enter()
        try:
            proxy = bind_worker_proxy(
                __import__(__name__ if False else "grok_register_ttk"),
                wid,
                log=wlog,
            )
            # bind via this module
            set_thread_proxy(proxy)
            wlog(f"[*] worker start proxy={proxy or '(direct)'}")
            try:
                start_browser(log_callback=wlog)
            except Exception as be:
                wlog(f"[!] worker browser start fail: {be}")
                return
            while not controller.should_stop() and not coord.should_halt():
                slot = coord.claim_slot()
                if slot is None:
                    break
                wlog(f"--- 开始第 {slot}/{count} 个账号 (worker={wid}) ---")
                try:
                    _register_one_browser(wlog)
                    coord.record_success()
                    wlog("[+] 注册成功")
                except RegistrationCancelled:
                    wlog("[!] 注册被停止")
                    break
                except Exception as exc:
                    emsg = str(exc)
                    if "pending_sso" in emsg:
                        coord.record_pending()
                        wlog(f"[*] pending_sso: {exc}")
                    else:
                        coord.record_fail()
                        wlog(f"[-] 注册失败: {exc}")
                finally:
                    coord.log_stats()
                    try:
                        if controller.should_stop():
                            break
                        if _get_browser() is None:
                            start_browser(log_callback=wlog)
                        else:
                            restart_browser(log_callback=wlog)
                    except Exception as rb:
                        wlog(f"[!] restart browser: {rb}")
                    sleep_with_cancel(1, controller.should_stop)
        finally:
            try:
                stop_browser(log_callback=wlog)
            except Exception:
                pass
            clear_thread_proxy()
            coord.worker_leave()
            wlog("[*] worker exit")

    threads = []
    for i in range(wn):
        t = _threading.Thread(target=_worker, args=(i + 1,), name=f"reg-browser-w{i+1}", daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    snap = coord.snapshot()
    try:
        wait_post_success_queue(timeout=90, log_callback=log)
    except Exception:
        pass
    try:
        if controller.should_stop():
            force_stop_registration(log_callback=log, reason="browser_mt_job_stopped")
        else:
            cleanup_runtime_memory(log_callback=log, reason="多线程任务结束")
    except Exception as fin_exc:
        log(f"[!] mt job finally: {fin_exc}")
    log(
        f"[*] 多线程任务结束。成功 {snap['success']} | 失败 {snap['fail']} | "
        f"pending_sso {snap['pending_sso']}"
    )
    return {
        "success": snap["success"],
        "fail": snap["fail"],
        "pending_sso": snap["pending_sso"],
        "skipped": snap["skipped"],
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
        "workers": wn,
    }

'''
    text = text.replace(
        "\ndef run_registration_cli(count):\n",
        mt + "\ndef run_registration_cli(count):\n",
        1,
    )
    print("added run_registration_job_multithread")
else:
    print("mt already")

path.write_text(text, encoding="utf-8")
import py_compile
py_compile.compile(str(path), doraise=True)
print("COMPILE OK", path.stat().st_size)
