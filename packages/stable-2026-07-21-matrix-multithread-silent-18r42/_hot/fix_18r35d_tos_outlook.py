# -*- coding: utf-8 -*-
"""18r35d hotfixes:
1) Outlook login/refresh: on proxy/network timeout, retry once via direct (no SOCKS)
2) open_signup: detect grok.com/tos-gate and hard-navigate to SIGNUP_URL / rotate proxy
"""
import ast
import os
import re
import shutil
import time

ROOT = r"C:\Users\zhang\grok-regkit"
OUTLOOK = os.path.join(ROOT, "outlook_mail.py")
TTK = os.path.join(ROOT, "grok_register_ttk.py")
HOT = os.path.join(ROOT, "_hot")
os.makedirs(HOT, exist_ok=True)
stamp = time.strftime("%Y%m%d_%H%M%S")


def bak(path: str) -> str:
    base = os.path.basename(path)
    dst = os.path.join(HOT, f"bak_18r35d_{base}_{stamp}")
    shutil.copy2(path, dst)
    return dst


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def patch_outlook(src: str) -> str:
    # Normalize only around ensure_tokens for reliable replace; keep file style.
    old = '''    def ensure_tokens(self, acc: OutlookAccount) -> OutlookAccount:

        if acc.access_token and acc.access_expires_at > _now() + 60:

            self._lg(f"[*] Outlook reuse access_token: {acc.email}")

            return acc

        sess = self._session(acc)

        if acc.refresh_token:

            try:

                data = sess.refresh_access_token(acc.refresh_token)

                acc.access_token = data["access_token"]

                acc.refresh_token = data.get("refresh_token") or acc.refresh_token

                acc.access_expires_at = _now() + int(data.get("expires_in") or 3600)

                self.cache.put(acc.email, {

                    "access_token": acc.access_token, "refresh_token": acc.refresh_token,

                    "access_expires_at": acc.access_expires_at, "client_id": acc.client_id,

                })

                self._lg(f"[+] Outlook refresh ok: {acc.email}")

                return acc

            except Exception as exc:

                self._lg(f"[!] Outlook refresh failed, try password+TOTP: {exc}")

        if acc.password and acc.totp_secret:

            data = sess.login_password_totp(acc.email, acc.password, acc.totp_secret)

            acc.access_token = data["access_token"]

            acc.refresh_token = data.get("refresh_token") or acc.refresh_token

            acc.access_expires_at = _now() + int(data.get("expires_in") or 3600)

            self.cache.put(acc.email, {

                "access_token": acc.access_token, "refresh_token": acc.refresh_token,

                "access_expires_at": acc.access_expires_at, "client_id": acc.client_id,

            })

            self._lg(f"[+] Outlook password+TOTP login ok: {acc.email}")

            return acc

        raise Exception(f"Outlook account {acc.email} has no refresh_token and missing password+totp")
'''
    new = '''    def ensure_tokens(self, acc: OutlookAccount) -> OutlookAccount:

        if acc.access_token and acc.access_expires_at > _now() + 60:

            self._lg(f"[*] Outlook reuse access_token: {acc.email}")

            return acc

        # 18r35d: login/refresh via configured proxies first; on proxy/network errors
        # retry once with direct (Graph already had direct-first). Avoid long SOCKS
        # stalls on login.microsoftonline.com under multi-worker load.
        proxy_sess = self._session(acc)
        direct_sess = None
        if self.proxies:
            try:
                direct_sess = OutlookSession(
                    client_id=acc.client_id or self.client_id,
                    proxies=None,
                    log_callback=self.log_callback,
                )
            except Exception:
                direct_sess = None

        def _apply_token_data(data: dict, how: str) -> OutlookAccount:
            acc.access_token = data["access_token"]
            acc.refresh_token = data.get("refresh_token") or acc.refresh_token
            acc.access_expires_at = _now() + int(data.get("expires_in") or 3600)
            self.cache.put(acc.email, {
                "access_token": acc.access_token,
                "refresh_token": acc.refresh_token,
                "access_expires_at": acc.access_expires_at,
                "client_id": acc.client_id,
            })
            self._lg(f"[+] Outlook {how} ok: {acc.email}")
            return acc

        if acc.refresh_token:
            last_refresh_exc = None
            for label, sess in (("proxy", proxy_sess), ("direct", direct_sess or proxy_sess)):
                if sess is None:
                    continue
                if label == "direct" and sess is proxy_sess:
                    continue
                try:
                    if label == "direct":
                        self._lg(
                            f"[*] Outlook refresh retry direct (proxy/network fail) email={acc.email}"
                        )
                    data = sess.refresh_access_token(acc.refresh_token)
                    return _apply_token_data(data, f"refresh/{label}")
                except Exception as exc:
                    last_refresh_exc = exc
                    if label == "proxy" and direct_sess is not None and _is_proxy_error(exc):
                        self._lg(
                            f"[!] Outlook refresh proxy fail, will try direct: {exc}"
                        )
                        continue
                    self._lg(f"[!] Outlook refresh failed ({label}), try password+TOTP: {exc}")
                    break
            if last_refresh_exc is not None and direct_sess is None:
                self._lg(f"[!] Outlook refresh failed, try password+TOTP: {last_refresh_exc}")

        if acc.password and acc.totp_secret:
            last_login_exc = None
            for label, sess in (("proxy", proxy_sess), ("direct", direct_sess or proxy_sess)):
                if sess is None:
                    continue
                if label == "direct" and sess is proxy_sess:
                    continue
                try:
                    if label == "direct":
                        self._lg(
                            f"[*] Outlook password+TOTP login retry direct email={acc.email}"
                        )
                    data = sess.login_password_totp(acc.email, acc.password, acc.totp_secret)
                    return _apply_token_data(data, f"password+TOTP/{label}")
                except Exception as exc:
                    last_login_exc = exc
                    info = classify_outlook_login_error(exc, auth_path="password+totp")
                    permanent = bool(info.get("permanent"))
                    if permanent:
                        raise
                    if label == "proxy" and direct_sess is not None and (
                        _is_proxy_error(exc) or info.get("category") == "network_proxy_or_timeout"
                    ):
                        self._lg(
                            f"[!] Outlook login proxy/network fail, retry direct | "
                            f"email={acc.email} exc={exc}"
                        )
                        continue
                    raise
            if last_login_exc is not None:
                raise last_login_exc

        raise Exception(f"Outlook account {acc.email} has no refresh_token and missing password+totp")
'''
    if old not in src:
        # try single-newline compacted match via regex of key markers
        m = re.search(
            r"    def ensure_tokens\(self, acc: OutlookAccount\) -> OutlookAccount:\n(?:.*\n)*?"
            r"        raise Exception\(f\"Outlook account \{acc\.email\} has no refresh_token and missing password\+totp\"\)\n",
            src,
        )
        if not m:
            raise RuntimeError("ensure_tokens block not found for patch")
        # If double-spaced, rebuild old from actual slice
        old = m.group(0)
        # convert new to double-spaced to match file style if old is double-spaced
        if "\n\n        if acc.access_token" in old or old.count("\n\n") > 10:
            # keep new with normal spacing; file already mixed in other places too? prefer match surrounding style
            # look at a nearby function spacing
            pass
        src2 = src[: m.start()] + new + src[m.end() :]
    else:
        src2 = src.replace(old, new, 1)

    # header note
    if "18r35d" not in src2[:800]:
        src2 = src2.replace(
            "create/acquire: rent mailbox from pool, ensure access_token",
            "create/acquire: rent mailbox from pool, ensure access_token\n"
            "- 2026-07-20r35d: ensure_tokens proxy/network fail -> one direct retry for refresh/password+TOTP login",
            1,
        )
    return src2


