# 18r30-lossfix: job-end wait_post 120s + Sub2 对账补齐; 减少 G2A/Sub2 丢号.

"""

18r28h: pending ONE login submit only + CF cannot skip re-register; pairs with pending_sso_recovery.

18r28g / 18r28f: code fetch uses grok_register_ttk.resolve_mailbox_provider (domain-first);

  pending login fail skips second login click (pending_sso_recovery).

Hybrid Grok registration: protocol RPC + browser tokens.



Used by Web/CLI when config register_mode == "hybrid".



Changelog:

- 18r28e: mailbox provider 按邮箱域名优先（outlook/* 不走 AOL preflight）；forced_email preflight 失败立即返回，不再同号空转 20 次；配合 pending 登录失败立刻改注册。

- 2026-07-19r26: browser SSO nudge 不再在仍含「完成注册」表单时跳转 grok.com（避免打断注册）

- 2026-07-19r29b: pending_sso 允许无密码占位写入（early_no_new_mail/验证码超时仍落盘+mail_token）；browser 同步 burn。

- 2026-07-19r25: NSFW socks fail -> direct fallback; Outlook early_no_new 110s

- 2026-07-19r24c: hybrid get_email_and_token 传入 log_callback，避免 Outlook acquire/preflight 静默卡住无日志。

- 2026-07-19r24b: pending 失败后队首轮转到 accounts_registered_pending_sso 末尾；8092 pending job importlib.reload 热加载；避免 doron28 堵死 count=1。

- 2026-07-19r24: browser 资料页默认 timeout 210s；Turnstile 迟到后 +75s 再提交；matrix classify 不再误判 IMAP login OK。

2026-07-19r23b: browser wait_for_sso_cookie signing-in nudge -> grok.com/accounts.x.ai to mint sso.

- 2026-07-19r23: browser success also mark_outlook_registered; Outlook strict post-send code only; form action # fix.

- 2026-07-19r22: VerifyEmail 在 SOCKS5/代理下 curl timeout 重试(最多3次, timeout 45/60s+backoff)；收码后瞬时网络失败不立刻 burn pending；主路径仍 注册→即时SSO→入池。

- 2026-07-19r21: Outlook early_no_new_mail(75s 无 post-send 信) 明文 burn→pending 并换号，避免空等满 180s；主路径不变。

- 2026-07-19r19: 修 code_timeout 假阳性：actual_send>=1 时禁止 protocol-rescue，故邮件轮询必须用满 180s（不再 45s short window）；

  short window 仅保留给「可协议救援」的虚假 browser_sent；日志明文打印真实 poll_timeout。

  主路径不变：注册→即时SSO→入池；pending 仅兜底。矩阵 10061 重试见 tools/matrix_cross_run.py。

- 2026-07-19r18: CreateEmail 并发双发锁（first-send-only）防 dual-code/验证码过多；保留 r17 switch cap / 明文日志 / rate-limit 换邮箱。

- 2026-07-19r17: UI fallback 卡验证码页快速 abort；无信+限流文案立即换邮箱；UI timeout 协议已验证时 40s；

# 2026-07-19r20: SignUp 200/sso_len=0 时多候选+强制 remint 再试，避免过早 UI stuck burn

  code_timeout 明文日志；主路径仍 注册→即时SSO→入池；pending 仅兜底。

- 2026-07-18r16: 检测 CreateEmail「验证码过多」于 protocol strings + browser UI 正文；

  限流后 burn_mailbox_to_pending 并从池删除，同一 register_one 内立即换下一邮箱(最多8次)；

  actual_send>=1 后禁止 protocol-rescue/二次 re-click 防双发；

  失败/验证码超时仍 burn→pending_sso；成功→hybrid+删池；日志明文无脱敏。

18r28d: mail_token lookup from outlook_token_cache + fix resolve_credentials misuse; rate_limit burn keeps mail_token

18r28b: _lookup_mail_token_from_pool for forced_email re-register

18r27: pending 行可带 mail_token(b64)；register_one_hybrid 支持 forced_email/mail_token/xai_password

供 pending auth_error 原号重注册；burn 时写入 mail_token 避免二次补丢 IMAP 凭据。

- 2026-07-18f: mailbox preflight/login failure logs include provider/auth/category/exception/raw (no masking); keep pool delete rules.

- 2026-07-18e: 池空即停 + 失败分类（success/fail/pending_sso/pool_empty/stopped）；

  pending_sso 独立统计；二次补 SSO 见 pending_sso_recovery.py。

- 2026-07-18b: 关闭 UI fallback；协议优先 SignUp；next-action 仅在拿到 SSO 时固化；

  CreateEmail 成功后禁止重复点击/协议重发，避免验证码过多限流；

  protocol 返回 RSC fragment/no-sso 时 live re-scrape 再协议重试；

  验证已过但无 SSO 时落盘 pending_sso 并从邮箱池移除，避免同邮箱反复发信。

- 2026-07-18: 修复 next-action 失效后 UI 卡在注册页：网络 hook 捕获 next-action；

  browser-fetch 失败后 live re-scrape 再试；UI fallback 接收 email/code 先推进邮箱/验证码页；

  验证已过但无 SSO 时单独落盘 accounts_registered_pending_sso.txt。

- 2026-07-17f: 修复 Web 停止竞态：打开注册页时传入 should_stop，浏览器被停止关闭后

  不再继续 new_tab；停止操作不计为注册失败，也不输出误导性的 NoneType 堆栈。

- 2026-07-17e: 协议 curl 超时(0 bytes)根因修复：跳过已有候选时的 curl chunk discover；

  SignUp 超时降至 18s；curl 超时/status=0 立即停止协议重试（不再试 hardcoded 死哈希）；

  协议失败后优先浏览器同源 fetch SignUp，再 UI 点提交；详细网络路径日志不脱敏。

- 2026-07-17d: SignUp 提交前强制刷新 castle（不再复用 CreateEmail 旧 token）；

  200 无 sso 详细日志（body/set-cookie/hints）；协议失败后浏览器 UI 资料提交兜底；

  注册成功/登录失败邮箱从 AOL/Outlook 账号池文件永久删除。

- 2026-07-17c: 邮箱登录失败自动换下一个（最多 20 次）；preflight 预登录；

  CreateEmail 后等 3s 再查信；AOL/Outlook 扫 ALL 文件夹（非仅 Inbox/Junk）。

  修复缩进损坏导致 IndentationError 无法启动。

- 2026-07-17b: CreateEmail 发信证据门禁 + since_ts 查信。



2026-07-18g: 隔离死 next-action；坏 capture 不加载；主路径保持 注册→即时SSO→入池，pending 仅兜底。

2026-07-18h: 修复 _is_protocol_network_dead 误返回 SUCCESS；恢复原始 next-action 候选顺序（hook→scrape→capture）。

2026-07-18i: 明确主流程不变：协议/browser-fetch 拿到 SSO 后立刻 schedule_post_registration 入池；

              pending_sso 只在协议+browser-fetch 都无 SSO 时兜底；不启用 UI fallback。

              scrape 回退恢复见 token_harvester（createUserAndSession + legacy markers）。

2026-07-18j: 实跑修复：early/scrape 丢弃已知死 next-action；支持 scrape 多候选，避免 7f7f6cee 独占主路径。

2026-07-18k: 修复误杀 live SignUp hash 7f7f6cee：协议 200 仅 RSC shell/业务错误不再 quarantine；

              browser-fetch run_js 改为闭包传参（DrissionPage 不注入 arguments 给 async IIFE）；

              识别 turnstile/业务错误，避免把唯一 live next-action 标死导致 no candidates。

              主流程仍是 注册→即时SSO→入池；pending 仅兜底。

2026-07-18l: 重新启用 UI fallback 为最后兜底：协议 SignUp → browser-fetch → UI profile submit → pending_sso。

2026-07-18r3: pending bad_password/auth_error 移出 pending 后 hybrid 重新注册（非只删号）；主路径仍是 注册→即时SSO→入池；UI fallback 最后。

2026-07-18r4: CreateEmail 前强制等待邮箱输入框；点「使用邮箱注册」后轮询/硬刷新/重开 signup；no-input 不误记为已发信；修复 re-register 空白页失败。

- 2026-07-18n: pending_sso 登录页点击「使用邮箱登录」；UI fallback 验证码后继续推进/报错可见；speed 补丁保留。主路径仍 注册→即时SSO→入池。

- 2026-07-18r4: CreateEmail 前强制等待邮箱输入框；点「使用邮箱注册」后轮询/硬刷新/重开 signup；no-input 不误记为已发信；修复 re-register 空白页失败。

2026-07-18o: pending 两步登录(email→下一步→password)；UI fallback 验证码后更稳进 profile；主路径仍 注册→即时SSO→入池；pending 仅兜底。

2026-07-18r: pending 二次补：提交后等待/CF 未过不跳转；密码错误走重新注册而非只删号。

              主路径不变：协议/browser-fetch 拿到 SSO 立刻 schedule_post 入池；UI 不抢主路径、不重复发信；

              仅在 protocol+browser-fetch 均无 SSO 时调用 submit_profile_and_wait_sso；仍无 SSO 才落盘 pending。

2026-07-18r6: CreateEmail 不再把 seen_status_unknown 当发信成功；仅 2xx/进入验证码页算 sent；转圈卡住允许一次二次点击；pending 仅 SSO/注册真正成功后才从 accounts_registered_pending_sso.txt 移出。

2026-07-18r5: SignUp 强制 clear+mint fresh castle（不再优先返回 CreateEmail capture）；日志 same_as_old_head；UI fallback 保留字母数字验证码；卡在确认邮箱时 prepare_profile 后快速失败。



2026-07-18r7: dual-code root fix — after protocol VerifyEmail, UI/prepare never open_signup+email re-submit;

              AOL dual-code prefers Inbox; VerifyEmail can retry alt codes; shorter mint timeouts.

              Main path still register→immediate SSO→pool; UI last resort and never re-sends code.

2026-07-18r8: CreateEmail freeze after first net hit; no hybrid re-click when browser_sent;

2026-07-18r12: protocol restore from r9 observe-only CreateEmail hook; no fake short-circuit/form disable;

              pending_sso only when signup confirmed (UI profile submitted); else unconfirmed fail keep mailbox;

              UI desync fast-abort after protocol VerifyEmail. Main path still register→immediate SSO→pool.

2026-07-18r10: dual-code true-send lock (hook short-circuit) + CPA consent scan budget + staged SSO materialize logs;

              CreateEmail status logs actual_send/blocked_dup; main path still register→immediate SSO→pool.

2026-07-18r9: weak castle early-abort (no 32s 744 spam); mint windows 6s/4s; reuse CreateEmail IBYIll for SignUp SSO path; keep freeze-reclick dual-code fix.

              weak castle rejected; mint timeout 18s + retry once; alt-code UI stuck recovery.

              Main path still register→immediate SSO→pool; UI last; pending only after real success remove.

2026-07-18r14: CreateEmail browser_sent requires actual_send/net_hits; protocol rescue after silent browser send; remove mailbox on code timeout; redact mail_token logs; main path still register->immediate SSO->pool.

2026-07-18r14b: full unredacted logs (mail_token plaintext); success->accounts_hybrid+remove pool; fail/code_timeout->pending_sso file+remove pool; profile/password minted early for pending lines.

- 2026-07-18r15: Outlook Graph folder dedupe + adaptive priority poll (inbox/junk/deleted first;

  full scan every 3rd round). Keep r14b burn/pending/unredacted rules. Matrix continues.

"""

from __future__ import annotations

from pathlib import Path



import os

import re

import time

import traceback

import uuid

from pathlib import Path

from typing import Callable, Optional



ROOT = Path(__file__).resolve().parent



from browser.token_harvester import BrowserTokenSession  # noqa: E402

from protocol.grpc_client import AuthManagementClient  # noqa: E402

from protocol.session import ProtocolSession  # noqa: E402

from pending_sso_recovery import (  # noqa: E402

    STATUS_FAIL,

    STATUS_PENDING_SSO,

    STATUS_POOL_EMPTY,

    STATUS_STOPPED,

    STATUS_SUCCESS,

    is_pool_empty_error,

    normalize_result,

    result as _result,

    run_pending_sso_recovery_job,

)







# Known-dead SignUp next-action hashes (404 / RSC shell only). Never prefer these.

DEAD_NEXT_ACTIONS = {

    # NOTE: 7f7f6cee... is CURRENT live SignUp createServerReference (2026-07-18).

    # Only quarantine on true 404 / "Server action not found", never on RSC shell.

    "7f50061dd2f5b389a530e4a048d5fdf0c48d1d9259",

    "7f0a91ba5242676db585f47da85cf4b6088e8920ae",

}





def _norm_action(val: str) -> str:

    return str(val or "").strip().lower()





def is_dead_next_action(val: str) -> bool:

    v = _norm_action(val)

    if not v:

        return True

    if v in DEAD_NEXT_ACTIONS:

        return True

    for bad in DEAD_NEXT_ACTIONS:

        if len(bad) >= 40 and v == bad:

            return True

    return False





