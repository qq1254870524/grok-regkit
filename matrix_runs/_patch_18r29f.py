from pathlib import Path
import shutil
from datetime import datetime
import py_compile

root = Path(r"C:\Users\zhang\grok-regkit")
path = root / "grok_register_ttk.py"
text = path.read_text(encoding="utf-8")
orig = text
bak = root / "matrix_runs" / f"_bak_grok_register_ttk_18r29f_{datetime.now().strftime('%H%M%S')}.py"
shutil.copy2(path, bak)

if "2026-07-19r29f" not in text:
    text = text.replace(
        "- 2026-07-19r29e:",
        "- 2026-07-19r29f: burn 成功即 +pending_sso_count；本轮已 burn 后空失败/页未就绪不记硬 fail。\n- 2026-07-19r29e:",
        1,
    )

old1 = '''                                    burn_mailbox_to_pending(
                                        email,
                                        _pw,
                                        reason=_reason,
                                        log=self.log,
                                        mail_token=str(dev_token or ""),
                                    )
                                    self.log(
                                        f"[!] browser mail fail -> pending_sso+del pool "
                                        f"email={email} reason={_reason} detail={msg}"
                                    )
'''
new1 = '''                                    burn_mailbox_to_pending(
                                        email,
                                        _pw,
                                        reason=_reason,
                                        log=self.log,
                                        mail_token=str(dev_token or ""),
                                    )
                                    self.pending_sso_count = int(getattr(self, "pending_sso_count", 0) or 0) + 1
                                    try:
                                        self.update_stats()
                                    except Exception:
                                        pass
                                    self.log(
                                        f"[!] browser mail fail -> pending_sso+del pool "
                                        f"email={email} reason={_reason} detail={msg} "
                                        f"pending_sso_count={self.pending_sso_count}"
                                    )
'''
old2 = '''                                burn_mailbox_to_pending(
                                    email,
                                    _pw,
                                    reason=_reason,
                                    log=log,
                                    mail_token=str(dev_token or ""),
                                )
                                log(
                                    f"[!] browser/cli mail fail -> pending_sso+del pool "
                                    f"email={email} reason={_reason} detail={msg}"
                                )
'''
new2 = '''                                burn_mailbox_to_pending(
                                    email,
                                    _pw,
                                    reason=_reason,
                                    log=log,
                                    mail_token=str(dev_token or ""),
                                )
                                pending_sso_count += 1
                                log(
                                    f"[!] browser/cli mail fail -> pending_sso+del pool "
                                    f"email={email} reason={_reason} detail={msg} "
                                    f"pending_sso_count={pending_sso_count}"
                                )
'''
if old1 not in text:
    raise SystemExit("old1 not found")
if old2 not in text:
    raise SystemExit("old2 not found")
text = text.replace(old1, new1)
text = text.replace(old2, new2)

old3 = '''                except Exception as exc:
                    retry_count_for_slot = 0
                    i += 1
                    emsg = str(exc)
                    if emsg.startswith("pending_sso:") or "pending_sso:" in emsg or "mailbox burned to pending_sso" in emsg:
                        self.pending_sso_count = int(getattr(self, "pending_sso_count", 0) or 0) + 1
                        self.log(f"[*] pending_sso counted (not fail): {exc}")
                    else:
                        self.fail_count += 1
                        self.log(f"[-] 注册失败: {exc}")
'''
new3 = '''                except Exception as exc:
                    retry_count_for_slot = 0
                    i += 1
                    emsg = str(exc)
                    _pend_n = int(getattr(self, "pending_sso_count", 0) or 0)
                    if emsg.startswith("pending_sso:") or "pending_sso:" in emsg or "mailbox burned to pending_sso" in emsg:
                        if "pending_sso:browser_code_fail" in emsg:
                            self.log(f"[*] pending_sso already counted on burn: {exc}")
                        else:
                            self.pending_sso_count = _pend_n + 1
                            self.log(f"[*] pending_sso counted (not fail): {exc}")
                    elif _pend_n > 0 and (
                        not emsg.strip()
                        or "注册页未就绪" in emsg
                        or "未找到「使用邮箱注册」" in emsg
                        or "验证码阶段失败" in emsg
                    ):
                        self.log(
                            f"[*] pending_sso keep (skip hard fail after burn) "
                            f"pending_sso_count={_pend_n} err={exc}"
                        )
                    else:
                        self.fail_count += 1
                        self.log(f"[-] 注册失败: {exc}")
'''
old4 = '''            except Exception as exc:
                retry_count_for_slot = 0
                i += 1
                emsg = str(exc)
                if emsg.startswith("pending_sso:") or "pending_sso:" in emsg or "mailbox burned to pending_sso" in emsg:
                    pending_sso_count += 1
                    log(f"[*] pending_sso counted (not fail): {exc}")
                else:
                    fail_count += 1
                    log(f"[-] 注册失败: {exc}")
'''
new4 = '''            except Exception as exc:
                retry_count_for_slot = 0
                i += 1
                emsg = str(exc)
                if emsg.startswith("pending_sso:") or "pending_sso:" in emsg or "mailbox burned to pending_sso" in emsg:
                    if "pending_sso:browser_code_fail" in emsg:
                        log(f"[*] pending_sso already counted on burn: {exc}")
                    else:
                        pending_sso_count += 1
                        log(f"[*] pending_sso counted (not fail): {exc}")
                elif pending_sso_count > 0 and (
                    not emsg.strip()
                    or "注册页未就绪" in emsg
                    or "未找到「使用邮箱注册」" in emsg
                    or "验证码阶段失败" in emsg
                ):
                    log(
                        f"[*] pending_sso keep (skip hard fail after burn) "
                        f"pending_sso_count={pending_sso_count} err={exc}"
                    )
                else:
                    fail_count += 1
                    log(f"[-] 注册失败: {exc}")
'''
if old3 not in text:
    raise SystemExit("old3 not found")
