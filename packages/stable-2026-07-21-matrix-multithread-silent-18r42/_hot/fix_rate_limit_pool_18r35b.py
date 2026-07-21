from pathlib import Path
import re, time

root = Path(r'C:\Users\zhang\grok-regkit')

# ---------- outlook_mail.py ----------
om_path = root / 'outlook_mail.py'
om = om_path.read_text(encoding='utf-8')

# changelog note near top
if '18r35b: preserve in_use' not in om:
    om = om.replace(
        'Changelog:\n',
        'Changelog:\n'
        '- 2026-07-20r35b: get_pool no longer rebuilds on config.outlook_accounts text churn;\n'
        '  preserve in_use/cooldown/tokens across force_reload; stop multi-worker same-email CreateEmail.\n'
        '  (root cause of 验证码过多 under browser×10 Outlook)\n',
        1,
    )

old_get_pool = '''def get_pool(config: dict, proxies=None, log_callback=None, force_reload: bool = False) -> OutlookAccountPool:

    global _POOL, _POOL_SIG

    sig = json.dumps({

        "accounts": config.get("outlook_accounts") or "",

        "file": config.get("outlook_accounts_file") or "",

        "client_id": config.get("outlook_client_id") or "",

    }, ensure_ascii=False, sort_keys=True)

    with _POOL_LOCK:

        if _POOL is None or force_reload or sig != _POOL_SIG:

            _POOL = build_pool_from_config(config, proxies=proxies, log_callback=log_callback)

            _POOL_SIG = sig

        else:

            _POOL.log_callback = log_callback

            _POOL.proxies = proxies

        return _POOL
'''

new_get_pool = '''def get_pool(config: dict, proxies=None, log_callback=None, force_reload: bool = False) -> OutlookAccountPool:

    global _POOL, _POOL_SIG

    # 18r35b: DO NOT put outlook_accounts text into sig.
    # persist/sync rewrites config text constantly; rebuilding wipes in_use and lets
    # multiple workers acquire the same mailbox -> dual CreateEmail -> 验证码过多.
    sig = json.dumps({
        "file": config.get("outlook_accounts_file") or "",
        "client_id": config.get("outlook_client_id") or "",
    }, ensure_ascii=False, sort_keys=True)

    with _POOL_LOCK:
        need_build = _POOL is None or force_reload or sig != _POOL_SIG
        if need_build:
            old = _POOL
            new_pool = build_pool_from_config(config, proxies=proxies, log_callback=log_callback)
            if old is not None:
                try:
                    old_by = {}
                    for a in (getattr(old, "accounts", None) or []):
                        try:
                            old_by[a.identity()] = a
                        except Exception:
                            continue
                    preserved_in_use = 0
                    for a in (getattr(new_pool, "accounts", None) or []):
                        prev = old_by.get(a.identity())
                        if not prev:
                            continue
                        # preserve runtime lease / cooldown / live tokens
                        try:
                            if getattr(prev, "status", "") == "in_use":
                                a.status = "in_use"
                                preserved_in_use += 1
                            elif getattr(prev, "status", "") in ("bad", "registered"):
                                a.status = prev.status
                            if float(getattr(prev, "cooldown_until", 0) or 0) > float(getattr(a, "cooldown_until", 0) or 0):
                                a.cooldown_until = prev.cooldown_until
                            if getattr(prev, "access_token", ""):
                                a.access_token = prev.access_token
                                a.access_expires_at = getattr(prev, "access_expires_at", 0) or a.access_expires_at
                            if getattr(prev, "refresh_token", ""):
                                a.refresh_token = prev.refresh_token
                            if getattr(prev, "last_used_at", 0):
                                a.last_used_at = prev.last_used_at
                            if getattr(prev, "last_error", ""):
                                a.last_error = prev.last_error
                        except Exception:
                            continue
                    if log_callback and preserved_in_use:
                        try:
                            log_callback(
                                f"[*] Outlook pool rebuild preserved in_use={preserved_in_use} "
                                f"total={len(getattr(new_pool, 'accounts', []) or [])}"
                            )
                        except Exception:
                            pass
                    # keep cursor roughly stable
                    try:
                        new_pool._idx = int(getattr(old, "_idx", 0) or 0) % max(1, len(new_pool.accounts) or 1)
                    except Exception:
                        pass
                except Exception as merge_exc:
                    if log_callback:
                        try:
                            log_callback(f"[!] Outlook pool rebuild merge skip: {merge_exc}")
                        except Exception:
                            pass
            _POOL = new_pool
            _POOL_SIG = sig
        else:
            _POOL.log_callback = log_callback
            _POOL.proxies = proxies
        return _POOL
'''