def quarantine_dead_capture(action: str = "", log: Callable[[str], None] | None = None) -> None:

    """Rename capture file if it stores a known-dead next-action."""

    try:

        import json

        rpc = ROOT / "capture_out" / "rpc"

        path = rpc / "03_SignUpSubmit.req.headers.json"

        if not path.is_file():

            return

        data = json.loads(path.read_text(encoding="utf-8"))

        cur = str((data or {}).get("next-action") or (data or {}).get("Next-Action") or "").strip()

        target = (action or cur).strip()

        if not target:

            return

        if not is_dead_next_action(target) and not is_dead_next_action(cur):

            return

        if not is_dead_next_action(target):

            target = cur

        bak = rpc / f"03_SignUpSubmit.req.headers.json.bak_dead_{target[:16]}_{int(time.time())}"

        path.replace(bak)

        if log:

            log(f"[hybrid] quarantined dead capture next-action={target[:20]}... -> {bak.name}")

    except Exception as exc:

        if log:

            log(f"[hybrid] quarantine capture fail: {exc}")



def load_next_action_from_capture() -> str:

    rpc = ROOT / "capture_out" / "rpc"

    for name in ("03_SignUpSubmit.req.headers.json",):

        p = rpc / name

        if p.is_file():

            try:

                import json



                h = json.loads(p.read_text(encoding="utf-8"))

                act = (h.get("next-action") or h.get("Next-Action") or "").strip()

                if act and not is_dead_next_action(act):

                    return act

                if act and is_dead_next_action(act):

                    quarantine_dead_capture(act)

            except Exception:

                pass

    if rpc.is_dir():

        import json



        for f in rpc.glob("*.req.headers.json"):

            try:

                h = json.loads(f.read_text(encoding="utf-8"))

                act = (h.get("next-action") or "").strip()

                if act and not is_dead_next_action(act):

                    return act

            except Exception:

                pass

    return ""







def save_next_action_to_capture(action: str, log: Callable[[str], None] | None = None) -> None:

    """Persist a known-good next-action so later runs prefer a live working hash."""

    act = (action or "").strip()

    if not act or is_dead_next_action(act):

        if log and act:

            log(f"[hybrid] refuse saving dead next-action hash={act[:20]}...")

        return

    try:

        import json



        rpc = ROOT / "capture_out" / "rpc"

        rpc.mkdir(parents=True, exist_ok=True)

        path = rpc / "03_SignUpSubmit.req.headers.json"

        data = {}

        if path.is_file():

            try:

                data = json.loads(path.read_text(encoding="utf-8"))

            except Exception:

                data = {}

        if not isinstance(data, dict):

            data = {}

        data["next-action"] = act

        data["Next-Action"] = act

        data["_saved_by"] = "hybrid_register"

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if log:

            log(f"[hybrid] saved working next-action hash={act[:20]}... len={len(act)}")

    except Exception as exc:

        if log:

            log(f"[hybrid] save next-action fail: {exc}")





def _account_scan_dirs() -> list[Path]:

    """Dirs that may contain successful Grok account dumps."""

    dirs = [

        ROOT,

        Path.home() / "Desktop" / "Gark",

        Path.home() / "Desktop" / "Grok",

        Path.home() / "Desktop" / "grok-regkit",

        Path(r"C:/Users/zhang/Desktop/Gark"),

    ]

    out: list[Path] = []

    seen: set[str] = set()

    for d in dirs:

        try:

            key = str(d.resolve()) if d.exists() else str(d)

        except Exception:

            key = str(d)

        if key in seen:

            continue

        seen.add(key)

        out.append(d)

    return out





def _registry_path() -> Path:

    return ROOT / "registered_emails_registry.txt"





def load_registered_emails() -> set[str]:

    """Emails already saved as successful Grok registrations (multi-dir + local registry)."""

    out: set[str] = set()

    reg = _registry_path()

    if reg.is_file():

        try:

            for line in reg.read_text(encoding="utf-8", errors="ignore").splitlines():

                email = (line.split("----")[0] or line.strip() or "").strip().lower()

                if email and "@" in email:

                    out.add(email)

        except Exception:

            pass

    patterns = ("accounts*.txt", "accounts_hybrid_*.txt", "accounts_browser_*.txt")

    for base in _account_scan_dirs():

        if not base.exists() or not base.is_dir():

            continue

        for pat in patterns:

            try:

                for pth in base.glob(pat):

                    try:

                        for line in pth.read_text(encoding="utf-8", errors="ignore").splitlines():

                            email = (line.split("----")[0] or "").strip().lower()

                            if email and "@" in email:

                                out.add(email)

                    except Exception:

                        continue

            except Exception:

                continue

    return out





def remember_registered_email(email: str, log: Callable[[str], None] | None = None) -> None:

    """Append email to local registry so future runs skip it even if accounts file is elsewhere."""

    em = (email or "").strip().lower()

    if not em or "@" not in em:

        return

    try:

        path = _registry_path()

        existing: set[str] = set()

        if path.is_file():

            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():

                e = (line.split("----")[0] or line.strip() or "").strip().lower()

                if e:

                    existing.add(e)

        if em not in existing:

            with path.open("a", encoding="utf-8", newline="\n") as f:

                f.write(em + "\n")

            if log:

                log(f"[hybrid] registry +1 registered email: {em} (total_was={len(existing)})")

    except Exception as exc:

        if log:

            log(f"[hybrid] registry write fail: {exc}")





def mark_outlook_registered(email: str, log: Callable[[str], None] | None = None) -> None:

    """Mark registered and permanently remove mailbox from AOL/Outlook pools."""

    remember_registered_email(email, log)

    remove_mailbox_from_pool(email, reason="registered", log=log)





def remove_mailbox_from_pool(

    email: str,

    reason: str = "removed",

    log: Callable[[str], None] | None = None,

) -> None:

    """Permanently delete email from AOL/Outlook account pool files."""

    em = (email or "").strip()

    if not em:

        return

    em_l = em.lower()

    try:

        from grok_register_ttk import config as _cfg

    except Exception:

        _cfg = {}



    # AOL / AIM

    try:

        import aol_mail as am



        pool = getattr(am, "_POOL", None)

        if pool is None:

            try:

                pool = am.get_pool(_cfg, log_callback=log)

            except Exception:

                pool = getattr(am, "_POOL", None)

        if pool is not None and hasattr(pool, "remove_account"):

            pool.remove_account(em, reason=reason)

        elif pool is not None:

            # fallback release bad

            try:

                pool.release(em, ok=False, bad=True)

            except Exception:

                pass

    except Exception as exc:

        if log:

            log(f"[hybrid] AOL pool remove fail email={em}: {exc}")



    # Outlook / Hotmail / Live

    try:

        import outlook_mail as om



        pool = getattr(om, "_POOL", None)

        if pool is None:

            try:

                pool = om.get_pool(_cfg, log_callback=log)

            except Exception:

                pool = getattr(om, "_POOL", None)

        if pool is not None and hasattr(pool, "remove_account"):

            pool.remove_account(em, reason=reason)

        elif pool is not None:

            with om._POOL_LOCK:

                for acc in list(pool.accounts):

                    if acc.identity() == em_l:

                        acc.status = "registered" if reason == "registered" else "bad"

                        acc.cooldown_until = time.time() + 86400 * 365

                        if log:

                            log(f"[hybrid] Outlook marked {acc.status}: {em}")

                        break

    except Exception as exc:

        if log:

            log(f"[hybrid] Outlook pool remove fail email={em}: {exc}")









def _encode_pending_mail_token(mail_token: str) -> str:

    tok = str(mail_token or "").strip()

    if not tok:

        return ""

    import base64

    return "b64:" + base64.urlsafe_b64encode(tok.encode("utf-8")).decode("ascii")





def save_to_pending_sso_file(

    email: str,

    password: str,

    reason: str = "pending_sso",

    log: Callable[[str], None] | None = None,

    mail_token: str = "",

) -> Path | None:

    """Append email----password----reason[----b64:mail_token] to pending files."""

    em = (email or "").strip()

    pw = (password or "").strip()

    if not em:

        if log:

            log(f"[hybrid] skip pending_sso save missing email reason={reason}")

        return None

    if not pw:

        # 18r29b: code-timeout / early_no_new_mail may burn before profile password exists

        pw = "PENDING_NO_PW"

        if log:

            log(f"[hybrid] pending_sso password placeholder used email={em} reason={reason}")

    tag = (reason or "pending_sso").strip() or "pending_sso"

    if not tag.startswith("pending_sso"):

        tag = f"pending_sso:{tag}"

    tok_field = _encode_pending_mail_token(mail_token)

    if tok_field:

        line = f"{em}----{pw}----{tag}----{tok_field}"

    else:

        line = f"{em}----{pw}----{tag}"

    pending_fixed = ROOT / "accounts_registered_pending_sso.txt"

    try:

        with pending_fixed.open("a", encoding="utf-8") as pf:

            pf.write(line + "\n")

        stamp = time.strftime("%Y%m%d_%H%M%S")

        pending_stamp = ROOT / f"accounts_no_sso_{stamp}.txt"

        with pending_stamp.open("a", encoding="utf-8") as pf:

            pf.write(line + "\n")

        if log:

            log(

                f"[hybrid] pending_sso saved email={em} reason={tag} "

                f"file={pending_fixed.name} stamp={pending_stamp.name} "

                f"line={line}"

            )

        return pending_fixed

    except Exception as exc:

        if log:

            log(f"[hybrid] pending_sso save fail email={em} reason={tag}: {exc}")

        return None







def detect_create_email_rate_limit(*parts) -> tuple[bool, str]:

    """Detect xAI CreateEmail rate-limit from protocol strings / UI body (plain text, no redact)."""

    chunks: list[str] = []

    for p in parts:

        if p is None:

            continue

        if isinstance(p, (list, tuple, set)):

            for x in p:

                if x is None:

                    continue

                chunks.append(str(x))

        else:

            chunks.append(str(p))

    joined = " ".join(chunks)

    if not joined.strip():

        return False, ""

    low = joined.lower()

    needles = (

        "验证码过多",

        "发送到此邮箱的验证码过多",

        "too many verification",

        "too many codes",

        "too many code",

        "too_many",

        "too many",

        "rate limit",

        "rate_limit",

        "rate-limited",

        "try again later",

        "please try again in",

    )

    hit = None

    for n in needles:

        if n.lower() in low or n in joined:

            hit = n

            break

    # ICU plural message often contains minute/minutes + retry/重试 together

    if hit is None and (

        ("minute" in low or "minutes" in low or "分钟" in joined)

        and ("retry" in low or "重试" in joined or "too many" in low or "过多" in joined)

    ):

        hit = "minute+retry"

    if hit is None:

        return False, ""

    # Keep full joined for debug (cap extreme length only)

    detail = joined if len(joined) <= 1200 else (joined[:1200] + "...(trunc)")

    return True, f"needle={hit!r} detail={detail}"





def handle_create_email_rate_limited(

    email: str,

    password: str,

    *,

    log: Callable[[str], None] | None = None,

    source: str = "unknown",

    evidence: str = "",

    mail_token: str = "",

) -> dict:

    """Burn mailbox to pending_sso and return PENDING so job can switch / stats stay clear."""

    if log:

        log(

            f"[hybrid] CreateEmail RATE_LIMITED source={source} email={email} "

            f"password={password!r} evidence={evidence} mail_token_len={len(str(mail_token or ''))}"

        )

    try:

        burn_mailbox_to_pending(

            email,

            password or "",

            reason="create_email_rate_limited",

            log=log,

            mail_token=mail_token,

        )

    except Exception as exc:

        if log:

            log(f"[hybrid] rate-limit burn fail email={email}: {exc}")

        try:

            remove_mailbox_from_pool(email, reason="create_email_rate_limited", log=log)

        except Exception as rm_exc:

            if log:

                log(f"[hybrid] rate-limit remove fail email={email}: {rm_exc}")

    return _result(

        STATUS_PENDING_SSO,

        email=email,

        detail="create_email_rate_limited",

        rate_limited=True,

        switch_mailbox=True,

    )





def burn_mailbox_to_pending(

    email: str,

    password: str,

    reason: str,

    log: Callable[[str], None] | None = None,

    mail_token: str = "",

) -> None:

    """Remove mailbox from AOL/Outlook pool and queue for secondary SSO recovery."""

    save_to_pending_sso_file(

        email, password, reason=reason, log=log, mail_token=mail_token

    )

    try:

        remove_mailbox_from_pool(email, reason=reason, log=log)

        if log:

            log(

                f"[hybrid] mailbox burned to pending_sso email={email} reason={reason} "

                f"mail_token_len={len(str(mail_token or ''))}"

            )

    except Exception as rm_exc:

        if log:

            log(f"[hybrid] burn mailbox remove fail email={email}: {rm_exc}")









def _mailbox_provider_is_aol(email: str, configured_provider: str = "") -> bool:

    """Route mailbox by email domain first; global provider only for ambiguous domains.



    Bug 18r28d: when UI email source=AOL, forced Outlook re-register incorrectly called

    aol_mail.preflight -> "AOL missing password for xxx@outlook.com".

    """

    em = str(email or "").strip().lower()

    prov = str(configured_provider or "").strip().lower()

    aol_suffixes = (

        "@aol.com", "@aim.com", "@verizon.net", "@love.com",

        "@ygm.com", "@games.com", "@wow.com",

    )

    outlook_suffixes = (

        "@outlook.com", "@hotmail.com", "@live.com", "@msn.com",

        "@office365.com", "@outlook.jp", "@outlook.fr", "@hotmail.co.uk",

    )

    if em.endswith(aol_suffixes):

        return True

    if em.endswith(outlook_suffixes):

        return False

    try:

        import aol_mail as _am

        if _am.is_aol_provider(prov):

            return True

    except Exception:

        pass

    if prov in {"aol", "aol_mail", "aol.com", "aim", "verizon_aol"}:

        return True

    if prov in {"outlook", "microsoft", "hotmail", "graph", "ms", "outlook_mail"}:

        return False

    return False





