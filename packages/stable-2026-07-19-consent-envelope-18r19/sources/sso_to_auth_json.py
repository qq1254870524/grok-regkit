#!/usr/bin/env python3
from __future__ import annotations

"""SSO cookie → CPA xai-*.json via Authorization Code + PKCE.

Fused from Git-creat7/grokRegister-cpa (MIT) into grok-regkit.

Changelog:
- 2026-07-19r19: consent 非 allow(无 code) 拉黑该 Next-Action 并继续试更多候选；
  深扫 JS chunks 不因 1 个 strong_id 早停；解析 redirect/query 中的 code；
  识别 RSC soft-nav 非 allow 响应，避免永远卡在 0071fd1191ff 类死 action。
- 2026-07-18r13: consent JS chunk discovery 默认直接 max=40 单阶段扫描（去掉 12→40 两阶段 expand）；
  保留 strong action id 早停；日志改为 "扫 max N"；不覆盖旧 package。
- 2026-07-18r11: consent JS chunk discovery 改为两阶段扫描（12 个快速阶段，必要时扩展到 40 个）；
  仅在真实解析出 action id 后早停；移除失效 hardcoded fallback 自动提交；增强空格/webpack 包装形式解析。
- 2026-07-18r10: consent JS chunk scan budget 10s / max 12 scripts / timeout 8s;
  prioritize working cache; log elapsed; faster fail to authcode retry path.
- 2026-07-18c: consent 快速路径不再默认死哈希 401b73e...；404 拉黑并清空
  _working_next_action_id；优先 HTML live action，其次上次真正成功的 action，
  硬编码仅作最后 fallback；Round0 无 live 候选时直接扫 JS chunks，去掉
  “必现第一次 404 再兜底成功”的慢路径。
- 2026-07-17 fuse-v1: Adopt upstream authcode mint (referrer=grok-build) and
  Management API upload helpers for local cpa_export + CLI backfill.

Original flow:
  SSO → authorize(referrer=grok-build) → consent → token → xai-<email>.json
  Optional: write local cpa_auth_dir and/or POST remote Management API.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
OIDC_ISSUER = "https://auth.x.ai"
AUTH_KEY = f"{OIDC_ISSUER}::{CLIENT_ID}"
# 与当前可用号 JWT scope 对齐（含 conversations:*）
SCOPES = (
    "openid profile email offline_access grok-cli:access "
    "api:access conversations:read conversations:write"
)

# --- Authorization Code Flow 常量 --------------------------------------------
# authorize 必须注入 referrer=grok-build，否则 access_token 无该 claim，
# cli-chat-proxy 会 403。实测 referrer=cli-proxy-api 会得到 referrer=None。
# plan=generic 对齐 grok-build-auth；consent.referrer 仍置空。
REDIRECT_URI = "http://127.0.0.1:56121/callback"
GROK_REFERRER = "grok-build"
GROK_PLAN = "generic"
GROK_VERSION = "0.2.93"
GROK_TOKEN_UA = f"grok-pager/{GROK_VERSION} grok-shell/{GROK_VERSION} (linux; x86_64)"
# consent 提交用的 Next.js Server Action ID（快速路径；失效时再从 consent 页 JS 动态解析）
# 2026-07 实测 createServerReference 在 accounts.x.ai chunks 内，HTML 里的 400b2e4e... 不是 consent allow
# 2026-07-18: 401b73e... 对当前前端已 404，不再作为默认快速路径首候选。
NEXT_ACTION_ID = "401b73e22a5e68737d0037e1aa449fef82cd1b35fb"
# 仅缓存“真正返回 authorization code”的 action；初始为空，避免必现死哈希 404。
_working_next_action_id = ""
# 进程内拉黑：404 / server action not found 的 action 不再优先重试。
_blacklisted_next_action_ids: set[str] = set()
_NEXT_ACTION_RE = re.compile(
    r'(?:\$ACTION_ID_|next-action["\']?\s*[:=]\s*["\']|["\'])([0-9a-f]{40,44})["\']',
    re.I,
)
_CREATE_SERVER_REF_RE = re.compile(
    r'createServerReference\s*\)?\s*\(\s*["\']([0-9a-f]{40,44})["\']',
    re.I,
)
_CALL_SERVER_RE = re.compile(
    r'["\']([0-9a-f]{40,44})["\']\s*,\s*(?:callServer|findSourceMapURL)',
    re.I,
)
_SCRIPT_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.I)

# --- CLIProxyAPI (CPA) 扁平格式常量 ------------------------------------------
# CPA 的 internal/auth/xai/token.go TokenStorage 读的是扁平字段。
# Build/CLI token（scope 含 grok-cli:access）必须走 cli-chat-proxy.grok.com，
# 不能用默认 api.x.ai/v1（那是计费通道，会 402）。
# headers 对齐 @xai-official/grok CLI / grok-build-auth（无 x-authenticateresponse）
CPA_TOKEN_ENDPOINT = f"{OIDC_ISSUER}/oauth2/token"
CPA_GROK_BASE_URL = "https://cli-chat-proxy.grok.com/v1"
CPA_GROK_HEADERS = {
    "User-Agent": GROK_TOKEN_UA,
    "X-XAI-Token-Auth": "xai-grok-cli",
    "x-authenticateresponse": "authenticate-response",
    "x-grok-client-identifier": "grok-pager",
    "x-grok-client-version": GROK_VERSION,
}
CPA_PROBE_MODEL = "grok-4.5"
CPA_PROBE_URL = f"{CPA_GROK_BASE_URL}/responses"


def b64url_decode(seg: str) -> bytes:
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg)


def decode_jwt_payload(token: str) -> dict:
    try:
        return json.loads(b64url_decode(token.split(".")[1]))
    except Exception:
        return {}


def rfc3339_ns(ts: float | None = None) -> str:
    """2026-07-10T01:00:00.000000000Z"""
    if ts is None:
        ts = time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"


def _urlopen(req, proxy: str = "", timeout: int = 15):
    """urllib 请求，proxy 非空时走代理。"""
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def _gen_pkce() -> tuple[str, str, str, str]:
    """生成 (code_verifier, code_challenge, state, nonce)。"""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    return verifier, challenge, state, nonce


def _parse_consent_code(body: str) -> str | None:
    """从 consent 提交的 text/x-component 响应里解析出 authorization code。

    兼容：
    - JSON 对象含 code
    - redirect URL / query 字符串 code=
    - RSC soft-nav q= 参数内嵌 code
    """
    text = body or ""
    for m in re.finditer(r"(?:[?&#]|^)code=([A-Za-z0-9._~+/-]+)", text):
        code = urllib.parse.unquote(m.group(1) or "").strip()
        if code and code.lower() not in ("null", "undefined", "none"):
            # avoid matching response_type=code alone
            start = m.start()
            prefix = text[max(0, start - 20):start]
            if "response_type=" in prefix:
                continue
            return code
    for line in text.split("\n"):
        start = line.find("{")
        if start < 0:
            continue
        try:
            data = json.loads(line[start:])
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("success") is False:
            continue
        if data.get("code"):
            return str(data.get("code"))
        for key in ("q", "url", "href", "redirect", "location"):
            val = data.get(key)
            if not isinstance(val, str) or not val:
                continue
            mm = re.search(r"(?:[?&#])code=([A-Za-z0-9._~+/-]+)", val)
            if mm:
                code = urllib.parse.unquote(mm.group(1) or "").strip()
                if code:
                    return code
    return None


def _is_non_allow_consent_body(body: str) -> bool:
    """True when response is clearly NOT consent-allow (RSC soft-nav / wrong action)."""
    b = (body or "").strip()
    if not b:
        return True
    low = b.lower()
    if "incomplete envelope" in low or "invalid_argument" in low:
        return True
    if "server action not found" in low:
        return True
    if '"a":"$@' in b or '"a": "$@' in b:
        if re.search(r"[?&#]code=", b) is None and '"code"' not in b:
            return True
    # authorize query echoed without issued auth code
    if "response_type=code" in low and "client_id=" in low and "redirect_uri=" in low:
        if re.search(r"(?:[?&#])code=", b) is None:
            return True
    return False


def _extract_next_action_ids(html: str, *, include_hardcoded_fallback: bool = False) -> list[str]:
    """仅从 HTML 文本抽哈希（弱信号；真正 id 多在 JS chunk）。"""
    found: list[str] = []
    seen: set[str] = set()
    text = html or ""

    def _add(val: str):
        v = (val or "").strip().lower()
        if len(v) < 40 or v in seen:
            return
        seen.add(v)
        found.append(v)

    for m in _CREATE_SERVER_REF_RE.finditer(text):
        _add(m.group(1))
    for m in _CALL_SERVER_RE.finditer(text):
        _add(m.group(1))
    for m in _NEXT_ACTION_RE.finditer(text):
        _add(m.group(1))
    if include_hardcoded_fallback:
        fb = str(NEXT_ACTION_ID or "").strip().lower()
        if fb and fb not in seen and fb not in _blacklisted_next_action_ids:
            found.append(fb)
    return found


def _discover_action_ids_from_js(session, html: str, base_url: str = "https://accounts.x.ai", log=None) -> list[str]:
    """Discover live consent Server Actions from referenced Next.js chunks.

    18r13 defaults to a single max scan (total_limit=40). No fast-12 then expand-40
    two-phase path. A chunk containing consent/allow words is not itself success:
    early-stop requires an actual createServerReference/callServer id.
    """
    t0 = time.time()
    found: list[str] = []
    priority: list[str] = []
    seen: set[str] = set()
    fetched_urls: set[str] = set()

    def _add(val: str, prefer: bool = False) -> bool:
        v = (val or "").strip().lower()
        if len(v) < 40 or v in seen or v in _blacklisted_next_action_ids:
            return False
        seen.add(v)
        (priority if prefer else found).append(v)
        return True

    cached = str(_working_next_action_id or "").strip().lower()
    if cached and cached not in _blacklisted_next_action_ids:
        _add(cached, prefer=True)

    scored: list[tuple[int, int, str]] = []
    for pos, src in enumerate(_SCRIPT_SRC_RE.findall(html or "")):
        low = src.lower()
        if "chunk" not in low and "/_next/" not in low:
            continue
        score = 0
        if any(k in low for k in ("consent", "oauth", "auth", "login", "sign")):
            score += 5
        if any(k in low for k in ("app", "page", "main", "layout")):
            score += 1
        scored.append((score, pos, src))
    scored.sort(key=lambda item: (-item[0], item[1]))

    # 18r13: default max single-phase scan (no fast-12 → expand-40).
    total_limit = 40
    total_budget = 28.0
    per_timeout = 8
    fetched = 0
    strong_ids = 0

    def _scan_until(limit: int, budget: float, phase: str) -> None:
        nonlocal fetched, strong_ids
        for score, _pos, src in scored:
            if fetched >= limit or (time.time() - t0) >= budget:
                break
            full = src if src.startswith("http") else urllib.parse.urljoin(base_url.rstrip("/") + "/", src.lstrip("/"))
            if full in fetched_urls:
                continue
            fetched_urls.add(full)
            try:
                resp = session.get(full, impersonate="chrome", timeout=per_timeout)
                text = str(resp.text or "")
            except Exception as exc:
                if log:
                    log(f"  [*] consent JS {phase} fetch fail file={urllib.parse.urlparse(full).path.rsplit('/', 1)[-1]} type={type(exc).__name__}")
                continue
            fetched += 1
            low_text = text.lower()
            context_prefer = score > 0 or ("consent" in low_text and "oauth" in low_text)
            if "allow" in low_text and ("consent" in low_text or "oauth" in low_text):
                context_prefer = True
            added_here = 0
            for regex in (_CREATE_SERVER_REF_RE, _CALL_SERVER_RE):
                for match in regex.finditer(text):
                    lo = max(0, match.start() - 240)
                    hi = min(len(text), match.end() + 240)
                    context = text[lo:hi].lower()
                    prefer = context_prefer or any(k in context for k in ("consent", "allow", "oauth2/consent", '"action":"allow"'))
                    if _add(match.group(1), prefer=prefer):
                        added_here += 1
                        if prefer:
                            strong_ids += 1
            # 18r19: do NOT early-stop on first strong_id — wrong page actions
            # (e.g. 0071fd1191ff soft-nav) often appear first. Prefer collecting
            # several prefer ids or scanning enough scripts.
            if strong_ids >= 3 and added_here > 0 and fetched >= 8:
                break
            if strong_ids >= 1 and fetched >= 25 and len(priority) + len(found) >= 3:
                break

    if log:
        log(f"  [*] consent JS max-scan start limit={total_limit} budget={total_budget:.0f}s scripts={len(scored)}")
    _scan_until(total_limit, total_budget, "max")

    for aid in _extract_next_action_ids(html, include_hardcoded_fallback=False):
        _add(aid, prefer=False)
    ordered = priority + [x for x in found if x not in priority]
    if log:
        log(f"  [*] 从 JS chunks 解析 Next-Action {len(ordered)} 个（max扫 {fetched}/{total_limit} 个脚本, elapsed={time.time()-t0:.1f}s, strong_ids={strong_ids}）")
    return ordered

def sso_to_token(sso_cookie: str, proxy: str = "", log=print) -> dict | None:
    """SSO cookie → token dict (access/refresh/expires_in)。

    使用授权码流程（Authorization Code + PKCE）：
    authorize 注入 referrer=grok-build + plan=generic，
    consent 优先 HTML live action / 上次真正成功的 Next-Action；
    死哈希与 404 拉黑；无 live 候选时直接扫 JS chunks。
    """
    global _working_next_action_id

    proxies = {"http": proxy, "https": proxy} if proxy else None
    s = requests.Session()
    if proxies:
        s.proxies = proxies
    # accounts.x.ai / auth.x.ai 都要带 sso（与 grok-build 授权码流程一致）
    for domain in (".x.ai", "accounts.x.ai", "auth.x.ai"):
        s.cookies.set("sso", sso_cookie, domain=domain)
        s.cookies.set("sso-rw", sso_cookie, domain=domain)

    try:
        r = s.get("https://accounts.x.ai/", impersonate="chrome", timeout=15)
    except Exception as e:
        log(f"  ❌ 网络错误: {e}")
        return None
    if "sign-in" in r.url or "sign-up" in r.url:
        log("  ❌ sso 无效")
        return None
    log("  ✅ sso 有效")

    verifier, challenge, state, nonce = _gen_pkce()

    # 1) 打开 authorize 页，跟随重定向进入 consent
    log(f"  🔑 Authorization Code Flow (referrer={GROK_REFERRER}, plan={GROK_PLAN})...")
    authorize_params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
        "plan": GROK_PLAN,
        "redirect_uri": REDIRECT_URI,
        "referrer": GROK_REFERRER,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    })
    authorize_url = f"{OIDC_ISSUER}/oauth2/authorize?{authorize_params}"

    def _open_consent(discover_actions=False):
        try:
            resp = s.get(
                authorize_url,
                impersonate="chrome",
                timeout=15,
                allow_redirects=True,
            )
        except Exception as e:
            log(f"  ❌ authorize 异常: {e}")
            return None, "", []
        url = str(resp.url)
        if "sign-in" in url or "sign-up" in url:
            log("  ❌ sso 无效")
            return None, url, []
        if "/oauth2/consent" not in url:
            log(f"  ❌ authorize 未进入 consent: {url}")
            return None, url, []
        html = str(resp.text or "")
        # consent 实际在 accounts.x.ai（从 auth.x.ai authorize 重定向）
        base = "https://accounts.x.ai"
        if "auth.x.ai" in url and "accounts.x.ai" not in url:
            base = "https://auth.x.ai"
        if discover_actions:
            action_ids = _discover_action_ids_from_js(s, html, base_url=base, log=log)
        else:
            action_ids = []
            # 1) HTML 内 live action（若有）
            for action_id in _extract_next_action_ids(html, include_hardcoded_fallback=False):
                if action_id in _blacklisted_next_action_ids:
                    continue
                if action_id not in action_ids:
                    action_ids.append(action_id)
            # 2) 上次真正成功的 working id（非硬编码死哈希）
            cached = str(_working_next_action_id or "").strip().lower()
            if (
                cached
                and cached not in _blacklisted_next_action_ids
                and cached != str(NEXT_ACTION_ID or "").strip().lower()
                and cached not in action_ids
            ):
                # 成功缓存放最前：已知可工作
                action_ids.insert(0, cached)
            log(
                f"  [*] consent 快速路径 Next-Action {len(action_ids)} 个"
                f"（HTML/缓存；跳过 JS chunks；已拉黑 {len(_blacklisted_next_action_ids)}）"
            )
        return resp, url, action_ids

    r, final_url, action_ids = _open_consent()
    if r is None:
        return None
    if not action_ids:
        # 无 HTML/缓存 live 候选：直接扫 JS，避免先 POST 死哈希 404
        log("  [*] 快速路径无 live Next-Action，直接扫描 JS chunks...")
        r, final_url, action_ids = _open_consent(discover_actions=True)
        if r is None:
            return None
    if not action_ids:
        log("  ❌ 未解析到 live Next-Action；拒绝提交已知失效 hardcoded fallback")
        return None
    else:
        log(f"  [*] consent Next-Action 候选 {len(action_ids)} 个（首个 {action_ids[0][:12]}...）")

    # 2) 提交 consent（allow），拿 authorization code
    # consent 也必须带 referrer=grok-build，否则 JWT claim 为 None
    consent_payload = json.dumps([{
        "action": "allow",
        "clientId": CLIENT_ID,
        "redirectUri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "codeChallenge": challenge,
        "codeChallengeMethod": "S256",
        "nonce": nonce,
        "principalType": "User",
        "principalId": "",
        "referrer": GROK_REFERRER,
    }])

    code = None
    last_err = ""
    tried: set[str] = set()
    # 最多 3 轮：快速路径 → 深扫 JS → 再深扫（排除已拉黑）。
    for round_i in range(3):
        if round_i > 0:
            log(
                f"  [*] consent 失败 round={round_i}，重新进入 authorize/consent 并解析 Next-Action"
                f"（已试 {len(tried)} 个，已拉黑 {len(_blacklisted_next_action_ids)}）..."
            )
            r, final_url, action_ids = _open_consent(discover_actions=True)
            if r is None:
                return None
            action_ids = [
                a for a in action_ids
                if a not in tried and a not in _blacklisted_next_action_ids
            ]
            if not action_ids:
                log("  ❌ JS 扩展扫描仍无新的 live Next-Action；停止 consent 提交")
                break
            log(f"  [*] round={round_i} 新候选 {len(action_ids)} 个（首个 {action_ids[0][:12]}...）")

        for action_id in action_ids[:12]:
            if action_id in tried:
                continue
            if action_id in _blacklisted_next_action_ids:
                continue
            tried.add(action_id)
            try:
                r = s.post(
                    final_url,
                    data=consent_payload,
                    headers={
                        "Content-Type": "text/plain;charset=UTF-8",
                        "Accept": "text/x-component",
                        "Origin": "https://accounts.x.ai",
                        "Referer": final_url,
                        "Next-Action": action_id,
                    },
                    impersonate="chrome",
                    timeout=12,
                    allow_redirects=True,
                )
            except Exception as e:
                last_err = f"consent 异常: {e}"
                log(f"  ❌ {last_err}")
                continue
            body = str(r.text or "")
            if r.status_code == 404 or "server action not found" in body.lower():
                last_err = f"consent HTTP {r.status_code}: {body[:160]}"
                log(f"  ⚠️ Next-Action {action_id[:12]}... 无效: {last_err}")
                _blacklisted_next_action_ids.add(action_id)
                if str(_working_next_action_id or "").strip().lower() == action_id:
                    _working_next_action_id = ""
                    log(f"  [*] 已清空失效 working Next-Action {action_id[:12]}...")
                else:
                    log(f"  [*] 已拉黑无效 Next-Action {action_id[:12]}...")
                continue
            if r.status_code < 200 or r.status_code >= 300:
                last_err = f"consent HTTP {r.status_code}: {body[:200]}"
                log(f"  ⚠️ {last_err}")
                continue
            try:
                final_loc = str(getattr(r, "url", "") or "")
            except Exception:
                final_loc = ""
            code = _parse_consent_code(body + "\n" + final_loc)
            if code:
                _working_next_action_id = action_id
                log(f"  [*] Next-Action {action_id[:12]}... 返回 authorization code len={len(code)}")
                break
            # 200 但无 code：拉黑，避免每轮卡在 0071fd1191ff soft-nav
            last_err = f"consent 未返回 code: {body[:220]}"
            non_allow = _is_non_allow_consent_body(body)
            log(
                f"  ⚠️ Next-Action {action_id[:12]}... 非 allow 响应"
                f"{' (soft-nav/wrong-action)' if non_allow else ''}，拉黑并继续试"
                f" body_head={body[:120]!r}"
            )
            _blacklisted_next_action_ids.add(action_id)
            if str(_working_next_action_id or "").strip().lower() == action_id:
                _working_next_action_id = ""
        if code:
            break

    if not code:
        log(f"  ❌ consent 失败（已试 {len(tried)} 个 Next-Action）: {last_err}")
        return None
    log("  ✅ 授权确认")

    # 3) 用 authorization code 换 token
    token_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": verifier,
    })
    try:
        r = s.post(
            f"{OIDC_ISSUER}/oauth2/token",
            data=token_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": GROK_TOKEN_UA,
                "X-Grok-Client-Version": GROK_VERSION,
                "Accept": "*/*",
            },
            impersonate="chrome",
            timeout=15,
        )
    except Exception as e:
        log(f"  ❌ token 异常: {e}")
        return None
    if r.status_code < 200 or r.status_code >= 300:
        log(f"  ❌ token HTTP {r.status_code}: {str(r.text)[:200]}")
        return None
    try:
        token = r.json()
    except Exception:
        log(f"  ❌ token 返回非 JSON: {str(r.text)[:200]}")
        return None
    if not token.get("access_token"):
        log(f"  ❌ token 缺少 access_token: {token}")
        return None
    if not token.get("expires_in"):
        token["expires_in"] = 21600
    if not token.get("token_type"):
        token["token_type"] = "Bearer"

    # 校验 referrer claim（authorize 注入 cli-proxy-api 后应写入 JWT）
    ap = decode_jwt_payload(token["access_token"])
    ref = ap.get("referrer")
    if ref not in (GROK_REFERRER, "grok-build", "cli-proxy-api"):
        log(f"  ⚠️ access_token referrer={ref!r}（预期 {GROK_REFERRER!r} 或 grok-build）")
    else:
        log(f"  ✅ access_token referrer={ref!r}")
    log(
        f"  ✅ access_token (expires_in={token.get('expires_in')}s)"
        + (" + refresh_token" if token.get("refresh_token") else "")
    )
    return token


def token_to_auth_entry(token: dict, email: str = "") -> tuple[str, dict]:
    """
    返回 (top_level_key, entry)
    top_level_key 固定为 issuer::client_id（与 ~/.grok/auth.json 一致）
    """
    access = token.get("access_token") or token.get("key") or ""
    refresh = token.get("refresh_token") or ""
    payload = decode_jwt_payload(access)

    user_id = payload.get("sub") or payload.get("principal_id") or ""
    principal_id = payload.get("principal_id") or user_id
    principal_type = payload.get("principal_type") or "User"

    expires_in = int(token.get("expires_in") or 21600)
    # 优先用 JWT exp
    if "exp" in payload:
        expires_at = rfc3339_ns(float(payload["exp"]))
    else:
        expires_at = rfc3339_ns(time.time() + expires_in)

    iat = payload.get("iat")
    create_time = rfc3339_ns(float(iat) if iat else time.time())

    entry = {
        "key": access,
        "auth_mode": "oidc",
        "create_time": create_time,
        "user_id": user_id,
        "email": email or "",
        "principal_type": principal_type,
        "principal_id": principal_id,
        "refresh_token": refresh,
        "expires_at": expires_at,
        "oidc_issuer": OIDC_ISSUER,
        "oidc_client_id": CLIENT_ID,
    }
    return AUTH_KEY, entry


def _iso_utc_from_unix(ts) -> str:
    """unix 秒 → CPA 认的 RFC3339（秒级，带 Z）。"""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _safe_email_for_filename(email: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in email)
    return safe or "unknown"


def token_to_cpa_record(token: dict, email: str = "", sso: str = "") -> dict:
    """token dict → CLIProxyAPI 扁平 xai auth 记录。

    对齐 CPA internal/auth/xai/token.go 的 TokenStorage 字段，以及
    grok-build-auth build_cliproxyapi_auth_record 的输出。
    """
    access = token.get("access_token") or token.get("key") or ""
    refresh = token.get("refresh_token") or ""
    id_token = token.get("id_token") or ""
    payload = decode_jwt_payload(access)
    id_payload = decode_jwt_payload(id_token) if id_token else {}

    if not email:
        email = id_payload.get("email") or payload.get("email") or ""
    sub = payload.get("sub") or id_payload.get("sub") or ""

    # expired: 优先 access token 的 exp，其次 expires_in 推算
    expired = ""
    if "exp" in payload:
        expired = _iso_utc_from_unix(payload["exp"])
    elif token.get("expires_in") is not None:
        try:
            expired = _iso_utc_from_unix(int(time.time()) + int(token["expires_in"]))
        except Exception:
            expired = ""

    record = {
        "type": "xai",
        "auth_kind": "oauth",
        "email": email or "",
        "sub": sub,
        "access_token": access,
        "refresh_token": refresh,
        "id_token": id_token,
        "token_type": token.get("token_type", "Bearer"),
        "expires_in": token.get("expires_in", None),
        "expired": expired,
        "last_refresh": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redirect_uri": REDIRECT_URI,
        "token_endpoint": CPA_TOKEN_ENDPOINT,
        "base_url": CPA_GROK_BASE_URL,
        "disabled": False,
        "headers": dict(CPA_GROK_HEADERS),
    }
    sso_val = str(sso or "").strip()
    if sso_val:
        record["sso"] = sso_val
    return record


def cpa_auth_filename(record: dict) -> str:
    """生成 CPA auth 文件名：xai-<email>.json。"""
    ident = str(record.get("email") or "").strip() or str(record.get("sub") or "").strip()
    safe = _safe_email_for_filename(ident)
    # 避免 email 本地部分已是 xai 时出现 "xai-xai..."
    fname = safe if safe.lower().startswith("xai") else f"xai-{safe}"
    return f"{fname}.json"


def probe_cpa_record(
    record: dict,
    proxy: str = "",
    timeout: int = 30,
    model: str = CPA_PROBE_MODEL,
) -> tuple[int | None, str]:
    """直连 CLI chat proxy 自测，返回 (HTTP 状态码, 响应摘要)。"""
    access = str(record.get("access_token") or "").strip()
    if not access:
        return None, "missing access_token"

    headers = dict(record.get("headers") or {})
    headers["Authorization"] = f"Bearer {access}"
    headers["Content-Type"] = "application/json"
    kwargs = {
        "headers": headers,
        "json": {
            "model": model,
            "input": "ping",
            "max_output_tokens": 2,
            "stream": False,
        },
        "impersonate": "chrome",
        "timeout": timeout,
    }
    if proxy:
        kwargs["proxy"] = proxy
    try:
        resp = requests.post(CPA_PROBE_URL, **kwargs)
        summary = str(resp.text or "").replace("\n", " ").strip()
        return int(resp.status_code), summary[:300]
    except Exception as exc:
        return None, str(exc)[:300]


def write_cpa_auth(auth_dir: Path, record: dict) -> Path:
    """写出 CPA 可热加载的 xai-<email>.json（原子替换）。

    无 email 时用 sub(user_id) 命名，避免多个无 email 账号写成同一个
    xai-unknown.json 互相覆盖。
    """
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / cpa_auth_filename(record)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def upload_cpa_auth_remote(
    base_url: str,
    management_key: str,
    record: dict,
    timeout: int = 30,
) -> str:
    """通过 CPA Management API 上传 auth 文件到远程实例。

    POST /v0/management/auth-files?name=<file.json>
    Header: Authorization: Bearer <management_key>
    Body: raw JSON auth record
    """
    import requests

    base = str(base_url or "").strip().rstrip("/")
    key = str(management_key or "").strip()
    if not base:
        raise ValueError("cpa_remote_url 为空")
    if not key:
        raise ValueError("cpa_management_key 为空")

    name = cpa_auth_filename(record)
    url = f"{base}/v0/management/auth-files"
    resp = requests.post(
        url,
        params={"name": name},
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(record, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        if len(body) > 300:
            body = body[:300] + "..."
        raise RuntimeError(f"远程上传失败 HTTP {resp.status_code}: {body or resp.reason}")
    return name


def write_auth_json(path: Path, auth_key: str, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {auth_key: entry}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_auth_json(path: Path, auth_key: str, entry: dict, unique: bool = True) -> None:
    """
    合并写入。unique=True 时 key 变成 issuer::client_id::user_id，避免多账号互相覆盖。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    key = auth_key
    if unique and entry.get("user_id"):
        key = f"{auth_key}::{entry['user_id']}"
    existing[key] = entry
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_sso_list(path: str | None, single: str | None) -> list[str]:
    if single:
        return [single.strip()]
    if not path:
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 兼容 邮箱----密码----sso
        if "----" in line:
            parts = line.split("----")
            line = parts[-1].strip()
        out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SSO cookie → grok auth.json (纯 HTTP)")
    ap.add_argument("--sso", metavar="FILE", help="sso 列表文件（一行一个 JWT，或 邮箱----密码----sso）")
    ap.add_argument("--sso-cookie", metavar="JWT", help="单个 sso cookie")
    ap.add_argument("--out", default=None, help="输出 auth.json 路径（单账号或 --merge）")
    ap.add_argument(
        "--out-dir",
        default=None,
        help="批量时每个账号写一个 {user_id}.json（可直接 cp 到 ~/.grok/auth.json）",
    )
    ap.add_argument(
        "--merge",
        action="store_true",
        help="合并到 --out，key 用 issuer::client_id::user_id",
    )
    ap.add_argument("--delay", type=int, default=0, help="每个间隔秒数")
    ap.add_argument("--email", default="", help="写入 entry.email（可选）")
    ap.add_argument(
        "--cpa-auth-dir",
        default=None,
        help="额外写出 CLIProxyAPI 扁平格式 xai-<email>.json 到该目录（CPA 热加载）",
    )
    ap.add_argument(
        "--cpa-remote-url",
        default=None,
        help="远程 CPA 地址，如 http://你的CPA地址:8317；配合 --cpa-management-key 通过 Management API 上传",
    )
    ap.add_argument(
        "--cpa-management-key",
        default=None,
        help="远程 CPA 管理密钥（remote-management.secret-key 明文）",
    )
    ap.add_argument("--proxy", default="", help="授权码流程走代理，如 http://127.0.0.1:7890")
    args = ap.parse_args()

    cookies = load_sso_list(args.sso, args.sso_cookie)
    if not cookies:
        ap.error("需要 --sso 或 --sso-cookie")

    if args.cpa_remote_url and not args.cpa_management_key:
        ap.error("使用 --cpa-remote-url 时必须同时提供 --cpa-management-key")
    if args.cpa_management_key and not args.cpa_remote_url:
        ap.error("使用 --cpa-management-key 时必须同时提供 --cpa-remote-url")

    if len(cookies) > 1 and not args.out_dir and not args.merge:
        # 默认批量写目录
        args.out_dir = args.out_dir or "./auth_out"
        print(f"批量模式默认 --out-dir {args.out_dir}")

    # 只指定 CPA 目标时不再默认写官方 ~/.grok/auth.json
    if (
        args.out is None
        and args.out_dir is None
        and not args.cpa_auth_dir
        and not args.cpa_remote_url
        and len(cookies) == 1
    ):
        args.out = str(Path.home() / ".grok" / "auth.json")

    print(f"🚀 SSO → auth.json: {len(cookies)} 个, delay={args.delay}s")
    ok = 0
    fail = 0

    for i, sso in enumerate(cookies, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(cookies)}] ...\n{'=' * 60}")
        try:
            token = sso_to_token(sso, proxy=args.proxy)
            if not token:
                fail += 1
                print(f"  ❌ [{i}] 失败")
                continue
            key, entry = token_to_auth_entry(token, email=args.email)
            uid = entry.get("user_id") or secrets.token_hex(4)

            if args.out_dir:
                p = Path(args.out_dir) / f"{uid}.json"
                write_auth_json(p, key, entry)
                print(f"  💾 {p}")
            if args.out:
                if args.merge or len(cookies) > 1:
                    merge_auth_json(Path(args.out), key, entry, unique=True)
                    print(f"  💾 merge → {args.out}")
                else:
                    write_auth_json(Path(args.out), key, entry)
                    print(f"  💾 {args.out}")

            if args.cpa_auth_dir or args.cpa_remote_url:
                record = token_to_cpa_record(token, email=args.email, sso=sso)
                if args.cpa_auth_dir:
                    cp = write_cpa_auth(Path(args.cpa_auth_dir), record)
                    print(f"  💾 CPA 本地 → {cp}")
                if args.cpa_remote_url:
                    name = upload_cpa_auth_remote(
                        args.cpa_remote_url,
                        args.cpa_management_key,
                        record,
                    )
                    print(f"  💾 CPA 远程 → {args.cpa_remote_url.rstrip('/')}/.../{name}")

            ok += 1
            print(f"  ✅ [{i}] 完成 user_id={uid[:12]}...")
        except Exception as e:
            fail += 1
            print(f"  ❌ [{i}] 异常: {e}")

        if args.delay > 0 and i < len(cookies):
            time.sleep(args.delay)

    print(f"\n{'=' * 60}\n📊 完成: {ok}/{len(cookies)} 成功, {fail} 失败")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