if old_get_pool not in om:
    # try compacted variant without blank lines between every line
    om2 = om
    # looser replace via regex
    m = re.search(r'def get_pool\(config: dict, proxies=None, log_callback=None, force_reload: bool = False\) -> OutlookAccountPool:.*?return _POOL\n', om, re.S)
    if not m:
        raise SystemExit('outlook get_pool block not found')
    om = om[:m.start()] + new_get_pool + om[m.end():]
else:
    om = om.replace(old_get_pool, new_get_pool)

om_path.write_text(om, encoding='utf-8')
print('outlook_mail.py patched')

# ---------- aol_mail.py ----------
am_path = root / 'aol_mail.py'
am = am_path.read_text(encoding='utf-8')
if '18r35b: preserve in_use' not in am:
    am = am.replace(
        '"""',
        '"""\n# 2026-07-20r35b: preserve in_use/cooldown across force_reload (anti dual-mailbox).\n',
        1,
    )
m = re.search(r'def get_pool\(config: dict, log_callback=None, force_reload: bool = False\) -> AolAccountPool:.*?return _POOL\n', am, re.S)
if not m:
    raise SystemExit('aol get_pool not found')
new_aol = '''def get_pool(config: dict, log_callback=None, force_reload: bool = False) -> AolAccountPool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None or force_reload:
            old = _POOL
            new_pool = build_pool_from_config(config, log_callback=log_callback)
            if old is not None:
                try:
                    old_by = {}
                    for a in (getattr(old, "accounts", None) or []):
                        try:
                            old_by[str(getattr(a, "email", "") or "").strip().lower()] = a
                        except Exception:
                            continue
                    preserved = 0
                    for a in (getattr(new_pool, "accounts", None) or []):
                        key = str(getattr(a, "email", "") or "").strip().lower()
                        prev = old_by.get(key)
                        if not prev:
                            continue
                        try:
                            if getattr(prev, "status", "") == "in_use":
                                a.status = "in_use"
                                preserved += 1
                            elif getattr(prev, "status", "") in ("bad", "registered"):
                                a.status = prev.status
                            if float(getattr(prev, "cooldown_until", 0) or 0) > float(getattr(a, "cooldown_until", 0) or 0):
                                a.cooldown_until = prev.cooldown_until
                            if getattr(prev, "last_used_at", 0):
                                a.last_used_at = prev.last_used_at
                            if getattr(prev, "last_error", ""):
                                a.last_error = prev.last_error
                        except Exception:
                            continue
                    if log_callback and preserved:
                        try:
                            log_callback(f"[*] AOL pool rebuild preserved in_use={preserved}")
                        except Exception:
                            pass
                    try:
                        new_pool._idx = int(getattr(old, "_idx", 0) or 0) % max(1, len(new_pool.accounts) or 1)
                    except Exception:
                        pass
                except Exception as merge_exc:
                    if log_callback:
                        try:
                            log_callback(f"[!] AOL pool rebuild merge skip: {merge_exc}")
                        except Exception:
                            pass
            _POOL = new_pool
        elif log_callback and _POOL.log_callback is not log_callback:
            _POOL.log_callback = log_callback
        return _POOL
'''
am = am[:m.start()] + new_aol + am[m.end():]
am_path.write_text(am, encoding='utf-8')
print('aol_mail.py patched')

# ---------- hybrid_register.py: stop force_reload on credential lookup ----------
hr_path = root / 'hybrid_register.py'
hr = hr_path.read_text(encoding='utf-8')
if '18r35b' not in hr[:2500]:
    hr = hr.replace(
        'Changelog:',
        'Changelog:\n- 2026-07-20r35b: mailbox token lookup no longer force_reload pools (preserve in_use).\n',
        1,
    )
hr = hr.replace(
    'pool = _am.get_pool(getattr(engine, "config", None), force_reload=True)',
    'pool = _am.get_pool(getattr(engine, "config", None), force_reload=False)',
)
hr = hr.replace(
    'pool = _am.get_pool(force_reload=True)',
    'pool = _am.get_pool(force_reload=False)',
)
hr = hr.replace(
    'pool = _om.get_pool(getattr(engine, "config", None), force_reload=True)',
    'pool = _om.get_pool(getattr(engine, "config", None), force_reload=False)',
)
hr = hr.replace(
    'pool = _om.get_pool(force_reload=True)',
    'pool = _om.get_pool(force_reload=False)',
)
hr_path.write_text(hr, encoding='utf-8')
print('hybrid_register.py patched')

# ---------- grok_register_ttk.py: detect rate limit after fill_email; smarter resend ----------
ttk_path = root / 'grok_register_ttk.py'
ttk = ttk_path.read_text(encoding='utf-8')