def _lookup_mail_token_from_pool(email: str, log=None) -> str:

    """Find IMAP/Graph mail_token for email from pools, outlook_token_cache, config, files.



    18r28d: recover Graph tokens from outlook_token_cache.json even after burn-remove;

    do NOT call AolAccountPool.resolve_credentials(email) (needs token_blob).

    18r28b: pending re-register needs original mailbox credentials; older pending

    lines may lack the 4th b64 mail_token field, so recover from live pools.

    """

    import json as _json

    from pathlib import Path as _Path



    em = str(email or "").strip().lower()

    if not em:

        return ""

    lg = log or (lambda m: None)



    def _from_aol_account(acc) -> str:

        try:

            pw = str(getattr(acc, "password", "") or "").strip()

            totp = str(getattr(acc, "totp_secret", "") or getattr(acc, "totp", "") or "").strip()

            if pw and totp:

                return f"{pw}----{totp}"

            return pw

        except Exception:

            return ""



    def _outlook_blob_from_acc(acc) -> str:

        try:

            if isinstance(acc, dict):

                data = {

                    "email": str(acc.get("email") or acc.get("user") or em),

                    "access_token": str(acc.get("access_token") or ""),

                    "refresh_token": str(acc.get("refresh_token") or acc.get("token") or acc.get("mail_token") or ""),

                    "access_expires_at": acc.get("access_expires_at") or 0,

                    "client_id": str(acc.get("client_id") or ""),

                    "password": str(acc.get("password") or ""),

                    "totp_secret": str(acc.get("totp_secret") or acc.get("totp") or ""),

                }

            else:

                data = {

                    "email": str(getattr(acc, "email", "") or em),

                    "access_token": str(getattr(acc, "access_token", "") or ""),

                    "refresh_token": str(getattr(acc, "refresh_token", "") or ""),

                    "access_expires_at": getattr(acc, "access_expires_at", 0) or 0,

                    "client_id": str(getattr(acc, "client_id", "") or ""),

                    "password": str(getattr(acc, "password", "") or ""),

                    "totp_secret": str(getattr(acc, "totp_secret", "") or ""),

                }

            # Prefer Graph token JSON when refresh/access present.

            if data.get("refresh_token") or data.get("access_token"):

                return _json.dumps(data, ensure_ascii=False)

            if data.get("password") and data.get("totp_secret"):

                return _json.dumps(data, ensure_ascii=False)

            if data.get("password"):

                return _json.dumps(data, ensure_ascii=False)

            return ""

        except Exception:

            return ""



    def _norm_line_token(line: str):

        s = str(line or "").strip()

        if not s or s.startswith("#"):

            return None

        for sep in ("----", "|", "\t"):

            if sep in s and "@" in s.split(sep, 1)[0]:

                parts = [x.strip() for x in s.split(sep) if str(x).strip()]

                if len(parts) >= 2 and parts[0].lower() == em:

                    rest = parts[1:]

                    # If looks like email----client_id----refresh or email----refresh

                    if len(rest) >= 2 and len(rest[0]) == 36 and "-" in rest[0] and len(rest[1]) > 40:

                        return _json.dumps(

                            {"email": em, "client_id": rest[0], "refresh_token": rest[1]},

                            ensure_ascii=False,

                        )

                    if len(rest) == 1 and len(rest[0]) > 40:

                        return _json.dumps(

                            {"email": em, "refresh_token": rest[0]},

                            ensure_ascii=False,

                        )

                    if len(rest) >= 2 and em.endswith(("@outlook.com", "@hotmail.com", "@live.com", "@msn.com")):

                        data = {

                            "email": em,

                            "password": rest[0],

                            "totp_secret": rest[1].replace(" ", ""),

                        }

                        if len(rest) >= 3 and len(rest[2]) == 36:

                            data["client_id"] = rest[2]

                        return _json.dumps(data, ensure_ascii=False)

                    # AOL / generic: password----totp

                    return "----".join(rest)

        if s.lower().startswith(em + ":"):

            return s.split(":", 1)[1].strip()

        return None



    # 1) outlook_token_cache.json (survives pool burn)

    try:

        cache_paths = [

            _Path(__file__).resolve().parent / "outlook_token_cache.json",

            _Path(__file__).resolve().parent / "data" / "outlook_token_cache.json",

        ]

        try:

            import grok_register_ttk as _eng



            cfg = getattr(_eng, "config", {}) or {}

            cf = str(cfg.get("outlook_token_cache") or "").strip()

            if cf:

                cache_paths.insert(0, _Path(cf) if _Path(cf).is_absolute() else (_Path(__file__).resolve().parent / cf))

        except Exception:

            pass

        for cp in cache_paths:

            if not cp.is_file():

                continue

            try:

                blob = _json.loads(cp.read_text(encoding="utf-8", errors="replace"))

            except Exception as e:

                lg(f"[hybrid] outlook_token_cache read fail {cp}: {e}")

                continue

            if not isinstance(blob, dict):

                continue

            entry = blob.get(em) or blob.get(email) or blob.get(str(email or "").strip())

            if not entry and isinstance(blob, dict):

                for k, v in blob.items():

                    if str(k).strip().lower() == em and isinstance(v, dict):

                        entry = v

                        break

            if isinstance(entry, dict) and (entry.get("refresh_token") or entry.get("access_token")):

                data = {

                    "email": em,

                    "access_token": str(entry.get("access_token") or ""),

                    "refresh_token": str(entry.get("refresh_token") or ""),

                    "access_expires_at": entry.get("access_expires_at") or 0,

                    "client_id": str(entry.get("client_id") or ""),

                }

                tok = _json.dumps(data, ensure_ascii=False)

                lg(f"[hybrid] mail_token from outlook_token_cache email={em} file={cp.name} rt_len={len(data['refresh_token'])}")

                return tok

    except Exception as exc:

        lg(f"[hybrid] outlook_token_cache lookup skip: {exc}")



    # 2) AOL pool object (iterate accounts ONLY — resolve_credentials needs token_blob)

    try:

        import aol_mail as _am

        import grok_register_ttk as engine



        pool = None

        try:

            pool = _am.get_pool(getattr(engine, "config", None), force_reload=True)

        except TypeError:

            try:

                pool = _am.get_pool(force_reload=True)

            except Exception as e:

                lg(f"[hybrid] aol get_pool: {e}")

                pool = None

        except Exception as e:

            lg(f"[hybrid] aol get_pool: {e}")

            pool = None

        if pool is not None:

            accs = getattr(pool, "accounts", None) or []

            for acc in list(accs):

                ae = str(getattr(acc, "email", "") or "").strip().lower()

                if ae == em:

                    tok = _from_aol_account(acc)

                    if tok:

                        lg(f"[hybrid] mail_token from AolAccountPool email={em}")

                        return tok

    except Exception as exc:

        lg(f"[hybrid] aol pool lookup skip: {exc}")



    # 3) Outlook live pool

    try:

        import outlook_mail as _om

        import grok_register_ttk as engine



        pool = None

        try:

            pool = _om.get_pool(getattr(engine, "config", None), force_reload=True)

        except TypeError:

            try:

                pool = _om.get_pool(force_reload=True)

            except Exception:

                pool = None

        except Exception as e:

            lg(f"[hybrid] outlook get_pool: {e}")

            pool = None

        if pool is not None:

            accs = getattr(pool, "accounts", None) or getattr(pool, "items", None) or []

            if isinstance(accs, dict):

                accs = list(accs.values())

            for acc in list(accs or []):

                if isinstance(acc, dict):

                    ae = str(acc.get("email") or acc.get("user") or "").strip().lower()

                    if ae == em:

                        tok = _outlook_blob_from_acc(acc)

                        if tok:

                            lg(f"[hybrid] mail_token from outlook dict pool email={em}")

                            return tok

                else:

                    ae = str(getattr(acc, "email", "") or "").strip().lower()

                    if ae == em:

                        tok = _outlook_blob_from_acc(acc)

                        if tok:

                            lg(f"[hybrid] mail_token from outlook pool email={em}")

                            return tok

    except Exception as exc:

        lg(f"[hybrid] outlook pool lookup skip: {exc}")



    # 4) config blobs

    try:

        import grok_register_ttk as engine



        cfg = getattr(engine, "config", {}) or {}

        for key in ("aol_accounts", "outlook_accounts", "aol_account_list", "outlook_account_list", "email_accounts"):

            blob = cfg.get(key) or ""

            lines = blob if isinstance(blob, list) else str(blob).splitlines()

            for line in lines:

                t = _norm_line_token(str(line))

                if t:

                    lg(f"[hybrid] mail_token from config.{key} email={em}")

                    return t

    except Exception as exc:

        lg(f"[hybrid] config pool lookup skip: {exc}")



    # 5) on-disk account files

    root_dir = _Path(__file__).resolve().parent

    for name in (

        "aol_accounts.txt",

        "outlook_accounts.txt",

        "accounts_aol.txt",

        "accounts_outlook.txt",

        "email_pool.txt",

    ):

        fp = root_dir / name

        if not fp.is_file():

            continue

        try:

            for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():

                t = _norm_line_token(line)

                if t:

                    lg(f"[hybrid] mail_token from {name} email={em}")

                    return t

        except Exception:

            pass



    lg(f"[hybrid] mail_token lookup MISS email={em}")

    return ""