if old4 not in text:
    raise SystemExit("old4 not found")
text = text.replace(old3, new3)
text = text.replace(old4, new4)

old5 = '''                    if not mail_ok:
                        raise Exception("验证码阶段失败，已达到最大重试次数")
'''
new5 = '''                    if not mail_ok:
                        raise Exception("pending_sso:browser_code_fail email=multiple 验证码阶段失败，已达到最大重试次数")
'''
c5 = text.count(old5)
if c5 < 1:
    raise SystemExit("old5 missing")
text = text.replace(old5, new5)

path.write_text(text, encoding="utf-8")
print("patched", path)
print("backup", bak)

mp = root / "tools" / "matrix_cross_run.py"
mt = mp.read_text(encoding="utf-8")
mold = '''        if not rec["class"]:
            if rec["ok"]:
                rec["class"] = "success"
            elif rec["pending_sso"] > 0:
                rec["class"] = "pending_sso"
            elif not (logs or "").strip() or logs.startswith("<log fetch fail"):
                rec["class"] = "empty_log"
            else:
                rec["class"] = classify(logs)
'''
mnew = '''        if not rec["class"]:
            clog = classify(logs) if (logs or "").strip() else ""
            if rec["ok"]:
                rec["class"] = "success"
            elif rec["pending_sso"] > 0 or clog == "pending_sso":
                # 18r29f: log burn markers win even if status.fail>0 / old status pending=0
                rec["class"] = "pending_sso"
                if rec["pending_sso"] <= 0:
                    rec["pending_sso"] = 1
                rec["fail"] = 0
            elif not (logs or "").strip() or logs.startswith("<log fetch fail"):
                rec["class"] = "empty_log"
            else:
                rec["class"] = clog or classify(logs)
'''
if mold not in mt:
    print("matrix run_one block not found exactly")
else:
    mt = mt.replace(mold, mnew, 1)
    if "2026-07-19r29f" not in mt:
        mt = mt.replace(
            "Changelog:\n",
            "Changelog:\n- 2026-07-19r29f: run_one prefers classify pending burn markers over status.fail; soft-clear fail on pending.\n",
            1,
        )
    mp.write_text(mt, encoding="utf-8")
    print("matrix_cross_run patched")

# Also update auto_publish changelog snippet if file exists
ap = root / "tools" / "_auto_publish_18r29.py"
if ap.exists():
    at = ap.read_text(encoding="utf-8")
    if "18r29f" not in at:
        at = at.replace(
            "- **18r29e**：browser 路径 `pending_sso:*` 异常计入 pending 而非 fail，结束日志带 pending_sso 计数。\n",
            "- **18r29e**：browser 路径 `pending_sso:*` 异常计入 pending 而非 fail，结束日志带 pending_sso 计数。\n"
            "- **18r29f**：burn 成功即累计 pending_sso；burn 后空失败/页未就绪不硬 fail；矩阵 run_one 以日志 burn 标记优先归 pending。\n",
        )
        ap.write_text(at, encoding="utf-8")
        print("auto_publish notes updated")

py_compile.compile(str(path), doraise=True)
py_compile.compile(str(mp), doraise=True)
print("compile ok")

# verify markers
t2 = path.read_text(encoding="utf-8")
assert "pending_sso keep (skip hard fail after burn)" in t2
assert "pending_sso_count={self.pending_sso_count}" in t2
print("markers ok")
