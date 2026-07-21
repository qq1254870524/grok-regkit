# -*- coding: utf-8 -*-
from pathlib import Path
import re
import py_compile
import importlib.util

root = Path(r"C:\Users\zhang\grok-regkit")

NEW_CLASSIFY = r'''
def classify(logs: str) -> str:
    """Failure/success taxonomy for matrix cells. Prefer specific terminal signals.

    IMPORTANT: do NOT match healthy log noise such as "IMAP login OK" or
    successful "confirmation code" fetch lines.
    """
    t = (logs or "")
    tl = t.lower()

    # Terminal counters first
    if re.search(r"任务结束。成功\s*1\s*\|\s*失败\s*0", t) or re.search(
        r"成功\s*1\s*\|\s*失败\s*0\s*\|\s*pending_sso\s*0", t
    ):
        return "success"

    rules = [
        ("stop_requested", ["stop requested", "force_stop", "stop requested from web"]),
        ("empty_log", ["<log fetch fail"]),
        ("early_no_new_mail", ["early_no_new_mail", "seen_new_after_send=0", "graph no post-send"]),
        (
            "rate_limit_mailbox",
            [
                "验证码过多",
                "create_email_rate_limited",
                "发送到此邮箱的验证码过多",
                "too many verification",
            ],
        ),
        (
            "create_email_fail",
            [
                "createemail fail",
                "create email fail",
                "发信失败",
                "switch_mailbox",
                "create_email_rate_limited",
            ],
        ),
        (
            "email_login_fail",
            [
                "邮箱登录失败",
                "获取邮箱失败",
                "imap login fail",
                "imap login failed",
                "login failed",
                "auth fail",
                "invalid credentials",
                "authentication failed",
                "preflight login fail",
                "aol ensure_login fail",
                "outlook login fail",
                "graph login fail",
            ],
        ),
        (
            "profile_fill_fail",
            [
                "最终注册页资料填写失败",
                "资料填写失败",
                "fill-failed",
                "no-submit-button",
                "filled-no-submit",
            ],
        ),
        (
            "sso_timeout",
            [
                "未获取到 sso cookie",
                "您正在登录",
                "signing-in",
                "wait_for_sso",
                "sso nudge",
            ],
        ),
        (
            "pending_sso",
            [
                "burn_mailbox_to_pending",
                "pending_sso saved",
                "-> pending_sso",
                "mailbox burned to pending_sso",
            ],
        ),
        (
            "signup_no_sso",
            [
                "protocol no sso",
                "no sso cookies=",
                "sso_len=0",
                "browser-fetch no sso",
            ],
        ),
        (
            "turnstile_fail",
            [
                "turnstile 获取 token 失败",
                "turnstile 二次复用失败",
                "turnstile token 失败",
            ],
        ),
        ("next_action_404", ["server action not found"]),
        ("consent_404", ["consent http 404", "consent 失败"]),
        (
            "verify_email_fail",
            ["verifyemail fail", "code invalid", "验证码错误", "invalid code"],
        ),
        (
            "proxy_fail",
            [
                "cannot complete socks5",
                "tunnel failed",
                "proxy error",
                "curl: (97)",
                "curl: (28)",
            ],
        ),
        ("cf_block", ["attention required", "just a moment", "cf challenge"]),
        ("ui_desync", ["ui desync", "ui fallback desync"]),
        (
            "browser_disconnect",
            ["page disconnected", "与页面的连接已断开"],
        ),
        (
            "password_error",
            [
                "账号密码错误",
                "incorrect password",
                "wrong password",
                "invalid password",
            ],
        ),
        ("success", ["注册成功", "sso 有效", "immediate sso", "已写入号池"]),
    ]
    for name, kws in rules:
        hit = False
        for k in kws:
            if k.isascii():
                if k.lower() in tl:
                    hit = True
                    break
            elif k in t:
                hit = True
                break
        if not hit:
            continue
        if name == "success" and ("成功 0" in t or "失败 1" in t or "fail=1" in tl):
            continue
        return name
    if "success" in tl and "fail" in tl:
        return "mixed"
    return "unknown"
'''