# add helper near fill_email if missing
if 'def detect_page_create_email_rate_limit' not in ttk:
    helper = '''

def detect_page_create_email_rate_limit(page=None, log_callback=None) -> tuple[bool, str]:
    """Browser-path detector for xAI CreateEmail '验证码过多' / too-many-codes UI."""
    try:
        from hybrid_register import detect_create_email_rate_limit
    except Exception:
        detect_create_email_rate_limit = None
    pg = page
    if pg is None:
        try:
            pg = _get_page()
        except Exception:
            pg = None
    if pg is None:
        return False, ""
    body = ""
    try:
        body = pg.run_js(
            r"""
try {
  const t = (document.body && (document.body.innerText || document.body.textContent) || '');
  return String(t || '').slice(0, 4000);
} catch (e) { return ''; }
"""
        ) or ""
    except Exception as exc:
        if log_callback:
            try:
                log_callback(f"[!] rate-limit page scrape fail: {exc}")
            except Exception:
                pass
        body = ""
    url = ""
    try:
        url = str(getattr(pg, "url", "") or "")
    except Exception:
        url = ""
    if detect_create_email_rate_limit is not None:
        hit, ev = detect_create_email_rate_limit(body, url)
        if hit:
            return True, ev
    # local fallback needles
    low = f"{body} {url}".lower()
    needles = (
        "验证码过多",
        "发送到此邮箱的验证码过多",
        "too many verification",
        "too many codes",
        "too many code",
        "try again later",
        "please try again in",
    )
    for n in needles:
        if n.lower() in low or n in body:
            return True, f"needle={n!r} body={(body or '')[:500]}"
    if (("minute" in low or "minutes" in low or "分钟" in body)
            and ("retry" in low or "重试" in body or "too many" in low or "过多" in body)):
        return True, f"needle='minute+retry' body={(body or '')[:500]}"
    return False, ""


'''
    # insert before fill_email_and_submit
    anchor = 'def fill_email_and_submit(timeout=75, log_callback=None, cancel_callback=None):'
    if anchor not in ttk:
        raise SystemExit('fill_email_and_submit not found')
    ttk = ttk.replace(anchor, helper + anchor, 1)

# after successful click in fill_email_and_submit, check rate limit before return
old_click_ok = '''        if clicked:
            if log_callback:
                detail = f" ({clicked})" if isinstance(clicked, str) else ""
                log_callback(f"[*] 已填写邮箱并提交: {email}{detail}")
            return email, dev_token
'''
new_click_ok = '''        if clicked:
            if log_callback:
                detail = f" ({clicked})" if isinstance(clicked, str) else ""
                log_callback(f"[*] 已填写邮箱并提交: {email}{detail}")
            # 18r35b: wait briefly then detect CreateEmail rate-limit UI (验证码过多)
            # so we switch mailbox instead of polling an empty inbox for 2 minutes.
            try:
                sleep_with_cancel(1.2, cancel_callback)
            except Exception:
                time.sleep(1.2)
            rl_hit, rl_ev = detect_page_create_email_rate_limit(page=_get_page(), log_callback=log_callback)
            if rl_hit:
                if log_callback:
                    log_callback(
                        f"[!] CreateEmail RATE_LIMITED email={email} evidence={rl_ev}"
                    )
                # burn/remove handled by caller via exception keywords
                raise Exception(
                    f"create_email_rate_limited email={email} evidence={rl_ev}"
                )
            # second check a bit later (UI text may paint after spinner)
            try:
                sleep_with_cancel(1.5, cancel_callback)
            except Exception:
                time.sleep(1.5)
            rl_hit2, rl_ev2 = detect_page_create_email_rate_limit(page=_get_page(), log_callback=log_callback)
            if rl_hit2:
                if log_callback:
                    log_callback(
                        f"[!] CreateEmail RATE_LIMITED(late) email={email} evidence={rl_ev2}"
                    )
                raise Exception(
                    f"create_email_rate_limited email={email} evidence={rl_ev2}"
                )
            return email, dev_token
'''
if old_click_ok not in ttk:
    raise SystemExit('click ok block not found')
ttk = ttk.replace(old_click_ok, new_click_ok, 1)

# make browser resend much more conservative: only after 90s, and skip if rate-limit text present
old_resend = '''def fill_code_and_submit(email, dev_token, timeout=180, log_callback=None, cancel_callback=None):
    def _resend_code():
        page = _get_page()
        if page is None:
            return False
        page.run_js(
'''
# read actual resend function block to replace carefully
m = re.search(r'def fill_code_and_submit\(email, dev_token, timeout=180, log_callback=None, cancel_callback=None\):\n    def _resend_code\(\):.*?code = get_oai_code\(', ttk, re.S)
if not m:
    raise SystemExit('fill_code_and_submit block not found')