def register_one_hybrid(

    *,

    log: Callable[[str], None],

    proxy: str = "",

    user_agent: str = "",

    next_action: str = "",

    accounts_file: Path,

    should_stop: Optional[Callable[[], bool]] = None,

    post_success: bool = True,

    forced_email: str = "",

    forced_mail_token: str = "",

    forced_xai_password: str = "",

) -> dict:

    """Register one account via hybrid path.



    Returns dict status: success|fail|pending_sso|pool_empty|stopped

    Each account uses its own browser session (open at start, close at end).

    forced_email/forced_mail_token: reuse a specific mailbox (pending re-register).

    forced_xai_password: optional preferred xAI password for the profile.

    """

    email = ""

    password = ""

    given = ""

    family = ""

    from grok_register_ttk import (

        build_profile,

        get_email_and_token,

        get_oai_code,

        schedule_post_registration,

    )



    stop = should_stop or (lambda: False)

    t0 = time.time()

    action = (next_action or load_next_action_from_capture() or "").strip()



    try:

        with BrowserTokenSession(log=log) as browser:

            if stop():

                return _result(STATUS_STOPPED)

            log("[browser] open signup page for this account")

            browser.open_signup(cancel_callback=stop)

            browser.install_network_hook()

            # Early scrape is advisory only. Never keep a known-dead hash into main SignUp path.

            if action and is_dead_next_action(action):

                log(f"[hybrid] drop dead early next-action hash={action[:20]}...")

                quarantine_dead_capture(action, log)

                action = ""

            scraped_early = ""

            try:

                scraped_early = (browser.scrape_next_action() or "").strip()

            except Exception as early_scrape_exc:

                log(f"[hybrid] early scrape next-action fail: {early_scrape_exc}")

            if scraped_early and is_dead_next_action(scraped_early):

                log(f"[hybrid] drop dead scraped next-action hash={scraped_early[:20]}...")

                scraped_early = ""

            action = action or scraped_early or action

            if action and is_dead_next_action(action):

                log(f"[hybrid] early next-action still dead; clear for post-turnstile live resolve")

                action = ""

            log(f"[hybrid] next-action ready len={len(action or '')} value={action or ''}")



            registered = load_registered_emails()

            email, mail_token = "", ""

            force_em = str(forced_email or "").strip()

            force_tok = str(forced_mail_token or "").strip()

            force_pw = str(forced_xai_password or "").strip()

            for _try in range(20):

                if stop():

                    return _result(STATUS_STOPPED)

                if force_em:

                    email = force_em

                    mail_token = force_tok

                    if not mail_token:

                        # try rebuild token from live pool if mailbox not yet burned

                        try:

                            mail_token = _lookup_mail_token_from_pool(email, log=log)

                        except Exception as look_exc:

                            log(f"[hybrid] forced_email pool token lookup fail email={email}: {look_exc}")

                            mail_token = ""

                    if not mail_token:

                        log(

                            f"[hybrid] forced_email missing mail_token email={email} "

                            f"— cannot re-register without IMAP/Graph credentials"

                        )

                        return _result(

                            STATUS_FAIL,

                            email=email,

                            detail="forced_email_missing_mail_token",

                        )

                    log(

                        f"[hybrid] using forced_email={email} mail_token_len={len(mail_token)} "

                        f"forced_xai_password_len={len(force_pw)}"

                    )

                else:

                    try:

                        email, mail_token = get_email_and_token(log_callback=log)

                    except Exception as get_exc:

                        log(f"[hybrid] 获取邮箱失败(池内可能都登录失败): {get_exc}")

                        if is_pool_empty_error(get_exc):

                            return _result(STATUS_POOL_EMPTY, detail=str(get_exc))

                        email, mail_token = "", ""

                        continue

                    if not email:

                        log("[hybrid] no fresh email available (pool exhausted / all registered?)")

                        return _result(STATUS_POOL_EMPTY, detail="no fresh email")

                if email.lower() in registered and not force_em:

                    log(f"[hybrid] skip already-registered local email: {email}")

                    try:

                        em_l = email.lower()

                        from grok_register_ttk import config as _cfg_skip

                        if em_l.endswith(("@aol.com", "@aim.com")):

                            import aol_mail as om_skip

                            om_skip.get_pool(_cfg_skip, log_callback=log).release(email, ok=True)

                        else:

                            import outlook_mail as om_skip

                            pool = om_skip.get_pool(_cfg_skip, log_callback=log)

                            pool.release(email, ok=True)

                            mark_outlook_registered(email, log)

                    except Exception as rel_exc:

                        log(f"[hybrid] release/skip email: {rel_exc}")

                    email, mail_token = "", ""

                    continue

                if email.lower() in registered and force_em:

                    log(

                        f"[hybrid] forced_email already in local registered list; "

                        f"continue re-register attempt anyway email={email}"

                    )



                log(

                    f"[hybrid] email={email} mail_token_len={len(str(mail_token or ''))} "

                    f"mail_token={mail_token}"

                )



                # Pre-login mailbox BEFORE CreateEmail; fail -> next email

                try:

                    from grok_register_ttk import config as _cfg_pre, get_email_provider as _gep



                    prov = str(_gep() or "").strip().lower()

                    em_l = (email or "").lower()

                    # 18r28e: domain-first; never route @outlook to AOL because global source=AOL

                    is_aol = _mailbox_provider_is_aol(email, prov)

                    log(

                        f"[hybrid] mailbox preflight route email={email} "

                        f"is_aol={int(is_aol)} configured_provider={prov or '-'}"

                    )

                    if is_aol:

                        import aol_mail as am

                        pre = am.preflight_mailbox(

                            _cfg_pre, mail_token, email, log_callback=log, top=5

                        )

                        log(

                            f"[hybrid] AOL pre-login OK email={email} "

                            f"auth={pre.get('auth')} total={pre.get('total')} "

                            f"counts={pre.get('folder_counts')} "

                            f"scanned_folders={pre.get('scanned_folders')} top={pre.get('top')}"

                        )

                    else:

                        import outlook_mail as om

                        pre = om.preflight_mailbox(

                            _cfg_pre, mail_token, email, log_callback=log, top=5

                        )

                        log(

                            f"[hybrid] Outlook pre-login OK email={email} "

                            f"auth={pre.get('auth')} "

                            f"counts={pre.get('folder_counts')} total={pre.get('total')} "

                            f"scanned_folders={pre.get('scanned_folders')} top={pre.get('top')}"

                        )

                    break

                except Exception as pre_exc:

                    em_l2 = (email or "").lower()

                    is_aol_fail = _mailbox_provider_is_aol(email, "")

                    category = 'unknown'

                    auth_path = 'unknown'

                    permanent = False

                    try:

                        if is_aol_fail:

                            import aol_mail as am_cls

                            info = am_cls.classify_aol_login_error(pre_exc)

                            category = str(info.get('category') or 'unknown')

                            auth_path = str(info.get('auth_path') or 'IMAP password/app-password')

                            permanent = bool(info.get('permanent'))

                            log(am_cls.format_aol_login_error(email, pre_exc, stage='hybrid-preflight'))

                        else:

                            import outlook_mail as om_cls

                            # best-effort auth path from token blob

                            try:

                                data_tb = json.loads(mail_token) if mail_token else {}

                                if data_tb.get('refresh_token'):

                                    auth_path = 'refresh_token'

                                elif data_tb.get('password') and data_tb.get('totp_secret'):

                                    auth_path = 'password+TOTP'

                                elif data_tb.get('access_token'):

                                    auth_path = 'access_token'

                            except Exception:

                                auth_path = 'outlook'

                            info = om_cls.classify_outlook_login_error(pre_exc, auth_path=auth_path)

                            category = str(info.get('category') or 'unknown')

                            permanent = bool(info.get('permanent'))

                            log(om_cls.format_outlook_login_error(email, pre_exc, stage='hybrid-preflight', auth_path=auth_path))

                    except Exception as cls_exc:

                        log(f"[hybrid] login-error classify fail: {type(cls_exc).__name__}: {cls_exc}")

                    log(

                        f"[hybrid] mailbox pre-login FAIL email={email} provider={'aol' if is_aol_fail else 'outlook'} "

                        f"auth={auth_path} category={category} permanent={int(permanent)} "

                        f"exc={type(pre_exc).__name__} raw={pre_exc} | 换下一个邮箱 continue try={_try + 1}/20"

                    )

                    try:

                        msg = str(pre_exc)

                        msg_l = msg.lower()

                        bad = permanent or any(

                            x in msg

                            for x in (

                                "AUTHENTICATIONFAILED",

                                "Invalid credentials",

                                "LOGIN failed",

                                "password login failed",

                                "MFA/TOTP",

                                "invalid_grant",

                                "AADSTS",

                            )

                        ) or any(

                            x in msg_l

                            for x in (

                                "authentication failed",

                                "login invalid",

                                "auth fail",

                                "unauthorized",

                            )

                        )

                        if bad:

                            remove_mailbox_from_pool(email, reason="login_fail", log=log)

                            log(

                                f"[hybrid] 已从邮箱池实时删除登录失败邮箱: {email} "

                                f"(reason=login_fail category={category} auth={auth_path})"

                            )

                        else:

                            # temporary: release back to idle/cooldown without permanent delete

                            from grok_register_ttk import config as _cfg_pre2

                            if is_aol_fail:

                                import aol_mail as am2

                                am2.get_pool(_cfg_pre2, log_callback=log).release(

                                    email, ok=False, bad=False

                                )

                            else:

                                import outlook_mail as om2

                                om2.get_pool(_cfg_pre2, log_callback=log).release(

                                    email, ok=False, bad=False

                                )

                            log(

                                f"[hybrid] mailbox temporary fail kept in pool with cooldown email={email} "

                                f"category={category} auth={auth_path}"

                            )

                    except Exception as rel_pre:

                        log(f"[hybrid] pre-login release email: {rel_pre}")

                    # 18r28e: forced_email is a specific pending mailbox — do NOT spin 20 times

                    if force_em:

                        log(

                            f"[hybrid] forced_email preflight failed once email={email} "

                            f"category={category} — abort re-register (keep pending)"

                        )

                        return _result(

                            STATUS_FAIL,

                            email=email,

                            detail=f"forced_email_preflight_fail:{category}:{pre_exc}",

                        )

                    email, mail_token = "", ""

                    continue

            else:

                log("[hybrid] 连续尝试邮箱均失败（登录/预检），放弃本号")

                return _result(STATUS_FAIL, detail="mailbox preflight exhausted")



            if not email:

                log("[hybrid] no fresh email available after retries")

                return _result(STATUS_POOL_EMPTY, detail="no fresh email after retries")

            if stop():

                return _result(STATUS_STOPPED)



            # 18r14b: mint profile early so fail/timeout can land pending_sso with xAI password.

            given, family, password = build_profile()

            if force_pw:

                password = force_pw

                log(f"[hybrid] forced_xai_password applied len={len(password)}")

            log(

                f"[hybrid] early profile given={given!r} family={family!r} "

                f"password={password!r} email={email}"

            )



            # Browser UI submit triggers native CreateEmail (passes CF). Capture castle from that request.

            castle = browser.harvest_castle_via_email_submit(email, timeout=45)



            browser_cookies = browser.export_cookies()

            if not castle or len(castle) < 1000 or not str(castle).startswith("IBYIll"):

                log(

                    f"[hybrid] bad castle len={len(castle or '')} head={(castle or '')[:24]} "

                    f"email={email} password={password!r}"

                )

                burn_mailbox_to_pending(

                    email, password, reason="bad_castle", log=log,

            mail_token=mail_token,

        )

                return _result(

                    STATUS_PENDING_SSO, email=email, detail="bad_castle"

                )

            ua = browser.browser_user_agent() or user_agent or ""

            sess = ProtocolSession(

                proxy=(proxy or "").strip(),

                user_agent=ua,

                impersonate="chrome131",

            )

            # Prefer fresh signup cookies; strip old sso so server doesn't treat as logged-in.

            jar = dict(browser_cookies or {})

            for stale in ("sso", "sso-rw"):

                jar.pop(stale, None)

            sess.set_cookies(jar)

            client = AuthManagementClient(sess)

            if action:

                client.next_action = action



            # Strict CreateEmail evidence: never skip polling on "have castle only".

            st = browser.create_email_status_via_browser()

            log(

                f"[hybrid] CreateEmail UI click status={st.get('status')} seen={st.get('seen')} "

                f"ok={st.get('ok')} net_hits={st.get('net_hits')} raw={st.get('net_hits_raw')} "

                f"actual_send={st.get('actual_send_count')} blocked_dup={st.get('blocked_duplicate_count')} "

                f"sent={st.get('sent')} reason={st.get('reason')} castle_len={len(castle)}"

            )

            # Accept browser_sent only with strong evidence (2xx / ok / code-step)

            # PLUS real send evidence: actual_send_count>=1 or net_hits>=1 or UI code step.

            # 18r14: status=200 alone with actual_send=0/net_hits=0 must NOT skip protocol.

            reason = str(st.get("reason") or "")

            actual_send = int(st.get("actual_send_count") or 0)

            net_hits_n = int(st.get("net_hits") or 0)

            if actual_send <= 0 and net_hits_n > 0:

                # net_hits is body capture of CreateEmail; backfill for logs/decision

                actual_send = net_hits_n

                st["actual_send_count"] = actual_send

            ui_code_now = bool(st.get("ui_has_code") or st.get("ui_body_code"))

            weak_reasons = {

                "seen_status_unknown",

                "not_seen",

                "no_data",

            }

            raw_sent = bool(st.get("sent")) and reason not in weak_reasons

            has_send_evidence = (actual_send >= 1) or (net_hits_n >= 1) or ui_code_now

            browser_sent = bool(raw_sent and has_send_evidence)

            # 18r16: detect rate-limit message on page even when HTTP status looks 200

            ui_rl_hit, ui_rl_ev = detect_create_email_rate_limit(

                st.get("ui_body_text"),

                st.get("ui_rate_limit_text"),

                st.get("reason"),

                "rate_limited" if st.get("ui_rate_limited") else "",

            )

            if ui_rl_hit or bool(st.get("ui_rate_limited")):

                log(

                    f"[hybrid] CreateEmail UI rate-limit detected email={email} "

                    f"status={st.get('status')} actual_send={actual_send} {ui_rl_ev} "

                    f"body={st.get('ui_body_text')!r}"

                )

                return handle_create_email_rate_limited(

                    email,

                    password,

                    log=log,

                    source="browser_ui",

                    evidence=ui_rl_ev or "ui_rate_limited_flag",

                    mail_token=mail_token,

                )

            if raw_sent and not has_send_evidence:

                log(

                    f"[hybrid] CreateEmail weak browser claim ignored "

                    f"(no actual_send/net_hits/ui_code) status={st.get('status')} "

                    f"reason={reason} actual_send={actual_send} net_hits={net_hits_n}"

                )

            protocol_sent = False

            if browser_sent:

                log(

                    f"[hybrid] CreateEmail via browser OK (skip protocol re-send) "

                    f"castle_len={len(castle)} reason={reason} "

                    f"net_hits={st.get('net_hits')} actual_send={actual_send} "

                    f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')}"

                )

            else:

                # 18r8/r16: only re-click when NO CreateEmail network hit / actual send at all.

                net_hits_now = int(st.get("net_hits") or 0)

                if actual_send >= 1:

                    log(

                        f"[hybrid] CreateEmail skip re-click (actual_send={actual_send} already) "

                        f"net_hits={net_hits_now} reason={reason} — 防双发/验证码过多"

                    )

                    # treat as browser attempt; polling decides

                    if not browser_sent and (net_hits_now >= 1 or 200 <= int(st.get("status") or 0) < 300):

                        browser_sent = True

                        log(f"[hybrid] CreateEmail promote browser_sent from actual_send={actual_send}")

                elif net_hits_now >= 1 or bool(st.get("ui_has_code") or st.get("ui_body_code")):

                    log(

                        f"[hybrid] CreateEmail skip re-click (already fired) "

                        f"net_hits={net_hits_now} reason={reason} "

                        f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')} "

                        f"maybe_inflight={st.get('maybe_inflight')}"

                    )

                    if bool(st.get("ui_has_code") or st.get("ui_body_code")):

                        browser_sent = True

                        reason = reason or "ui_code_step_after_net_hit"

                        log(f"[hybrid] CreateEmail accept ui_code_step as sent reason={reason}")

                else:

                    try:

                        click2 = browser.click_email_continue_for_create(email)

                        log(

                            f"[hybrid] CreateEmail single re-click={click2} "

                            f"prev_reason={reason} maybe_inflight={st.get('maybe_inflight')} "

                            f"ui_busy={st.get('ui_busy')} net_hits=0"

                        )

                        time.sleep(2.5)

                        st = browser.create_email_status_via_browser()

                        reason = str(st.get("reason") or "")

                        actual_send = int(st.get("actual_send_count") or 0)

                        net_hits_n = int(st.get("net_hits") or 0)

                        if actual_send <= 0 and net_hits_n > 0:

                            actual_send = net_hits_n

                            st["actual_send_count"] = actual_send

                        ui_code_now = bool(st.get("ui_has_code") or st.get("ui_body_code"))

                        raw_sent = bool(st.get("sent")) and reason not in {

                            "seen_status_unknown",

                            "not_seen",

                            "no_data",

                        }

                        browser_sent = bool(

                            raw_sent

                            and ((actual_send >= 1) or (net_hits_n >= 1) or ui_code_now)

                        )

                        log(

                            f"[hybrid] CreateEmail after single re-click status={st.get('status')} "

                            f"seen={st.get('seen')} ok={st.get('ok')} sent={browser_sent} "

                            f"raw_sent={st.get('sent')} reason={reason} "

                            f"net_hits={st.get('net_hits')} actual_send={actual_send} "

                            f"ui_code={st.get('ui_has_code')}/{st.get('ui_body_code')}"

                        )

                    except Exception as re_exc:

                        log(f"[hybrid] CreateEmail re-click error: {re_exc}")

            if not browser_sent:

                # Protocol path only when UI never sent. Never stack protocol on top of browser_sent.

                r1 = client.create_email_validation_code(email, castle)

                strings = list(r1.get("strings") or [])

                log(

                    f"[hybrid] CreateEmail protocol status={r1['status']} "

                    f"castle_len={len(castle)} strings={strings[:4]}"

                )

                joined = " ".join(str(x) for x in strings)

                low_joined = joined.lower()

                rl_hit, rl_ev = detect_create_email_rate_limit(joined, strings, st.get("ui_body_text"), st.get("ui_rate_limit_text"))

                if rl_hit:

                    log(

                        f"[hybrid] CreateEmail rate-limited for {email}; "

                        f"burn pending + switch mailbox strings_full={strings} ui={st.get('ui_body_text')!r} {rl_ev}"

                    )

                    return handle_create_email_rate_limited(

                        email,

                        password,

                        log=log,

                        source="protocol_create_email",

                        evidence=rl_ev,

                    mail_token=mail_token,

                )

                if r1["status"] >= 400:

                    body_hint = ""

                    try:

                        raw = r1.get("raw") or b""

                        if b"cloudflare" in raw[:500].lower() or b"<!DOCTYPE" in raw[:200]:

                            body_hint = " (Cloudflare block)"

                    except Exception:

                        pass

                    log(f"[hybrid] CreateEmail fail{body_hint} strings={strings[:4]}")

                    log(

                        "[hybrid] CreateEmail 未真正发信（UI 无 seen/ok 且协议失败），"

                        "跳过 180s 空等验证码"

                    )

                    return _result(STATUS_FAIL)

                protocol_sent = True

                log(f"[hybrid] CreateEmail via protocol OK status={r1['status']}")



            if not browser_sent and not protocol_sent:

                log("[hybrid] CreateEmail 无发信迹象，禁止空等验证码")

                return _result(STATUS_FAIL)

            if stop():

                return _result(STATUS_STOPPED)



            send_ts = time.time()

            log(

                f"[hybrid] CreateEmail done send_ts={send_ts:.3f} email={email} "

                f"browser_sent={browser_sent} protocol_sent={protocol_sent}; "

                f"wait 3s before poll mail (AOL/Outlook ALL folders)"

            )

            # Wait 3s after send so Graph has time to receive; support cancel.

            for _w in range(30):

                if stop():

                    log("[hybrid] stop during post-CreateEmail 3s wait")

                    return _result(STATUS_FAIL)

                if time.time() - send_ts >= 3.0:

                    break

                time.sleep(0.1)

            log(

                f"[hybrid] 开始查邮件 email={email} timeout=180s since_ts={send_ts:.3f} "

                f"elapsed_since_send={time.time() - send_ts:.2f}s "

                f"(scan ALL mail folders; cancel 支持已启用)"

            )

            code = ""

            code_exc = None

            try:

                # 18r19: short window ONLY when protocol-rescue is still allowed.

                # After dual-send lock (actual_send/net_hits>=1), rescue is blocked — must poll full 180s

                # or code_timeout false-positives dominate (Outlook Graph often >45s).

                can_protocol_rescue = (

                    bool(browser_sent)

                    and (not protocol_sent)

                    and int(actual_send or 0) < 1

                    and int(net_hits_n or 0) < 1

                )

                use_short = bool(can_protocol_rescue)

                poll_timeout = 45 if use_short else 180

                log(

                    f"[hybrid] mail poll window email={email} poll_timeout={poll_timeout}s "

                    f"use_short={int(use_short)} can_protocol_rescue={int(can_protocol_rescue)} "

                    f"browser_sent={browser_sent} protocol_sent={protocol_sent} "

                    f"actual_send={actual_send} net_hits={net_hits_n}"

                )

                try:

                    code = get_oai_code(

                        mail_token,

                        email,

                        log_callback=log,

                        cancel_callback=stop,

                        since_ts=send_ts,

                        timeout=poll_timeout,

                    )

                except TypeError:

                    code = get_oai_code(

                        mail_token,

                        email,

                        log_callback=log,

                        cancel_callback=stop,

                        since_ts=send_ts,

                    )

            except Exception as e0:

                code_exc = e0

                code = ""



            clean = str(code or "").replace("-", "").strip()

            if (

                not clean

                and browser_sent

                and not protocol_sent

                and int(actual_send or 0) >= 1

                and not stop()

            ):

                log(

                    f"[hybrid] skip protocol-rescue (actual_send={actual_send} already fired) "

                    f"email={email} — avoid dual CreateEmail / 验证码过多; fall through code_timeout burn"

                )



            # 18r16 protocol rescue: ONLY if no real actual_send/net_hits (false browser_sent).

            # actual_send>=1 already requested mail — second CreateEmail triggers 验证码过多.

            if (

                not clean

                and browser_sent

                and not protocol_sent

                and int(actual_send or 0) < 1

                and int(net_hits_n or 0) < 1

                and not stop()

            ):

                try:

                    log(

                        f"[hybrid] CreateEmail silent browser send -> protocol rescue once "

                        f"email={email} actual_send={actual_send} net_hits={net_hits_n} err={code_exc}"

                    )

                    r_rescue = client.create_email_validation_code(email, castle)

                    strings_r = list(r_rescue.get("strings") or [])

                    joined_r = " ".join(str(x) for x in strings_r)

                    log(

                        f"[hybrid] CreateEmail protocol-rescue status={r_rescue.get('status')} "

                        f"strings_full={strings_r}"

                    )

                    rl_r, rl_ev_r = detect_create_email_rate_limit(joined_r, strings_r)

                    if rl_r:

                        return handle_create_email_rate_limited(

                            email,

                            password,

                            log=log,

                            source="protocol_rescue",

                            evidence=rl_ev_r,

                    mail_token=mail_token,

                )

                    if int(r_rescue.get("status") or 0) < 400:

                        protocol_sent = True

                        send_ts = time.time()

                        log(

                            f"[hybrid] protocol-rescue accepted; re-poll mail "

                            f"since_ts={send_ts:.3f}"

                        )

                        try:

                            try:

                                code = get_oai_code(

                                    mail_token,

                                    email,

                                    log_callback=log,

                                    cancel_callback=stop,

                                    since_ts=send_ts,

                                    timeout=120,

                                )

                            except TypeError:

                                code = get_oai_code(

                                    mail_token,

                                    email,

                                    log_callback=log,

                                    cancel_callback=stop,

                                    since_ts=send_ts,

                                )

                        except Exception as e2:

                            code_exc = e2

                            code = ""

                        clean = str(code or "").replace("-", "").strip()

                except Exception as rescue_exc:

                    log(f"[hybrid] protocol-rescue error: {rescue_exc}")



            if not clean:

                log(

                    f"[hybrid] no mail code email={email} browser_sent={browser_sent} "

                    f"protocol_sent={protocol_sent} err={code_exc} "

                    f"password={password!r} full_detail=code_timeout_or_empty"

                )

                # 18r17: empty inbox after send may be xAI rate-limit without UI; check err text

                try:

                    ui_body_chk = ""

                    try:

                        st_now = browser.read_create_email_ui_state() if hasattr(browser, "read_create_email_ui_state") else {}

                        if isinstance(st_now, dict):

                            ui_body_chk = str(st_now.get("ui_body_text") or st_now.get("body") or "")

                    except Exception:

                        ui_body_chk = ""

                    rl_hit, rl_ev = detect_create_email_rate_limit(code_exc, ui_body_chk, str(code_exc or ""))

                    if rl_hit or ("验证码过多" in str(code_exc or "")) or ("验证码过多" in ui_body_chk):

                        return handle_create_email_rate_limited(

                            email,

                            password or "",

                            log=log,

                            source="code_timeout_scan",

                            evidence=rl_ev or ui_body_chk or str(code_exc or ""),

                    mail_token=mail_token,

                )

                except Exception as rl_exc:

                    log(f"[hybrid] code_timeout rate-limit check err: {rl_exc}")

                try:

                    if not password:

                        given, family, password = build_profile()

                        log(f"[hybrid] late profile for pending password={password!r}")

                except Exception as pe:

                    log(f"[hybrid] late profile mint fail: {pe}")

                _exc_s = str(code_exc or "")

                _burn_reason = (

                    "early_no_new_mail"

                    if "early_no_new_mail" in _exc_s

                    else "code_timeout_or_empty"

                )

                log(

                    f"[hybrid] code empty burn reason={_burn_reason} email={email} "

                    f"err_full={_exc_s}"

                )

                burn_mailbox_to_pending(

                    email,

                    password,

                    reason=_burn_reason,

                    log=log,

            mail_token=mail_token,

        )

                return _result(

                    STATUS_PENDING_SSO,

                    email=email,

                    detail=_burn_reason,

                )

            log(f"[hybrid] code={clean}")



            # 18r22: VerifyEmail 经代理易 30s curl timeout；有码后必须重试，避免误 burn pending

            r2 = None

            _ve_last_exc = None

            _proxy_on = bool((proxy or "").strip())

            _ve_attempts = 3 if _proxy_on else 2

            for _ve_i in range(1, _ve_attempts + 1):

                if stop():

                    return _result(STATUS_STOPPED)

                _ve_timeout = 45 if (not _proxy_on and _ve_i == 1) else (60 if _proxy_on else 50)

                if _proxy_on and _ve_i >= 2:

                    _ve_timeout = 75

                try:

                    log(

                        f"[hybrid] VerifyEmail try {_ve_i}/{_ve_attempts} "

                        f"email={email} code={clean} timeout={_ve_timeout}s proxy={_proxy_on}"

                    )

                    r2 = client.verify_email_validation_code(

                        email, clean, timeout=_ve_timeout

                    )

                    log(

                        f"[hybrid] VerifyEmail status={r2.get('status')} "

                        f"try={_ve_i} strings={(r2.get('strings') or [])[:3]!r}"

                    )

                    _ve_last_exc = None

                    break

                except Exception as _ve_exc:

                    _ve_last_exc = _ve_exc

                    _ve_s = str(_ve_exc)

                    _transient = any(

                        k in _ve_s.lower()

                        for k in (

                            "timeout",

                            "timed out",

                            "curl: (28)",

                            "connection reset",

                            "connection aborted",

                            "failed to perform",

                            "recv failure",

                            "ssl",

                            "proxy",

                        )

                    )

                    log(

                        f"[hybrid] VerifyEmail exception try={_ve_i}/{_ve_attempts} "

                        f"transient={int(bool(_transient))} err={_ve_exc}"

                    )

                    if (not _transient) or _ve_i >= _ve_attempts:

                        break

                    time.sleep(1.5 * _ve_i)

            if r2 is None:

                if _ve_last_exc is not None:

                    raise _ve_last_exc

                raise RuntimeError("VerifyEmail returned no response")

            log(f"[hybrid] VerifyEmail status={r2['status']}")

            if r2["status"] >= 400:

                log(f"[hybrid] VerifyEmail fail {r2.get('strings')[:5]}")

                # 18r7: dual-code alternate retry (Inbox preferred first; try Bulk next)

                alt_codes = []

                try:

                    from aol_mail import LAST_OAI_CODE_CANDIDATES



                    for c in list(LAST_OAI_CODE_CANDIDATES or []):

                        cc = re.sub(r"[^A-Za-z0-9]", "", str((c or {}).get("code") or ""))

                        if cc and cc != clean and cc not in alt_codes:

                            alt_codes.append(cc)

                except Exception as alt_exc:

                    log(f"[hybrid] dual-code alt load fail: {alt_exc}")

                verified_alt = False

                for alt in alt_codes[:3]:

                    if stop():

                        return _result(STATUS_STOPPED)

                    try:

                        log(f"[hybrid] VerifyEmail retry alt code={alt} (dual-code)")

                        r2b = client.verify_email_validation_code(email, alt, timeout=60)

                        log(f"[hybrid] VerifyEmail alt status={r2b.get('status')}")

                        if int(r2b.get("status") or 0) < 400:

                            clean = alt

                            code = alt

                            r2 = r2b

                            verified_alt = True

                            log(f"[hybrid] VerifyEmail alt ok code={alt}")

                            break

                    except Exception as ve:

                        log(f"[hybrid] VerifyEmail alt exception: {ve}")

                if not verified_alt:

                    log(

                        f"[hybrid] VerifyEmail ultimate fail email={email} "

                        f"password={password!r} strings={r2.get('strings')[:8]!r}"

                    )

                    burn_mailbox_to_pending(

                        email, password, reason="verify_email_fail", log=log,

            mail_token=mail_token,

        )

                    return _result(

                        STATUS_PENDING_SSO,

                        email=email,

                        detail="verify_email_fail",

                    )

            if stop():

                return _result(STATUS_STOPPED)



            # 18r14b: profile already minted early (given/family/password)

            try:

                client.validate_password(email, password)

            except Exception:

                pass



            if stop():

                log("[hybrid] stop before turnstile")

                return _result(STATUS_FAIL)

            turnstile = browser.get_turnstile_token(timeout=90, inject=True, cancel_callback=stop)

            if stop():

                log("[hybrid] stop after turnstile")

                return _result(STATUS_FAIL)

            if len(turnstile) < 80:

                log(f"[hybrid] turnstile short len={len(turnstile)}")

                return _result(STATUS_FAIL)

            # CRITICAL: frontend mints a NEW castle via createRequestToken() on every SignUp.

            # Reusing CreateEmail castle often yields HTTP 200 RSC fragment with no sso cookie.

            # 18r5: force clear captures + mint; log whether head actually changed.

            castle_old = browser.read_captured_castle() or castle or ""

            log(

                f"[hybrid] mint fresh castle for SignUp (old_len={len(castle_old)} "

                f"old_head={(castle_old or '')[:36]})"

            )

            castle2 = castle_old

            try:

                fresh_castle = ""

                for mint_try in range(1, 3):

                    if hasattr(browser, "mint_fresh_castle_token"):

                        # 18r9: short mint windows; early-abort inside mint on weak 744 junk.

                        # CreateEmail IBYIll reuse remains the proven SSO path.

                        to = 6 if mint_try == 1 else 4

                        fresh_castle = browser.mint_fresh_castle_token(timeout=to, reason=f"signup_t{mint_try}") or ""

                    else:

                        try:

                            browser.clear_captured_castles(reason=f"signup_t{mint_try}")

                        except Exception:

                            pass

                        fresh_castle = browser.get_castle_token_injected(timeout=6) or ""

                    if fresh_castle and len(fresh_castle) >= 1000 and str(fresh_castle).startswith("IBYIll"):

                        break

                    if fresh_castle and len(fresh_castle) < 1000:

                        log(

                            f"[hybrid] fresh castle weak discard try={mint_try} "

                            f"len={len(fresh_castle)} head={(fresh_castle or '')[:24]}"

                        )

                        fresh_castle = ""

                    # 18r9: skip long get_castle_token after first weak early-abort; only one quick alt read.

                    if (not fresh_castle or len(fresh_castle) < 1000) and hasattr(

                        browser, "get_castle_token"

                    ) and mint_try == 1:

                        alt = browser.get_castle_token(timeout=3) or ""

                        if alt and len(alt) >= 1000 and str(alt).startswith("IBYIll"):

                            fresh_castle = alt

                            break

                        if alt and len(alt) < 1000:

                            log(f"[hybrid] get_castle_token weak discard len={len(alt)}")

                if fresh_castle and len(fresh_castle) >= 1000:

                    same_head = (fresh_castle[:48] == (castle_old or "")[:48]) if castle_old else False

                    castle2 = fresh_castle

                    log(

                        f"[hybrid] fresh castle ok len={len(castle2)} "

                        f"head={castle2[:48]} same_as_old_head={int(same_head)} "

                        f"src=force_mint"

                    )

                else:

                    log(

                        f"[hybrid] fresh castle weak/empty after retries; "

                        f"reuse previous head={(castle2 or '')[:36]} "

                        f"prev_len={len(castle2 or '')}"

                    )

            except Exception as castle_exc:

                log(f"[hybrid] fresh castle mint fail: {castle_exc}; reuse previous")



            browser_cookies = browser.export_cookies()

            jar2 = dict(browser_cookies or {})

            for stale in ("sso", "sso-rw"):

                jar2.pop(stale, None)

            sess.set_cookies(jar2)

            # Build next-action candidates. Prefer browser (CF/proxy already working).

            # Hardcoded known is last resort only — xAI redeploys invalidate it (404).

            known = "7f7f6cee188bd9cc17a3fb9dbde4abe224f21af0e3"  # live SignUp hash as of 2026-07-18k

            candidates: list[str] = []



            def _add_action(val: str, src: str):

                v = (val or "").strip()

                if not v:

                    return

                if is_dead_next_action(v):

                    log(

                        f"[hybrid] skip dead next-action src={src} "

                        f"hash={v[:20]}... len={len(v)}"

                    )

                    if src in {"capture_file", "earlier_or_capture", "hardcoded_fallback"}:

                        quarantine_dead_capture(v, log)

                    return

                if v not in candidates:

                    candidates.append(v)

                    log(

                        f"[hybrid] next-action candidate[{len(candidates)}] "

                        f"src={src} hash={v[:20]}... len={len(v)}"

                    )



            log("[hybrid] resolving next-action after turnstile…")

            # Main path unchanged: protocol SignUp with live candidates, then immediate SSO + pool.

            # pending_sso is fallback only after protocol/browser-fetch/UI all fail.

            try:

                for a in (browser.read_captured_next_actions() or []):

                    _add_action(a, "network_hook")

            except Exception as hook_exc:

                log(f"[hybrid] network hook next-action fail: {hook_exc}")

            try:

                # Prefer multi-candidate scrape so one dead hash does not kill the main path.

                multi = []

                if hasattr(browser, "scrape_next_action_candidates"):

                    multi = list(browser.scrape_next_action_candidates() or [])

                if multi:

                    for i, act_i in enumerate(multi, 1):

                        _add_action(act_i, f"browser_scrape_multi_{i}")

                else:

                    scraped = browser.scrape_next_action() or ""

                    _add_action(scraped, "browser_scrape")

            except Exception as scrape_exc:

                log(f"[hybrid] browser scrape next-action fail: {scrape_exc}")

            _add_action(action, "earlier_or_capture")

            if stop():

                return _result(STATUS_STOPPED)

            _add_action(load_next_action_from_capture(), "capture_file")

            # curl chunk discover often hangs 20s with 0 bytes when SOCKS/proxy path is dead

            # for accounts.x.ai static chunks. Skip if we already have live candidates.

            if candidates:

                log(

                    f"[hybrid] skip curl chunk discover "

                    f"(have {len(candidates)} live candidate(s); avoid 20s timeout)"

                )

            else:

                try:

                    client.next_action = ""

                    discovered = client.discover_next_action(timeout=8) or ""

                    _add_action(discovered, "chunk_discover")

                except Exception as disc_exc:

                    log(f"[hybrid] chunk discover next-action fail: {disc_exc}")

            if stop():

                return _result(STATUS_STOPPED)

            if not candidates:

                # Dead hash only when nothing else — expected 404 after redeploy.

                if not is_dead_next_action(known):

                    _add_action(known, "hardcoded_fallback")

                else:

                    log("[hybrid] hardcoded fallback is dead; skip")

            if not candidates:

                log("[hybrid] no next-action candidates at all")

                return _result(STATUS_FAIL)

            if stop():

                return _result(STATUS_STOPPED)



            def _mint_castle_for_try(try_idx: int) -> str:

                nonlocal castle2

                # Always force a real remint for browser-fetch / later tries.

                # try_idx==1 uses pre-minted castle2; later tries clear+mint.

                if try_idx == 1:

                    return castle2

                try:

                    if hasattr(browser, "mint_fresh_castle_token"):

                        c = browser.mint_fresh_castle_token(

                            timeout=10, reason=f"signup_try_{try_idx}"

                        ) or ""

                    else:

                        c = browser.get_castle_token_injected(timeout=8) or ""

                    if c and len(c) >= 1000:

                        same_head = (c[:40] == (castle2 or "")[:40]) if castle2 else False

                        castle2 = c

                        log(

                            f"[hybrid] re-mint castle for try {try_idx} "

                            f"len={len(c)} head={c[:40]} same_as_prev={int(same_head)}"

                        )

                        return c

                except Exception as exc:

                    log(f"[hybrid] re-mint castle fail try={try_idx}: {exc}")

                return castle2



            def _do_signup(act: str, castle_tok: str):

                # Short timeout: curl path often hangs 40s with 0 bytes on bad proxy.

                return client.create_user_via_server_action(

                    email=email,

                    code=clean,

                    given_name=given,

                    family_name=family,

                    password=password,

                    turnstile_token=turnstile,

                    castle_token=castle_tok,

                    next_action=act,

                    conversion_id=str(uuid.uuid4()),

                    timeout=18,

                )



            def _extract_sso(resp: dict) -> str:

                s = (resp or {}).get("sso") or ""

                if not s:

                    ck = (resp or {}).get("cookies") or {}

                    s = ck.get("sso") or ck.get("sso-rw") or ""

                return s or ""



            def _is_protocol_network_dead(st, body: str) -> bool:

                low = (body or "").lower()

                if st in (0, None):

                    return True

                return any(

                    k in low

                    for k in (

                        "curl: (28)",

                        "operation timed out",

                        "timed out after",

                        "0 bytes received",

                        "connection timed out",

                        "failed to perform",

                        "proxy",

                        "could not resolve",

                        "connection reset",

                        "ssl connect error",

                    )

                )



            def _log_signup_diag(idx: int, resp: dict, path: str = "protocol") -> None:

                body = str((resp or {}).get("text") or "")

                sc = (resp or {}).get("set_cookie_blob") or ""

                hints = (resp or {}).get("error_hints") or []

                redir = (resp or {}).get("redirect_url") or ""

                log(

                    f"[hybrid] sign-up diag path={path} try={idx} status={resp.get('status')} "

                    f"sso_len={len(_extract_sso(resp))} text_len={resp.get('text_len') or len(body)} "

                    f"castle_len={resp.get('castle_len')} turnstile_len={resp.get('turnstile_len')} "

                    f"tos={resp.get('tos_accepted_version')} redirect={redir!r} "

                    f"hints={hints} cookies={list(((resp.get('cookies') or {}).keys()))[:16]}"

                )

                if body:

                    log(f"[hybrid] sign-up body_head={body[:500]!r}")

                    if len(body) > 500:

                        log(f"[hybrid] sign-up body_tail={body[-400:]!r}")

                if sc:

                    log(f"[hybrid] sign-up set-cookie={sc[:500]!r}")



            r3 = {}

            sso = ""

            body_txt = ""

            protocol_network_dead = False

            for idx, act in enumerate(candidates, 1):

                if stop():

                    return _result(STATUS_STOPPED)

                try:

                    jar3 = dict(browser.export_cookies() or {})

                    for stale in ("sso", "sso-rw"):

                        jar3.pop(stale, None)

                    sess.set_cookies(jar3)

                except Exception:

                    pass

                castle_tok = _mint_castle_for_try(idx)

                client.next_action = act

                log(

                    f"[hybrid] sign-up try {idx}/{len(candidates)} path=protocol/curl "

                    f"next-action={act[:20]}... castle_len={len(castle_tok)} timeout=18s"

                )

                t_try = time.time()

                try:

                    r3 = _do_signup(act, castle_tok)

                except Exception as signup_exc:

                    log(f"[hybrid] sign-up try {idx} exception: {signup_exc}")

                    r3 = {

                        "status": 0,

                        "text": str(signup_exc),

                        "cookies": {},

                        "sso": "",

                        "error_hints": ["exception"],

                    }

                sso = _extract_sso(r3)

                body_txt = str(r3.get("text") or "")

                st = r3.get("status")

                log(

                    f"[hybrid] sign-up try {idx} status={st} sso_len={len(sso)} "

                    f"elapsed={time.time() - t_try:.1f}s body={body_txt[:180]!r}"

                )

                if not sso:

                    _log_signup_diag(idx, r3, path="protocol/curl")

                if sso:

                    try:

                        save_next_action_to_capture(act, log)

                    except Exception:

                        pass

                    break

                low = body_txt.lower()

                # Keep keywords specific — avoid matching random RSC noise.

                if any(

                    k in low

                    for k in (

                        "already registered",

                        "already exists",

                        "email already",

                        "account already",

                        "signinmethods",

                        "sign_in_methods",

                        "email_already",

                        "already_exists",

                        "isloggedinwithsso",

                    )

                ):

                    log(

                        f"[hybrid] email/account state blocks sign-up, stop candidates: "

                        f"{body_txt[:240]}"

                    )

                    try:

                        mark_outlook_registered(email, log)

                    except Exception:

                        pass

                    break

                if _is_protocol_network_dead(st, body_txt):

                    protocol_network_dead = True

                    log(

                        "[hybrid] protocol network DEAD (curl timeout/0-byte/proxy) — "

                        "stop further protocol candidates; switch to browser same-origin path"

                    )

                    break

                # Only hard-404 means dead hash. RSC shell / business error means action is ALIVE.

                if st == 404 or "server action not found" in low:

                    DEAD_NEXT_ACTIONS.add(_norm_action(act))

                    quarantine_dead_capture(act, log)

                    log(

                        f"[hybrid] next-action {act[:16]} hard-404 invalid "

                        f"(status={st}, no sso); quarantine and try next"

                    )

                    continue

                # Business / token failures: keep hash alive, stop wasting candidates.

                if any(

                    k in low

                    for k in (

                        "failed to verify cloudflare turnstile",

                        "turnstile token",

                        "castle",

                        "invalid email",

                        "email validation",

                        "rate limit",

                        "too many",

                    )

                ) or (

                    '"error"' in low and "traceid" in low

                ):

                    log(

                        f"[hybrid] sign-up business/token error on live next-action "

                        f"{act[:16]}... status={st}; stop protocol candidates "

                        f"(action hash kept alive)"

                    )

                    break

                # Large RSC shell with fragment usually means action accepted but rejected

                # server-side (missing/invalid tokens). Do NOT quarantine.

                if "$sreact.fragment" in low or "react.fragment" in low:

                    log(

                        f"[hybrid] next-action {act[:16]} returned RSC shell "

                        f"(status={st}, no sso); hash stays live, try next path"

                    )

                    continue

                log(

                    f"[hybrid] sign-up try {idx} no sso (status={st}); "

                    f"continue next candidate with fresh castle"

                )

            # 18r5: same live hash RSC shell often needs a second protocol shot with forced fresh castle + new conversionId.

            if (not sso) and (not protocol_network_dead) and candidates and (not stop()):

                try:

                    act = candidates[0]

                    castle_tok = _mint_castle_for_try(99)

                    try:

                        jar3 = dict(browser.export_cookies() or {})

                        for stale in ("sso", "sso-rw"):

                            jar3.pop(stale, None)

                        sess.set_cookies(jar3)

                    except Exception:

                        pass

                    client.next_action = act

                    log(

                        f"[hybrid] protocol forced-remint retry path=protocol/curl "

                        f"next-action={act[:20]}... castle_len={len(castle_tok)} "

                        f"castle_head={(castle_tok or '')[:40]}"

                    )

                    t_try = time.time()

                    try:

                        r3 = _do_signup(act, castle_tok)

                    except Exception as signup_exc:

                        log(f"[hybrid] protocol forced-remint exception: {signup_exc}")

                        r3 = {

                            "status": 0,

                            "text": str(signup_exc),

                            "cookies": {},

                            "sso": "",

                            "error_hints": ["exception"],

                        }

                    sso = _extract_sso(r3)

                    body_txt = str(r3.get("text") or "")

                    st = r3.get("status")

                    log(

                        f"[hybrid] protocol forced-remint status={st} sso_len={len(sso)} "

                        f"elapsed={time.time() - t_try:.1f}s body={body_txt[:180]!r}"

                    )

                    if not sso:

                        _log_signup_diag(99, r3, path="protocol/curl-forced-remint")

                    if sso:

                        try:

                            save_next_action_to_capture(act, log)

                        except Exception:

                            pass

                except Exception as forced_exc:

                    log(f"[hybrid] protocol forced-remint block error: {forced_exc}")



            # Protocol-first recovery: if candidates only returned RSC shell/no-sso,

            # live re-scrape next-action and retry protocol once before browser-fetch.

            if (not sso) and (not protocol_network_dead) and (not stop()):

                try:

                    live_retry_acts: list[str] = []

                    try:

                        for a in (browser.read_captured_next_actions() or []):

                            a = (a or "").strip()

                            if a and a not in live_retry_acts and a != known and a not in candidates:

                                live_retry_acts.append(a)

                    except Exception:

                        pass

                    try:

                        scraped2 = (browser.scrape_next_action() or "").strip()

                        if (

                            scraped2

                            and scraped2 not in live_retry_acts

                            and scraped2 != known

                            and scraped2 not in candidates

                        ):

                            live_retry_acts.append(scraped2)

                    except Exception as scrape2_exc:

                        log(f"[hybrid] protocol re-scrape next-action fail: {scrape2_exc}")

                    if live_retry_acts:

                        log(

                            f"[hybrid] protocol live re-scrape retry candidates="

                            f"{len(live_retry_acts)}"

                        )

                    for ridx, act in enumerate(live_retry_acts[:2], 1):

                        if stop() or sso:

                            break

                        try:

                            jar3 = dict(browser.export_cookies() or {})

                            for stale in ("sso", "sso-rw"):

                                jar3.pop(stale, None)

                            sess.set_cookies(jar3)

                        except Exception:

                            pass

                        castle_tok = _mint_castle_for_try(ridx + 30)

                        client.next_action = act

                        log(

                            f"[hybrid] protocol re-scrape try {ridx} path=protocol/curl "

                            f"next-action={act[:20]}... castle_len={len(castle_tok)}"

                        )

                        t_try = time.time()

                        try:

                            r3 = _do_signup(act, castle_tok)

                        except Exception as signup_exc:

                            log(f"[hybrid] protocol re-scrape try {ridx} exception: {signup_exc}")

                            r3 = {

                                "status": 0,

                                "text": str(signup_exc),

                                "cookies": {},

                                "sso": "",

                                "error_hints": ["exception"],

                            }

                        sso = _extract_sso(r3)

                        body_txt = str(r3.get("text") or "")

                        st = r3.get("status")

                        log(

                            f"[hybrid] protocol re-scrape try {ridx} status={st} "

                            f"sso_len={len(sso)} elapsed={time.time() - t_try:.1f}s "

                            f"body={body_txt[:180]!r}"

                        )

                        if not sso:

                            _log_signup_diag(ridx, r3, path="protocol/curl-rescrape")

                        if sso:

                            try:

                                save_next_action_to_capture(act, log)

                            except Exception:

                                pass

                            break

                        low = body_txt.lower()

                        if _is_protocol_network_dead(st, body_txt):

                            protocol_network_dead = True

                            break

                except Exception as prot_live_exc:

                    log(f"[hybrid] protocol live re-scrape block error: {prot_live_exc}")



            # 18r20-retry-first-after-nosso: 200 RSC shell often intermittent; remint + retry best action once

            if (not sso) and (not protocol_network_dead) and candidates:

                try:

                    act0 = candidates[0]

                    log(

                        f"[hybrid] 18r20 SignUp no-sso retry: remint castle + retry action={act0[:20]}..."

                    )

                    castle_retry = _mint_castle_for_try(99)

                    if not castle_retry or len(castle_retry) < 1000:

                        castle_retry = castle2 or ''

                    # prefer CreateEmail long castle if remint weak

                    try:

                        oldc = browser.read_captured_castle() or ""

                        if oldc.startswith("IBYIll") and len(oldc) >= 1000 and (

                            not castle_retry or len(castle_retry) < 1000 or not str(castle_retry).startswith("IBYIll")

                        ):

                            castle_retry = oldc

                            log(f"[hybrid] 18r20 reuse CreateEmail castle len={len(oldc)}")

                    except Exception:

                        pass

                    t_try = time.time()

                    r3 = _do_signup(act0, castle_retry or castle2)

                    sso = _extract_sso(r3)

                    body_txt = str(r3.get("text") or "")

                    log(

                        f"[hybrid] 18r20 no-sso retry status={r3.get('status')} sso_len={len(sso)} "

                        f"elapsed={time.time()-t_try:.1f}s body={body_txt[:160]!r}"

                    )

                    if not sso:

                        _log_signup_diag(99, r3, path="protocol/curl-18r20-retry")

                    if sso:

                        try:

                            save_next_action_to_capture(act0, log)

                        except Exception:

                            pass

                except Exception as retry_exc:

                    log(f"[hybrid] 18r20 no-sso retry fail: {retry_exc}")





            log(

                f"[hybrid] sign-up final status={r3.get('status')} sso_len={len(sso)} "

                f"elapsed={time.time() - t0:.1f}s protocol_network_dead={protocol_network_dead}"

            )

            if not sso:

                log(

                    f"[hybrid] protocol no sso cookies={list((r3.get('cookies') or {}).keys())[:12]} "

                    f"body={body_txt[:240]}"

                )

                if stop():

                    return _result(STATUS_STOPPED)

                # Prefer browser same-origin fetch: browser already passed CF/proxy to accounts.x.ai

                live_acts = list(candidates)  # include known live hash; do not drop it

                log(

                    f"[hybrid] browser same-origin fetch SignUp "

                    f"candidates={len(live_acts)} email={email}"

                )

                for bidx, act in enumerate(live_acts[:3], 1):

                    if stop():

                        return _result(STATUS_FAIL)

                    try:

                        castle_tok = _mint_castle_for_try(bidx + 10)

                        log(

                            f"[hybrid] browser-fetch try {bidx}/{min(3, len(live_acts))} "

                            f"next-action={act[:20]}... castle_len={len(castle_tok)}"

                        )

                        t_bf = time.time()

                        br = browser.fetch_signup_server_action(

                            email=email,

                            code=clean,

                            given_name=given,

                            family_name=family,

                            password=password,

                            turnstile_token=turnstile,

                            castle_token=castle_tok,

                            next_action=act,

                            conversion_id=str(uuid.uuid4()),

                            router_state_tree=getattr(client, "router_state_tree", "") or "",

                            timeout=25,

                        )

                        sso = _extract_sso(br) or ""

                        if not sso:

                            try:

                                jar_b = browser.export_cookies() or {}

                                sso = jar_b.get("sso") or jar_b.get("sso-rw") or ""

                            except Exception:

                                pass

                        body_txt = str((br or {}).get("text") or body_txt)

                        r3 = br or r3

                        log(

                            f"[hybrid] browser-fetch try {bidx} status={br.get('status')} "

                            f"sso_len={len(sso)} elapsed={time.time() - t_bf:.1f}s "

                            f"body={str(br.get('text') or '')[:180]!r}"

                        )

                        if not sso:

                            _log_signup_diag(bidx, br or {}, path="browser-fetch")

                        if sso:

                            try:

                                save_next_action_to_capture(act, log)

                            except Exception:

                                pass

                            break

                        st_b = br.get("status")

                        low_b = str(br.get("text") or "").lower()

                        if st_b == 404 or "server action not found" in low_b:

                            DEAD_NEXT_ACTIONS.add(_norm_action(act)); quarantine_dead_capture(act, log); log(f"[hybrid] browser-fetch next-action {act[:16]} invalid, quarantine, try next")

                            continue

                    except Exception as bf_exc:

                        log(f"[hybrid] browser-fetch try {bidx} error: {bf_exc}")

                if not sso and not stop():

                    # Live re-scrape next-action after failed browser-fetch (hook/HTML/chunks).

                    try:

                        live_retry_acts: list[str] = []

                        try:

                            for a in (browser.read_captured_next_actions() or []):

                                a = (a or "").strip()

                                if a and a not in live_retry_acts and a != known:

                                    live_retry_acts.append(a)

                        except Exception:

                            pass

                        try:

                            scraped2 = (browser.scrape_next_action() or "").strip()

                            if scraped2 and scraped2 not in live_retry_acts and scraped2 != known:

                                live_retry_acts.append(scraped2)

                        except Exception as scrape2_exc:

                            log(f"[hybrid] live re-scrape next-action fail: {scrape2_exc}")

                        for a in list(candidates):

                            a = (a or "").strip()

                            if a and a not in live_retry_acts and a != known:

                                live_retry_acts.append(a)

                        if live_retry_acts:

                            log(

                                f"[hybrid] live re-scrape browser-fetch retry "

                                f"candidates={len(live_retry_acts)}"

                            )

                        for ridx, act in enumerate(live_retry_acts[:2], 1):

                            if stop() or sso:

                                break

                            if act in live_acts[:3]:

                                # already tried in previous browser-fetch loop

                                continue

                            try:

                                castle_tok = _mint_castle_for_try(ridx + 20)

                                log(

                                    f"[hybrid] browser-fetch live-retry {ridx} "

                                    f"next-action={act[:20]}... castle_len={len(castle_tok)}"

                                )

                                br = browser.fetch_signup_server_action(

                                    email=email,

                                    code=clean,

                                    given_name=given,

                                    family_name=family,

                                    password=password,

                                    turnstile_token=turnstile,

                                    castle_token=castle_tok,

                                    next_action=act,

                                    conversion_id=str(uuid.uuid4()),

                                    router_state_tree=getattr(client, "router_state_tree", "") or "",

                                    timeout=25,

                                )

                                sso = _extract_sso(br) or ""

                                if not sso:

                                    try:

                                        jar_b = browser.export_cookies() or {}

                                        sso = jar_b.get("sso") or jar_b.get("sso-rw") or ""

                                    except Exception:

                                        pass

                                body_txt = str((br or {}).get("text") or body_txt)

                                r3 = br or r3

                                log(

                                    f"[hybrid] browser-fetch live-retry {ridx} "

                                    f"status={br.get('status')} sso_len={len(sso)} "

                                    f"body={str(br.get('text') or '')[:180]!r}"

                                )

                                if sso:

                                    try:

                                        save_next_action_to_capture(act, log)

                                    except Exception:

                                        pass

                                    break

                            except Exception as retry_exc:

                                log(f"[hybrid] browser-fetch live-retry {ridx} error: {retry_exc}")

                    except Exception as live_exc:

                        log(f"[hybrid] live re-scrape block error: {live_exc}")



                # Last-resort UI fallback only. Main path remains protocol/browser-fetch → immediate SSO.

                if not sso:

                    log(

                        f"[hybrid] browser-fetch no sso; UI profile submit fallback "

                        f"email={email} given={given} family={family}"

                    )

                    try:

                        # 18r17: protocol already verified; do not spin 90s on stuck code page

                        ui_sso = browser.submit_profile_and_wait_sso(

                            given_name=given,

                            family_name=family,

                            password=password,

                            turnstile_token=turnstile,

                            email=email,

                            code=clean,

                            timeout=40,

                            cancel_callback=stop,

                        )

                        ui_sso = (ui_sso or "").strip()

                        if ui_sso:

                            sso = ui_sso

                            log(

                                f"[hybrid] UI fallback SSO ok len={len(sso)} email={email}"

                            )

                            try:

                                # Capture any live next-action observed during UI submit for later runs.

                                for a in (browser.read_captured_next_actions() or []):

                                    if a and not is_dead_next_action(a):

                                        save_next_action_to_capture(a, log)

                                        break

                            except Exception:

                                pass

                        else:

                            log(

                                f"[hybrid] UI fallback finished without SSO email={email}"

                            )

                    except Exception as ui_exc:

                        if stop():

                            log("[hybrid] stop during UI fallback")

                            return _result(STATUS_STOPPED)

                        log(f"[hybrid] UI fallback exception: {ui_exc}")

                        try:

                            log(traceback.format_exc())

                        except Exception:

                            pass

            if not sso:

                # 18r12: pending_sso ONLY when registration is actually confirmed (UI profile submitted).

                # Protocol VerifyEmail alone is NOT account creation; desync/stuck email page must not pending.

                ui_result = {}

                try:

                    ui_result = getattr(browser, "last_ui_fallback_result", None) or {}

                    if not isinstance(ui_result, dict):

                        ui_result = {}

                except Exception:

                    ui_result = {}

                signup_confirmed = bool(ui_result.get("signup_confirmed") or ui_result.get("submitted"))

                ui_reason = str(ui_result.get("reason") or "")

                log(

                    f"[hybrid] no-sso classify signup_confirmed={int(signup_confirmed)} "

                    f"ui_reason={ui_reason!r} ui_result={ui_result}"

                )

                if email and password and not signup_confirmed:

                    log(

                        f"[hybrid] signup unconfirmed (no SSO); burn to pending_sso "

                        f"ui_reason={ui_reason!r} email={email} password={password!r} "

                        f"ui_result={ui_result}"

                    )

                    burn_mailbox_to_pending(

                        email,

                        password,

                        reason=f"signup_unconfirmed:{ui_reason or 'no_sso'}",

                        log=log,

            mail_token=mail_token,

        )

                    return _result(

                        STATUS_PENDING_SSO,

                        email=email,

                        detail=f"signup_unconfirmed:{ui_reason or 'no_sso'}",

                    )

                # Confirmed registration without SSO: burn mailbox + pending for secondary SSO.

                log(

                    f"[hybrid] registered without SSO/OOS; burn to pending_sso "

                    f"email={email} password={password!r}"

                )

                burn_mailbox_to_pending(

                    email,

                    password,

                    reason="pending_sso_no_sso",

                    log=log,

            mail_token=mail_token,

        )

                log(

                    f"[hybrid] no sso after protocol+browser-fetch+UI (confirmed) email={email}"

                )

                return _result(STATUS_PENDING_SSO, email=email, detail="verified_no_sso")



            # Hybrid often gets set-cookie *wrapper* JWT (~2k). CPA needs real session sso (~150).

            try:

                from protocol.sso_util import (

                    is_session_sso,

                    is_wrapper_sso,

                    materialize_sso_via_browser,

                    materialize_sso_via_http,

                )



                if is_wrapper_sso(sso) or not is_session_sso(sso):

                    t_mat = time.time()

                    log(

                        f"[hybrid] sso materialize stage=start wrapper_len={len(sso)} "

                        f"is_wrapper={is_wrapper_sso(sso)} is_session={is_session_sso(sso)}"

                    )

                    from grok_register_ttk import _get_page



                    page = _get_page()

                    sess_sso = ""

                    if page is not None:

                        log("[hybrid] sso materialize stage=browser_nav timeout=28")

                        sess_sso = materialize_sso_via_browser(

                            page, sso, log=log, timeout=28

                        )

                        log(

                            f"[hybrid] sso materialize stage=browser_done "

                            f"len={len(sess_sso or '')} ok={bool(sess_sso and is_session_sso(sess_sso))} "

                            f"elapsed={time.time()-t_mat:.1f}s"

                        )

                    if not sess_sso or not is_session_sso(sess_sso):

                        log("[hybrid] sso materialize stage=http_fallback")

                        jar = dict(browser.export_cookies() or {})

                        sess_sso = materialize_sso_via_http(

                            sso,

                            proxy=(proxy or "").strip(),

                            extra_cookies=jar,

                            log=log,

                            timeout=18,

                        ) or sess_sso

                        log(

                            f"[hybrid] sso materialize stage=http_done "

                            f"len={len(sess_sso or '')} ok={bool(sess_sso and is_session_sso(sess_sso))} "

                            f"elapsed={time.time()-t_mat:.1f}s"

                        )

                    if sess_sso and is_session_sso(sess_sso):

                        log(

                            f"[hybrid] session sso ready len={len(sess_sso)} "

                            f"elapsed={time.time()-t_mat:.1f}s"

                        )

                        sso = sess_sso

                    else:

                        log(

                            f"[hybrid] WARN still wrapper/non-session sso len={len(sso)}; "

                            f"CPA mint may fail until browser path works "

                            f"elapsed={time.time()-t_mat:.1f}s"

                        )

            except Exception as e:

                log(f"[hybrid] sso materialize: {e}")



            line = f"{email}----{password}----{sso}\n"

            try:

                with accounts_file.open("a", encoding="utf-8") as f:

                    f.write(line)

            except Exception as e:

                log(f"[hybrid] save file fail: {e}")



            log(f"[hybrid][+] OK {email}")

            try:

                mark_outlook_registered(email, log)

            except Exception:

                pass

            if post_success:

                try:

                    # Export full browser jar (cf_clearance + sso) for CPA protocol mint

                    jar_full = dict(browser.export_cookies() or {})

                    if sso:

                        jar_full["sso"] = sso

                        jar_full["sso-rw"] = jar_full.get("sso-rw") or sso

                    cookie_list = [

                        {"name": k, "value": v, "domain": ".x.ai", "path": "/"}

                        for k, v in jar_full.items()

                        if k and v is not None

                    ]

                    log(f"[hybrid] post cookies={len(cookie_list)} for CPA/g2a")

                    # Main path: immediate post-success on SSO (CPA/Sub2API/g2a). pending is NOT used here.

                    schedule_post_registration(

                        email,

                        password,

                        sso,

                        page=None,

                        cookies=cookie_list,

                        log_callback=log,

                    )

                except Exception as e:

                    log(f"[hybrid] post_success: {e}")

            log(

                f"[hybrid][+] OK immediate SSO+pool path elapsed={time.time()-t0:.1f}s "

                f"email={email} sso_len={len(sso or '')}"

            )

            return _result(STATUS_SUCCESS, email=email)

    except Exception as e:

        if stop():

            log("[hybrid] 已按停止请求中断当前账号，不计为注册失败")

            return _result(STATUS_STOPPED)

        log(f"[hybrid] exception: {e}")

        try:

            log(traceback.format_exc())

        except Exception:

            pass

        if is_pool_empty_error(e):

            return _result(STATUS_POOL_EMPTY, detail=str(e))

        try:

            em = str(email or "").strip()

            pw = str(password or "").strip()

        except Exception:

            em, pw = "", ""

        if em and pw:

            log(

                f"[hybrid] exception burn to pending_sso email={em} password={pw!r} err={e}"

            )

            try:

                burn_mailbox_to_pending(

                    em, pw, reason=f"register_exception:{type(e).__name__}", log=log,

            mail_token=mail_token,

        )

            except Exception as be:

                log(f"[hybrid] exception pending burn fail: {be}")

            return _result(STATUS_PENDING_SSO, email=em, detail=str(e))

        return _result(STATUS_FAIL, detail=str(e))