mp = root / "tools" / "matrix_cross_run.py"
mt = mp.read_text(encoding="utf-8")
m = re.search(r"def classify\(logs: str\) -> str:.*?return \"unknown\"\n", mt, re.S)
if not m:
    raise SystemExit("classify block not found")
mt2 = mt[: m.start()] + NEW_CLASSIFY.strip() + "\n\n" + mt[m.end() :]
if "18r24: classify fixed" not in mt2:
    mt2 = mt2.replace(
        '"""',
        '"""\n18r24: classify fixed (no false email_login_fail on IMAP login OK); profile/sso classes.\n',
        1,
    )
mp.write_text(mt2, encoding="utf-8")
print("matrix classify patched")

gp = root / "grok_register_ttk.py"
gt = gp.read_text(encoding="utf-8")
gt2 = gt.replace(
    "def fill_profile_and_submit(timeout=120, log_callback=None, cancel_callback=None):",
    "def fill_profile_and_submit(timeout=210, log_callback=None, cancel_callback=None):",
    1,
)

marker = 'log_callback(f"[*] Turnstile 二次复用完成，回填长度={synced}")'
extend = '''log_callback(f"[*] Turnstile 二次复用完成，回填长度={synced}")
                        # 18r24: late CF token must still get a submit window
                        try:
                            deadline = max(deadline, time.time() + 75)
                        except Exception:
                            pass
                        if log_callback:
                            try:
                                log_callback("[*] profile submit window extended +75s after late Turnstile")
                            except Exception:
                                pass'''

if marker not in gt2:
    raise SystemExit("turnstile success marker missing")
# only extend inside fill_profile_and_submit function body
start = gt2.find("def fill_profile_and_submit")
end = gt2.find("\ndef wait_for_sso_cookie")
if start < 0 or end < 0:
    raise SystemExit("fill_profile bounds missing")
body = gt2[start:end]
if "profile submit window extended" not in body:
    body2 = body.replace(marker, extend)
    if body2 == body:
        raise SystemExit("no replacement in fill_profile body")
    gt2 = gt2[:start] + body2 + gt2[end:]
    print("fill_profile turnstile extend applied", body2.count("profile submit window extended"))
else:
    print("already extended")

gp.write_text(gt2, encoding="utf-8")
print("grok_register_ttk patched")

hp = root / "hybrid_register.py"
ht = hp.read_text(encoding="utf-8")
if "2026-07-19r24" not in ht[:3000]:
    ht = ht.replace(
        "2026-07-19r23",
        "2026-07-19r24: browser 资料页默认 timeout 210s；Turnstile 迟到后 +75s 再提交；matrix classify 不再误判 IMAP login OK。\n2026-07-19r23",
        1,
    )
    hp.write_text(ht, encoding="utf-8")
    print("hybrid changelog")

for p in (mp, gp, hp):
    py_compile.compile(str(p), doraise=True)
print("compile OK")

spec = importlib.util.spec_from_file_location("mcr", mp)
mcr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcr)
samples = {
    "imap_ok_then_profile": "[+] AOL IMAP login OK\n[-] 注册失败: 最终注册页资料填写失败\n任务结束。成功 0 | 失败 1",
    "sso_timeout": "[Debug] 最终页状态: final-page-no-submit:您正在登录\n[-] 注册失败: 等待超时：未获取到 sso cookie",
    "success": "[+] AOL IMAP login OK\n[+] 已写入号池本地\n任务结束。成功 1 | 失败 0",
    "turnstile_noise_success": "Turnstile 已通过\nAOL IMAP login OK\n任务结束。成功 1 | 失败 0",
}
for k, v in samples.items():
    print(k, "->", mcr.classify(v))