block = m.group(0)
# replace resend body start
new_block = '''def fill_code_and_submit(email, dev_token, timeout=180, log_callback=None, cancel_callback=None):
    def _resend_code():
        page = _get_page()
        if page is None:
            return False
        # 18r35b: never auto-resend when page already shows 验证码过多
        try:
            rl_hit, rl_ev = detect_page_create_email_rate_limit(page=page, log_callback=log_callback)
            if rl_hit:
                if log_callback:
                    log_callback(f"[!] skip resend: rate-limited email={email} {rl_ev}")
                raise Exception(f"create_email_rate_limited email={email} evidence={rl_ev}")
        except Exception as _rl_exc:
            if "create_email_rate_limited" in str(_rl_exc):
                raise
        page.run_js(
'''
# keep the rest from original after page.run_js(
idx = block.find('page.run_js(')
if idx < 0:
    raise SystemExit('page.run_js in resend not found')
# Also need to change next_resend timing if present after get_oai_code - handled below
rest = block[idx + len('page.run_js('):]
# reconstruct from original after page.run_js(
orig_after = block[idx:]
# Build new: new_block already ends with page.run_js(
# take from original starting at page.run_js(
new_full = new_block + block[idx + len('page.run_js('):]
# Wait - new_block ends with 'page.run_js(\n' so we need original from after that
new_full = new_block + block.split('page.run_js(', 1)[1]
ttk = ttk[:m.start()] + new_full + ttk[m.end():]

# Also delay first resend: cloudflare path uses 35s - for get_oai_code browser call:
# fill_code uses resend_callback=_resend_code - need to see if there's interval in get_oai_code for outlook
# Outlook path ignores resend_callback currently - good.
# For safety, still bump cloudflare interval 35->120 if present near fill_code get_oai_code

# Ensure mail fail handlers treat create_email_rate_limited as switchable mail fail
for old_keys in [
'''                            _mail_fail = any(
                                k in msg
                                for k in (
                                    "early_no_new_mail",
                                    "未收到验证码",
                                    "获取验证码失败",
                                    "code_timeout",
                                    "no post-send",
                                    "验证码超时",
                                )
''',
'''                        _mail_fail = any(
                            k in msg
                            for k in (
                                "early_no_new_mail",
                                "未收到验证码",
                                "获取验证码失败",
                                "code_timeout",
                                "no post-send",
''',
]:
    if old_keys in ttk and 'create_email_rate_limited' not in old_keys:
        ttk = ttk.replace(
            old_keys,
            old_keys.replace(
                '"early_no_new_mail",',
                '"early_no_new_mail",\n                                    "create_email_rate_limited",\n                                    "验证码过多",\n                                    "RATE_LIMITED",',
            ),
        )

# broader worker mail_fail keys already has 验证码 - good

# after fill_email exception path: if rate limited, burn and continue
# inject right after fill_email_and_submit calls via wrapping is hard; exception will bubble with keyword.

if '18r35b rate-limit' not in ttk[:3000]:
    ttk = ttk.replace(
        'Changelog:',
        'Changelog:\n- 2026-07-20r35b: browser CreateEmail 验证码过多 detect+switch; pool in_use preserve (see outlook/aol).\n',
        1,
    )

ttk_path.write_text(ttk, encoding='utf-8')
print('grok_register_ttk.py patched')

# syntax check
import ast
for p in [om_path, am_path, hr_path, ttk_path]:
    ast.parse(p.read_text(encoding='utf-8'))
    print('AST_OK', p.name)

# write changelog
cl = root / 'CHANGELOG_18r35b_rate_limit_pool.md'
cl.write_text('''# 18r35b — 验证码过多 / 多 worker 同邮箱 热修

## 现象
- 页面/日志提示：发送到此邮箱的验证码过多，请在 N minutes 后重试
- browser×10 Outlook 格：大量 early_no_new_mail，同一邮箱被多个 worker 同时 poll

## 根因
1. `outlook_mail.get_pool` 把 `config.outlook_accounts` **全文**放进 pool signature；
   删号/同步写回 config 后 signature 变化 → **重建 pool** → 所有 `in_use` 清空。
2. 多线程于是再次 `acquire` 到同一邮箱，同时对 xAI CreateEmail 发码。
3. hybrid 侧 `force_reload=True` 取 token 也会触发重建。
4. browser 路径提交邮箱后**没有**检测「验证码过多」UI，继续空等收信 → 看起来像验证码问题。

## 修复
- Outlook/AOL：`get_pool` 重建时 **preserve in_use/cooldown/tokens**；Outlook sig 不再含 accounts 文本。
- hybrid token lookup：**不再 force_reload**。
- browser：`fill_email_and_submit` 提交后检测 rate-limit UI，立刻 `create_email_rate_limited` 换号；
  resend 前同样检测，禁止对已限流邮箱再点重发。

## 验证
- AST_OK 四文件
- 新 job importlib.reload 后生效（不必杀 8092）
''', encoding='utf-8')
print('changelog written', cl)
print('DONE', time.strftime('%Y-%m-%d %H:%M:%S'))
