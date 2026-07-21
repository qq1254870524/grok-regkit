# -*- coding: utf-8 -*-
from pathlib import Path
import shutil
from datetime import datetime

root = Path(r"C:\Users\zhang\grok-regkit")
path = root / "grok_register_ttk.py"
bak = root / f"grok_register_ttk.py.bak_18r29_{datetime.now().strftime('%H%M%S')}"
shutil.copy2(path, bak)
text = path.read_text(encoding="utf-8")

# changelog header insert after first docstring line block
marker = "def fill_code_and_submit"
if "18r29b: browser early_no_new_mail" not in text:
    # add changelog near top if there's a changelog list
    insert_note = (
        "- 2026-07-19r29b: browser 路径 early_no_new_mail/验证码超时与 hybrid 对齐："
        "burn_mailbox_to_pending 删池+写 pending_sso，统计 pending 而非硬 fail；"
        "保留成功→即时SSO→入池主路径。\n"
    )
    if "2026-07-19r28f" in text and insert_note.strip() not in text:
        text = text.replace(
            "- 2026-07-19r28f:",
            insert_note + "- 2026-07-19r28f:",
            1,
        )

OLD1 = '''                        except Exception as mail_exc:
                            msg = str(mail_exc)
                            if ("未收到验证码" in msg or "验证码" in msg) and mail_try < max_mail_retry:
                                self.log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {msg}")
                                restart_browser(log_callback=self.log)
                                sleep_with_cancel(1, self.should_stop)
                                continue
                            raise
'''

NEW1 = '''                        except Exception as mail_exc:
                            msg = str(mail_exc)
                            _mail_fail = any(
                                k in msg
                                for k in (
                                    "early_no_new_mail",
                                    "未收到验证码",
                                    "获取验证码失败",
                                    "code_timeout",
                                    "no post-send",
                                    "验证码超时",
                                )
                            )
                            if _mail_fail:
                                try:
                                    from hybrid_register import burn_mailbox_to_pending
                                    _reason = (
                                        "early_no_new_mail"
                                        if "early_no_new_mail" in msg
                                        else "browser_code_timeout"
                                    )
                                    burn_mailbox_to_pending(
                                        email,
                                        "",
                                        reason=_reason,
                                        log=self.log,
                                        mail_token=str(dev_token or ""),
                                    )
                                    self.log(
                                        f"[!] browser mail fail -> pending_sso+del pool "
                                        f"email={email} reason={_reason} detail={msg}"
                                    )
                                except Exception as pend_exc:
                                    self.log(
                                        f"[!] browser burn pending fail email={email}: {pend_exc}"
                                    )
                            if _mail_fail and mail_try < max_mail_retry:
                                self.log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {msg}")
                                restart_browser(log_callback=self.log)
                                sleep_with_cancel(1, self.should_stop)
                                continue
                            if _mail_fail:
                                raise Exception(
                                    f"pending_sso:browser_code_fail email={email} {msg}"
                                )
                            raise
'''

OLD2 = '''                    except Exception as mail_exc:
                        msg = str(mail_exc)
                        if ("未收到验证码" in msg or "验证码" in msg) and mail_try < max_mail_retry:
                            log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {msg}")
                            restart_browser(log_callback=log)
                            sleep_with_cancel(1, controller.should_stop)
                            continue
                        raise
'''

NEW2 = '''                    except Exception as mail_exc:
                        msg = str(mail_exc)
                        _mail_fail = any(
                            k in msg
                            for k in (
                                "early_no_new_mail",
                                "未收到验证码",
                                "获取验证码失败",
                                "code_timeout",
                                "no post-send",
                                "验证码超时",
                            )
                        )
                        if _mail_fail:
                            try:
                                from hybrid_register import burn_mailbox_to_pending
                                _reason = (
                                    "early_no_new_mail"
                                    if "early_no_new_mail" in msg
                                    else "browser_code_timeout"
                                )
                                burn_mailbox_to_pending(
                                    email,
                                    "",
                                    reason=_reason,
                                    log=log,
                                    mail_token=str(dev_token or ""),
                                )
                                log(
                                    f"[!] browser/cli mail fail -> pending_sso+del pool "
                                    f"email={email} reason={_reason} detail={msg}"
                                )
                            except Exception as pend_exc:
                                log(f"[!] browser/cli burn pending fail email={email}: {pend_exc}")
                        if _mail_fail and mail_try < max_mail_retry:
                            log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {msg}")
                            restart_browser(log_callback=log)
                            sleep_with_cancel(1, controller.should_stop)
                            continue
                        if _mail_fail:
                            raise Exception(
                                f"pending_sso:browser_code_fail email={email} {msg}"
                            )
                        raise
'''

n1 = text.count(OLD1)
n2 = text.count(OLD2)
print("OLD1 matches", n1, "OLD2 matches", n2)
if n1 != 1 or n2 != 1:
    raise SystemExit(f"unexpected match counts n1={n1} n2={n2}")
text = text.replace(OLD1, NEW1, 1).replace(OLD2, NEW2, 1)
path.write_text(text, encoding="utf-8")
print("patched", path)
print("bak", bak)

# retro-burn venitamargiebl6
import importlib.util
spec = importlib.util.spec_from_file_location("hybrid_register", root / "hybrid_register.py")
hr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hr)

def log(m):
    print(m)

# find token from mail_credentials
token = ""
mc = root / "mail_credentials.txt"
if mc.exists():
    for line in mc.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("venitamargiebl6@outlook.com"):
            parts = line.split("\t", 1)
            if len(parts) == 2:
                token = parts[1].strip()
hr.burn_mailbox_to_pending(
    "venitamargiebl6@outlook.com",
    "",
    reason="early_no_new_mail",
    log=log,
    mail_token=token,
)
print("retro burn done")
# verify
pool = (root / "outlook_accounts.txt").read_text(encoding="utf-8", errors="replace")
pend = (root / "accounts_registered_pending_sso.txt").read_text(encoding="utf-8", errors="replace")
print("still_in_pool", "venitamargiebl6" in pool)
print("in_pending", "venitamargiebl6" in pend)