def patch_ttk(src: str) -> str:
    # bump header
    if src.startswith("# 18r35c:"):
        src = src.replace(
            "# 18r35c: CreateEmail gate + MT/serial catch rate-limit on fill_email\n",
            "# 18r35d: tos-gate escape in open_signup + keep 18r35c CreateEmail gate\n"
            "# 18r35c: CreateEmail gate + MT/serial catch rate-limit on fill_email\n",
            1,
        )
    if "2026-07-20r35d" not in src:
        src = src.replace(
            "- 2026-07-20r35b: browser CreateEmail 验证码过多 detect+switch; pool in_use preserve (see outlook/aol).\n",
            "- 2026-07-20r35d: open_signup 识别 grok.com/tos-gate，强制跳回 accounts.x.ai/sign-up 或换代理；避免成功后卡 tos-gate 找不到邮箱注册按钮。\n"
            "- 2026-07-20r35b: browser CreateEmail 验证码过多 detect+switch; pool in_use preserve (see outlook/aol).\n",
            1,
        )

    helper = '''
def page_is_tos_gate(page_obj=None):
    """True when browser landed on grok.com/tos-gate (post-login ToS) instead of signup."""
    p = page_obj or _get_page()
    if p is None:
        return False
    try:
        url = (p.url or "").lower()
    except Exception:
        url = ""
    if "tos-gate" in url or "/accept-tos" in url:
        return True
    try:
        html = (p.html or "")[:4000].lower()
    except Exception:
        html = ""
    return ("tos-gate" in html) or ("accept the terms" in html and "grok.com" in url)


def escape_tos_gate_to_signup(page_obj=None, log_callback=None, cancel_callback=None):
    """Leave tos-gate / leftover logged-in shell and force fresh signup URL."""
    p = page_obj or _get_page()
    if p is None:
        return False
    if not page_is_tos_gate(p):
        return False
    if log_callback:
        try:
            cur = p.url
        except Exception:
            cur = "?"
        log_callback(f"[!] 检测到 ToS/gate 页，强制跳转注册页: {cur}")
    try:
        p.get(SIGNUP_URL)
    except Exception as e:
        if log_callback:
            log_callback(f"[!] tos-gate navigate fail: {e}")
        return False
    try:
        p.wait.doc_loaded()
    except Exception:
        pass
    sleep_with_cancel(1.2, cancel_callback)
    try:
        # best-effort clear storage that keeps session on grok.com
        p.run_js(
            "try{localStorage.clear();sessionStorage.clear();}catch(e){}"
        )
    except Exception:
        pass
    try:
        p.get(SIGNUP_URL)
        p.wait.doc_loaded()
    except Exception:
        pass
    sleep_with_cancel(1.0, cancel_callback)
    still = page_is_tos_gate(p)
    if log_callback:
        try:
            log_callback(f"[*] tos-gate escape done url={p.url} still_gate={int(still)}")
        except Exception:
            pass
    return not still

'''

    if "def page_is_tos_gate" not in src:
        # insert before page_is_cloudflare_challenge
        anchor = "\ndef page_is_cloudflare_challenge(page_obj=None):\n"
        if anchor not in src:
            raise RuntimeError("page_is_cloudflare_challenge anchor missing")
        src = src.replace(anchor, "\n" + helper + anchor, 1)

    # inject check after URL log in open_signup_page
    needle = '''        if log_callback:
            log_callback(f"[*] 当前URL: {cur_url}")

        # Cloudflare challenge: wait then rotate proxy if still blocked
'''
    insert = '''        if log_callback:
            log_callback(f"[*] 当前URL: {cur_url}")

        # 18r35d: leftover session may land on grok.com/tos-gate — leave before click email
        try:
            page = _get_page() or page
        except Exception:
            pass
        if page_is_tos_gate(page) or ("tos-gate" in (cur_url or "").lower()):
            ok_escape = escape_tos_gate_to_signup(
                page, log_callback=log_callback, cancel_callback=cancel_callback
            )
            try:
                page = _get_page() or page
                cur_url = page.url if page is not None else cur_url
            except Exception:
                pass
            if log_callback:
                log_callback(f"[*] tos-gate 处理后 URL: {cur_url} ok={int(bool(ok_escape))}")
            if (not ok_escape) or page_is_tos_gate(page) or ("tos-gate" in (cur_url or "").lower()):
                if log_callback:
                    log_callback(
                        f"[!] tos-gate 仍在，更换代理/重启浏览器 ({round_i}/{max_proxy_rounds})"
                    )
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                continue

        # Cloudflare challenge: wait then rotate proxy if still blocked
'''
    if "18r35d: leftover session may land on grok.com/tos-gate" not in src:
        if needle not in src:
            raise RuntimeError("open_signup URL log needle missing")
        src = src.replace(needle, insert, 1)

    # also treat tos-gate as not-ready in click failure path
    bad = 'if still_cf or "未找到" in emsg or disconnected:'
    good = 'if still_cf or page_is_tos_gate(page) or "未找到" in emsg or disconnected or "tos-gate" in emsg.lower():'
    if bad in src and good not in src:
        src = src.replace(bad, good, 1)

    return src