def run_hybrid_registration_job(count, log_callback=None, controller=None, workers=None):

    """Web/CLI entry compatible with run_registration_job return shape."""

    import grok_register_ttk as engine



    log = log_callback or engine.cli_log

    if controller is None:

        controller = engine.CliStopController()



    success_count = 0

    fail_count = 0

    pending_sso_count = 0

    skipped_count = 0

    pool_empty = False

    accounts_output_file = os.path.join(

        os.path.dirname(os.path.abspath(__file__)),

        f"accounts_hybrid_{engine.now_beijing('%Y%m%d_%H%M%S')}.txt",

    )

    log(f"[*] 混合模式启动，目标数量: {count}")

    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")



    mode = str(engine.config.get("proxy_mode", "direct") or "direct")

    try:

        resolved_proxy = engine.apply_resolved_proxy_to_config(

            log_callback=log, fetch_live=True

        )

    except Exception as proxy_exc:

        log(f"[!] 获取/解析代理失败: {proxy_exc}")

        raise



    if resolved_proxy:

        # Full proxy URL in logs (no redaction), per user request.

        log(f"[*] 代理模式: {mode} | {resolved_proxy}")

    else:

        log(f"[*] 代理模式: {mode or 'direct'}（直连）")



    next_action = load_next_action_from_capture()

    try:

        scan_dirs = [str(d) for d in _account_scan_dirs() if d.exists()]

        log(f"[hybrid] scan registered account dirs: {scan_dirs}")

        registered = load_registered_emails()

        log(f"[hybrid] already-registered emails loaded: {len(registered)}")

        if registered:

            for em in list(registered)[:500]:

                mark_outlook_registered(em, None)

            sample = ", ".join(list(sorted(registered))[:5])

            log(f"[hybrid] pre-marked Outlook pool; sample: {sample}")

    except Exception as pre_exc:

        log(f"[hybrid] pre-mark registered outlook fail: {pre_exc}")

    ua = str(engine.config.get("user_agent") or "")

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

            if controller.should_stop():

                break

            log(f"--- [hybrid] 开始第 {i + 1}/{count} 个账号 ---")

            raw = register_one_hybrid(

                log=log,

                proxy=proxy,

                user_agent=ua,

                next_action=next_action,

                accounts_file=Path(accounts_output_file),

                should_stop=controller.should_stop,

                post_success=True,

            )

            res = normalize_result(raw)

            status = str(res.get("status") or STATUS_FAIL)

            if controller.should_stop() or status == STATUS_STOPPED:

                log("[*] 当前账号因停止请求中断，统计保持不变")

                break

            if status == STATUS_SUCCESS:

                success_count += 1

            elif status == STATUS_PENDING_SSO and (

                bool(res.get("rate_limited") or res.get("switch_mailbox"))

                or "create_email_rate_limited" in str(res.get("detail") or "")

            ):

                pending_sso_count += 1

                switch_mailbox_tries += 1

                log(

                    f"[hybrid] rate-limited mailbox burned; IMMEDIATE switch next email "

                    f"email={res.get('email')} detail={res.get('detail')} "

                    f"switch_try={switch_mailbox_tries}/{max_switch_mailbox} "

                    f"(do not consume success target slot)"

                )

                log(

                    f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count} | "

                    f"pending_sso {pending_sso_count} | 跳过(池空) {skipped_count}"

                )

                if switch_mailbox_tries >= max_switch_mailbox:

                    log(

                        f"[hybrid] switch_mailbox cap reached {switch_mailbox_tries}; "

                        f"stop job without infinite retry"

                    )

                    break

                engine.sleep_with_cancel(0.5, controller.should_stop)

                continue

            elif status == STATUS_PENDING_SSO:

                pending_sso_count += 1

            elif status == STATUS_POOL_EMPTY:

                pool_empty = True

                skipped_count += 1

                log("[*] 邮箱池已空，停止后续注册（不计为失败）")

                log(

                    f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count} | "

                    f"pending_sso {pending_sso_count} | 跳过(池空) {skipped_count}"

                )

                break

            else:

                fail_count += 1

            i += 1

            log(

                f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count} | "

                f"pending_sso {pending_sso_count} | 跳过(池空) {skipped_count}"

            )

            engine.sleep_with_cancel(1, controller.should_stop)

    except KeyboardInterrupt:

        controller.stop()

        log("[!] 收到 Ctrl+C，正在停止")

    except Exception as exc:

        log(f"[!] 混合任务异常: {exc}")

        try:

            log(traceback.format_exc())

        except Exception:

            pass

    finally:

        # Stop browser immediately so Web「停止」不会留下 Chromium 僵尸进程

        try:

            if controller.should_stop():

                engine.force_stop_registration(log_callback=log, reason="hybrid_job_stopped")

            else:

                engine.stop_browser(log_callback=log)

        except Exception as stop_exc:

            log(f"[!] hybrid finally stop browser: {stop_exc}")

            try:

                engine.force_kill_registration_browsers(log_callback=log)

            except Exception:

                pass

        # Don't block job end for long CPA browser mint (SSO already saved).

        try:

            engine.wait_post_success_queue(timeout=20 if controller.should_stop() else 120, log_callback=log)

        except Exception:

            pass

        try:

            engine.cleanup_runtime_memory(log_callback=log, reason="混合任务结束")

        except Exception:

            pass

        log(

            f"[*] 混合任务结束。成功 {success_count} | 失败 {fail_count} | "

            f"pending_sso {pending_sso_count} | 跳过(池空) {skipped_count}"

        )



    return {

        "success": success_count,

        "fail": fail_count,

        "pending_sso": pending_sso_count,

        "skipped": skipped_count,

        "pool_empty": bool(pool_empty),

        "accounts_file": accounts_output_file,

        "stopped": bool(controller.should_stop()),

    }







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

        engine.wait_post_success_queue(timeout=20 if controller.should_stop() else 120, log_callback=log)

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