def main():
    bak(OUTLOOK)
    bak(TTK)
    with open(OUTLOOK, encoding="utf-8", errors="replace") as f:
        o = f.read()
    with open(TTK, encoding="utf-8", errors="replace") as f:
        t = f.read()
    o2 = patch_outlook(o)
    t2 = patch_ttk(t)
    # syntax check before write
    ast.parse(o2)
    ast.parse(t2)
    write_text(OUTLOOK, o2)
    write_text(TTK, t2)
    # write changelog
    cl = os.path.join(ROOT, "CHANGELOG_18r35d_tos_gate_outlook_direct.md")
    write_text(
        cl,
        """# 18r35d — tos-gate escape + Outlook login direct fallback

## Why
- Multi-worker browser@socks5@outlook: after SSO success some workers reopen on `https://grok.com/tos-gate` and spin looking for 「使用邮箱注册」.
- Outlook `password+TOTP` / refresh through SOCKS hits `login.microsoftonline.com` timeouts/resets; Graph already falls back to direct, login did not.

## Fix
1. `grok_register_ttk.py`
   - `page_is_tos_gate` / `escape_tos_gate_to_signup`
   - `open_signup_page`: if URL/html is tos-gate → force `SIGNUP_URL`, clear storage; still gate → rotate proxy/restart browser
2. `outlook_mail.py` `ensure_tokens`
   - refresh/password+TOTP: proxy first; on proxy/network error → one **direct** retry
   - permanent auth failures still delete/burn as before (no silent keep)

## Load
Running web job keeps old modules in memory. After current matrix cell finishes, restart **only** `web/server.py` :8092 (do not kill 8010/8080/8317/8318).

## Note
Does not change main path: register → immediate SSO → pool. CreateEmail gate (18r35c) retained.
""",
    )
    print("OK 18r35d applied")
    print("OUTLOOK", OUTLOOK)
    print("TTK", TTK)


if __name__ == "__main__":
    main()
