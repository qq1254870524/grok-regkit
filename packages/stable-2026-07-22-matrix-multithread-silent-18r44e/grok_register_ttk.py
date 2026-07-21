# 18r44d: SOCKS5 live precheck BEFORE Chromium — TCP+HTTP via proxy; bad proxy cooldown; bind_worker/start_browser only use LIVE nodes
# 18r44c: process-wide session_id claim — reject same SSO session_id across workers/emails before disk/G2A/Sub2; restart browser after each browser success
# 18r44a: browser SSO isolation — reject stale sso cookie across same-worker multi-account; clear xAI session cookies on open_signup; Windows per-launch user-data
# 18r43n: force_stop sets cancel + non-block web stop
# 18r43m: attempt-based JobCoordinator claim_mode
# 18r43i: wait_post re-ensure drain workers every 10s
# 18r43h: post_success task_done guard + auto-replace dead drain workers
# 18r43a: multi post-success workers (default 6) drain awaiting_pool under workers=20
# 18r43d: wait_post_success_queue scales timeout with awaiting_pool depth (not hard 90s)
# 18r42d: G2A 入池拒绝 mail_token/wrapper；_normalize_sso_token 去前导 -
# 18r41: browser MT early_no_new/code-fail last-try -> pending_sso (not hard fail)
# 18r35k: CreateEmail min gap 4.0s for MT rate-limit
# 18r35d: tos-gate escape in open_signup + keep 18r35c CreateEmail gate
# 18r35c: CreateEmail gate + MT/serial catch rate-limit on fill_email
#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 18r35e: fix stale page in proxy-error detect + Chromium interstitial markers + early abort click_email
"""
Grok 注册机 - TTK GUI 版本
整合 DrissionPage_example.py, openai_register.py, batch_open_nsfw.py

Changelog:
- 2026-07-22r44d: 启动浏览器前强制 SOCKS5 预检（TCP 连通 + 经代理 HTTP 探测 accounts.x.ai/Cloudflare）；死代理冷却轮换；worker bind / mark_proxy_bad 同步 thread-local；避免首次打开 Chromium interstitial。
- 2026-07-22r44c: 进程级 session_id 认领：同 session_id 第二邮箱禁止写盘/入池（防 G2A 少号）；browser 每号成功后 clear cookie + restart_browser 硬隔离。
- 2026-07-22r44a: 修复同 worker 连续注册串 SSO：wait_for_sso 拒绝开等前已存在的 sso cookie；open_signup 清 xAI session cookie；Windows 每实例独立 user-data，避免两号共用 session_id 导致 G2A 少入池。
- 2026-07-21r43h: post-success worker 永不因单任务异常退出；task_done 防双调用；ensure 替换死线程，避免 awaiting_pool 卡住。
- 2026-07-20r35d: open_signup 识别 grok.com/tos-gate，强制跳回 accounts.x.ai/sign-up 或换代理；避免成功后卡 tos-gate 找不到邮箱注册按钮。
- 2026-07-20r35b: browser CreateEmail 验证码过多 detect+switch; pool in_use preserve (see outlook/aol).

- 2026-07-19r31-g2a-keyfix: 修复 grok2api_remote_app_key 错误导致远端入池 401 静默失败；后处理/远端入池前热重载 config.json；401/403 明确报错且不重试、不误走全量覆盖。
- 2026-07-19r30-lossfix: 后处理 Sub2 失败重试；任务结束 wait 加长 + 自动对账补齐 G2A/CPA/hybrid 缺号；减少 Sub2 比 G2A 少号。
- 2026-07-19r29k: 后处理顺序改为 NSFW→G2A→CPA→Sub2API；Sub2API 优先用刚 mint 的 CPA OAuth JSON 直导入，
  失败再 SSO→OAuth；失败写入 sub2api_import_pending.jsonl 便于回填；日志打印三池计数对照。
- 2026-07-19r29j: wait_for_sso 若仍停在注册表单（完成注册可见），自动再点「完成注册/Create account」提交，避免仅日志 hold 不推进；成功仍即时 SSO 入池。
- 2026-07-19r29i: profile 提交 CF token=0 卡住时：加强 Turnstile 点击/reset、多次复用；代理下连续失败可换 IP 后继续等 widget（不改注册→即时SSO主路径）。
- 2026-07-19r29h: browser/SOCKS5 邮箱输入框长时间 not-ready 时硬刷新注册页+重点邮箱入口；超时默认 75s；代理下二次失败可换 IP 再开页（不改主路径）。
- 2026-07-19r29f: burn 成功即 +pending_sso_count；本轮已 burn 后空失败/页未就绪不记硬 fail。
- 2026-07-19r29e: browser 路径 pending_sso:* 异常计入 pending_sso 而非 fail，任务结束日志带 pending_sso 计数。
- 2026-07-19r29b: browser 路径 early_no_new_mail/验证码超时与 hybrid 对齐：burn_mailbox_to_pending 删池+写 pending_sso，统计 pending 而非硬 fail；保留成功→即时SSO→入池主路径。
- 2026-07-19r28f: get_oai_code domain/token-first routing (Outlook not misrouted to AOL when UI source=AOL);
  fix CreateEmail-sent then "AOL missing password for @outlook.com" code fetch fail.
- 2026-07-18a: Sub2API create-success is import success; verify fail warns only unless require_verify_success.
- 2026-07-17g: Sub2API import now uses the current sso_tokens array contract and
  performs a direct per-account usability test before reporting the pool entry usable.
- 2026-07-17f: 修复 AOL 账号池 source_file 构造参数遗漏；修复停止时浏览器已关闭但
  open_signup_page 仍调用 new_tab 的竞态；新增 Sub2API Grok SSO→OAuth 后台入池，
  默认启用且失败不影响注册成功结果。
- 2026-07-17e: 接入 AOL 邮箱 provider（IMAP 协议登录，账号----密码/应用专用密码；
  配置 aol_accounts / aol_accounts_file；Web/GUI 可选 aol）。
- 2026-07-17d: 接入微软 Outlook/Hotmail 邮箱 provider（password+TOTP 或 refresh_token），
  Graph Mail.Read 收验证码；配置 outlook_accounts / outlook_accounts_file / outlook_token_cache；
  Web/桌面 GUI 可选 outlook；依赖 pyotp。
- 2026-07-17c: SOCKS5 代理池改为通用 proxy_mode=socks5_list（注册/HTTP/YYDS/浏览器共用），
  socks5_proxies.txt；失败轮询；Chromium 本地 SOCKS5 认证桥；需 PySocks。
- 2026-07-17b: 原 email_proxy_* 专用池已并入通用代理池。
- 2026-07-17: 接入公共临时邮箱 provider（tempmail_io / linshiyouxiang / boomlify / tempmail_org） + mailtm / tempmail_lol / tempmail_plus，
  与 cloudflare/duckmail/yyds 共用 email_provider 单选开关；建箱与收验证码走 temp_email_public_providers。
"""
# update: 2026-07-17 detailed email logs + clear log fix


import threading
import datetime
import time
import os
import sys
import gc
import queue
import secrets
import struct
import random
import re
import string
import json
import base64
import select
import socket
import socketserver
import ssl
import urllib.parse
from zoneinfo import ZoneInfo

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

# 运行日志统一北京时间（与服务器 UTC 无关）
_BJ_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing(fmt: str = "%H:%M:%S") -> str:
    return datetime.datetime.now(_BJ_TZ).strftime(fmt)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    HAS_TK = True
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    scrolledtext = None  # type: ignore
    HAS_TK = False

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage.errors import PageDisconnectedError
from curl_cffi import requests

try:
    import temp_email_public_providers as public_email
except Exception:
    public_email = None  # type: ignore

try:
    import outlook_mail
except Exception:
    outlook_mail = None  # type: ignore
try:
    import aol_mail
except Exception:
    aol_mail = None  # type: ignore


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
MEMORY_CLEANUP_INTERVAL = 5

UI_BG = "#242424"
UI_PANEL_BG = "#2b2b2b"
UI_FG = "#f2f2f2"
UI_MUTED_FG = "#b8b8b8"
UI_ENTRY_BG = "#333333"
UI_BUTTON_BG = "#3a3a3a"
UI_ACTIVE_BG = "#4a6078"

DEFAULT_CONFIG = {
    "duckmail_api_key": "",
    "cloudflare_api_base": "",
    "cloudflare_api_key": "",
    "cloudflare_auth_mode": "none",
    "cloudflare_path_domains": "/api/domains",
    "cloudflare_path_accounts": "/api/new_address",
    "cloudflare_path_token": "/api/token",
    "cloudflare_path_messages": "/api/mails",
    "proxy": "",
    # proxy_mode: direct | custom | whitelist | cliproxy_white | airport | socks5_list
    "proxy_mode": "airport",
    # 机场(Mihomo)本地 HTTP 入口：订阅在 mihomo 的 REGISTER-RESIDENTIAL 组
    "proxy_airport_url": "http://127.0.0.1:7893",
    # Cliproxy 白名单 API：返回 ip:port 文本
    # 例: https://api.cliproxy.io/white/api?region=US&num=1&time=10&format=n&type=txt
    "proxy_api_url": "https://api.cliproxy.io/white/api",
    "proxy_api_num": 5,
    "proxy_api_format": "n",
    "proxy_api_type": "txt",
    # IP 质量检测
    # 1) 先查「入口 IP」(Cliproxy 返回的 host) —— 不走代理，省家宽
    # 2) 可选再经代理查出口 IP（IPPure）
    "proxy_quality_api": "https://my.ippure.com/v1/info",
    "proxy_host_lookup_api": "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,org,as,hosting,proxy,mobile,query,isp",
    "proxy_quality_check": True,
    # Cliproxy white API returns shared DC gateway host:port; real residential is EXIT via proxy.
    # Entry host check is informational only by default (do not hard-reject Zenlayer gateways).
    "proxy_check_entry_host": False,
    "proxy_check_exit_ippure": True,
    "proxy_max_fraud_score": 40,
    "proxy_require_residential": True,
    "proxy_require_country_match": True,
    "proxy_reject_datacenter_org": True,
    "proxy_reject_hosting_flag": True,
    "proxy_quality_max_tries": 8,
    # whitelist / 代理组（用户名带国家，旧模式）
    "proxy_host": "",
    "proxy_port": "",
    "proxy_user": "",
    "proxy_pass": "",
    # 国家/地区：Cliproxy 用 region，建议 US
    "proxy_country": "US",
    # 用户名拼装分隔符，如 - 或 _
    "proxy_delimiter": "-",
    # 轮转/粘性时长（分钟）：Cliproxy 对应 time 参数
    "proxy_duration": "10",
    # 模板变量: {user} {pass} {host} {port} {country} {delimiter} {session} {duration}
    "proxy_user_template": "{user}{delimiter}region{delimiter}{country}",
    "proxy_session": "",
    # ===== General SOCKS5/proxy list pool (proxy_mode=socks5_list) =====
    # host:port:user:pass | socks5://user:pass@host:port | user:pass@host:port
    "proxy_list_file": "socks5_proxies.txt",
    "proxy_list": "",
    "proxy_scheme": "socks5h",
    "proxy_rotate": True,
    "proxy_no_direct_fallback": True,
    "enable_nsfw": True,
    # True=NSFW 后台执行（功能仍做）；False=拿 sso 后立刻同步开 NSFW
    "nsfw_async": True,
    "register_count": 1,
    # 18r30 multithread: web-configurable worker count (1 = serial / same as 18r29)
    "workers": 1,
    "thread_count": 1,
    # mail poll: ALL folders, only newest N messages per folder
    "mail_top_per_folder": 5,
    # job-start preflight login for outlook/aol pools (drop bad mailboxes)
    "email_preflight_on_start": True,
    "email_preflight_limit": 12,
    # continuous background pre-login (warm queue ahead of workers)
    "email_preflight_continuous": True,
    "email_preflight_warm_ahead": 0,  # 0=auto max(6,min(40,workers*4)); >0 = web UI fixed warm count
    "email_preflight_warm_ttl_sec": 600,
    "email_preflight_interval_sec": 0.8,
    # register_mode: browser (full UI) | hybrid (protocol + short browser tokens)
    "register_mode": "browser",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "grok2api_auto_add_local": True,
    "grok2api_local_token_file": "",
    "grok2api_pool_name": "ssoBasic",
    "grok2api_auto_add_remote": False,
    "grok2api_remote_base": "",
    "grok2api_remote_app_key": "",
    # ===== Sub2API: successful Grok SSO -> OAuth account import =====
    "sub2api_auto_add": True,
    "sub2api_base_url": "http://127.0.0.1:8080",
    "sub2api_admin_email": "",
    "sub2api_admin_password": "",
    "sub2api_group_ids": [3],
    "sub2api_concurrency": 1,
    "sub2api_priority": 1,
    "sub2api_timeout_sec": 60,
    "sub2api_verify_after_add": True,
    "sub2api_require_verify_success": False,
    "sub2api_verify_attempts": 2,
    "sub2api_verify_timeout_sec": 105,
    "sub2api_verify_retry_delay_sec": 3,
    # ===== CPA / free Grok 4.5 (OIDC via Grok Build, NOT SSO) =====
    # SSO → web model pool; OIDC → CLIProxyAPI → cli-chat-proxy → grok-4.5
    "cpa_export_enabled": True,
    # alias from grokRegister-cpa; False disables export even if cpa_export_enabled True
    "cpa_auto_add": True,
    "cpa_auth_dir": "./cpa_auths",
    "cpa_copy_to_hotload": True,
    "cpa_hotload_dir": "",  # set to CPA auth-dir on server, e.g. /opt/cliproxyapi/auths
    # Remote CLIProxyAPI Management API (plaintext key; bcrypt hash in CPA yaml will NOT work)
    "cpa_remote_url": "http://127.0.0.1:8317",
    "cpa_management_key": "",
    "cpa_remote_upload": False,
    "cpa_remote_timeout_sec": 30,
    # Prefer Authorization Code + PKCE (referrer=grok-build); fallback device/protocol
    "cpa_prefer_authcode": True,
    "cpa_base_url": "https://cli-chat-proxy.grok.com/v1",
    "cpa_proxy": "",  # empty = fall back to runtime proxy / airport
    # Protocol mint needs no browser; fallback browser MUST be headed (Xvfb) on servers.
    "cpa_headless": False,
    "cpa_force_standalone": True,
    "cpa_mint_timeout_sec": 300,
    "cpa_mint_required": False,
    "cpa_probe_after_write": True,
    "cpa_probe_required": False,
    "cpa_probe_chat": False,
    "cpa_prefer_protocol": True,
    "cpa_protocol_only": False,
    "cpa_protocol_poll_timeout_sec": 90,
    "cpa_mint_cookie_inject": True,
    "cpa_gui_close_mint_browser": True,
    "cpa_mint_browser_reuse": False,
    "cpa_mint_browser_recycle_every": 15,
    # Gap between CPA mints to avoid auth.x.ai device-code 429/slow_down
    "cpa_mint_gap_sec": 25,
    # 注册主路径提速：sso 落盘后，g2a 入池 + CPA mint 进后台队列（功能都保留）
    "post_success_async": True,
    # 后台入池：浏览器松了再多试几次，比注册高峰硬等 502 更划算
    "grok2api_bg_max_http_tries": 6,
    "grok2api_bg_http_timeout_sec": 15,
    # ===== Email providers =====
    "email_provider": "duckmail",
    "defaultDomains": "",
    "yyds_api_key": "",
    "yyds_jwt": "",
    # Outlook / Microsoft personal mailbox (password+TOTP or refresh_token)
    "outlook_accounts": "",
    "outlook_accounts_file": "outlook_accounts.txt",
    "outlook_client_id": "9e5f94bc-e8a4-4e73-b8be-63364c29d753",
    "outlook_token_cache": "outlook_token_cache.json",
    # AOL mailbox (IMAP email----password/app-password)
    "aol_accounts": "",
    "aol_accounts_file": "aol_accounts.txt",
    # 18r42 silent multi-thread: keep headed Chrome for CF/Turnstile,
    # but do not steal focus / flood desktop. Off-screen + minimize.
    "browser_silent": True,
    "browser_start_minimized": True,
    "browser_window_x": -32000,
    "browser_window_y": 0,
    "browser_window_width": 900,
    "browser_window_height": 640,
}

config = DEFAULT_CONFIG.copy()
_cf_domain_index = 0
_cpa_export_lock = threading.Lock()
_cpa_last_mint_ts = 0.0  # wall clock; serialize + gap between mints
_post_success_q = queue.Queue()
_post_success_worker_lock = threading.Lock()
_post_success_worker_started = False
_post_success_worker_count = 0
_post_success_threads = []  # 18r43h live Thread refs for dead-worker replace
_post_success_pending = 0
_post_success_pending_lock = threading.Lock()
# 18r43a: multi post-success workers drain awaiting_pool under high concurrency
_POST_SUCCESS_DEFAULT_WORKERS = 6


def get_post_success_queue_depth():
    """Return (pending_count, unfinished_tasks) for UI awaiting_pool metric."""
    with _post_success_pending_lock:
        pending = int(_post_success_pending or 0)
    unfinished = int(getattr(_post_success_q, "unfinished_tasks", 0) or 0)
    return pending, unfinished


def get_awaiting_pool_count():
    """Accounts registered OK but still waiting to enter G2A/Sub2/CPA pools."""
    pending, unfinished = get_post_success_queue_depth()
    return max(pending, unfinished)



class RegistrationCancelled(Exception):
    pass


class AccountRetryNeeded(Exception):
    pass


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            config = {**DEFAULT_CONFIG, **loaded}
        except Exception:
            config = DEFAULT_CONFIG.copy()
    return config


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存配置失败: {e}")


def ensure_stable_python_runtime():
    if sys.version_info < (3, 14) or os.environ.get("DPE_REEXEC_DONE") == "1":
        return

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Programs", "Python", "Python312", "python.exe"),
        os.path.join(local_app_data, "Programs", "Python", "Python313", "python.exe"),
    ]

    current_python = os.path.normcase(os.path.abspath(sys.executable))
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        if os.path.normcase(os.path.abspath(candidate)) == current_python:
            return

        print(
            f"[*] 检测到 Python {sys.version.split()[0]}，自动切换到更稳定的解释器: {candidate}"
        )
        env = os.environ.copy()
        env["DPE_REEXEC_DONE"] = "1"
        os.execve(candidate, [candidate, os.path.abspath(__file__), *sys.argv[1:]], env)


def warn_runtime_compatibility():
    if sys.version_info >= (3, 14):
        print(
            "[提示] 当前 Python 为 3.14+；若出现 Mail.tm TLS 异常，建议改用 Python 3.12 或 3.13。"
        )


ensure_stable_python_runtime()
warn_runtime_compatibility()

load_config()

EXTENSION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "turnstilePatch")
)


DUCKMAIL_API_BASE = "https://api.duckmail.sbs"


def _proxy_quote(part: str) -> str:
    return urllib.parse.quote(str(part or ""), safe="")


def _cliproxy_build_url(c, region, num, duration, fmt, typ) -> str:
    base = str(c.get("proxy_api_url", "") or "https://api.cliproxy.io/white/api").strip()
    if not base:
        raise ValueError("未配置 proxy_api_url")
    if "?" in base:
        return (
            base.replace("{region}", region)
            .replace("{country}", region)
            .replace("{num}", str(num))
            .replace("{time}", duration)
            .replace("{duration}", duration)
            .replace("{format}", fmt)
            .replace("{type}", typ)
        )
    qs = urllib.parse.urlencode(
        {
            "region": region,
            "num": str(num),
            "time": duration,
            "format": fmt,
            "type": typ,
        }
    )
    return f"{base.rstrip('/')}?{qs}"


def _parse_proxy_hostports(text: str) -> list:
    """Parse ip:port lines from Cliproxy txt/json response."""
    text = (text or "").strip()
    if not text:
        return []
    lines = []
    # try full JSON first
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                raw_list = data.get("data") or data.get("list") or data.get("proxies") or []
                if isinstance(raw_list, str):
                    text = raw_list
                elif isinstance(raw_list, list):
                    for item in raw_list:
                        if isinstance(item, str):
                            lines.append(item)
                        elif isinstance(item, dict):
                            lines.append(
                                str(item.get("proxy") or item.get("ip") or item.get("addr") or "")
                            )
                else:
                    one = str(data.get("proxy") or data.get("ip") or "")
                    if one:
                        lines.append(one)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, dict):
                        lines.append(str(item.get("proxy") or item.get("ip") or ""))
        except Exception:
            pass
    if not lines:
        lines = text.replace("\r\n", "\n").replace(",", "\n").split("\n")

    out = []
    seen = set()
    for raw in lines:
        cand = str(raw or "").strip()
        if not cand or cand.startswith("#"):
            continue
        cand = cand.replace("http://", "").replace("https://", "").strip()
        if ":" not in cand:
            continue
        host, port = cand.rsplit(":", 1)
        host = host.strip().strip("[]")
        port = port.strip()
        if not host or not port.isdigit():
            continue
        item = f"{host}:{port}"
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


_DATACENTER_ORG_KEYWORDS = (
    "amazon",
    "aws",
    "google cloud",
    "google llc",
    "microsoft",
    "azure",
    "digitalocean",
    "linode",
    "akamai",
    "cloudflare",
    "ovh",
    "hetzner",
    "vultr",
    "contabo",
    "choopa",
    "leaseweb",
    "colocrossing",
    "psychz",
    "quadranet",
    "m247",
    "datacamp",
    "zenlayer",
    "server",
    "hosting",
    "vps",
    "dedicated",
    "data center",
    "datacenter",
    "colocation",
    "colo ",
)


def _normalize_quality_info(info: dict) -> dict:
    """Normalize IPPure / ip-api style payloads into one shape."""
    info = dict(info or {})
    # ip-api.com fields -> common
    if not info.get("ip") and info.get("query"):
        info["ip"] = info.get("query")
    if not info.get("countryCode") and info.get("countryCode") is None:
        # already ok
        pass
    if not info.get("asOrganization"):
        info["asOrganization"] = (
            info.get("asOrganization")
            or info.get("org")
            or info.get("isp")
            or info.get("as")
            or ""
        )
    if "isResidential" not in info or info.get("isResidential") is None:
        # ip-api: hosting/proxy/mobile
        if "hosting" in info or "mobile" in info:
            hosting = bool(info.get("hosting"))
            mobile = bool(info.get("mobile"))
            if hosting:
                info["isResidential"] = False
            elif mobile:
                info["isResidential"] = True
    if info.get("hosting") is True and info.get("isResidential") is None:
        info["isResidential"] = False
    return info


def lookup_entry_ip_quality(ip: str, cfg=None, timeout: int = 12) -> dict:
    """Lookup Cliproxy *entry host* IP quality WITHOUT going through proxy.

    Saves residential bandwidth. Uses ip-api.com free endpoint by default.
    """
    c = cfg if isinstance(cfg, dict) else config
    ip = str(ip or "").strip()
    if not ip:
        raise ValueError("empty ip")
    template = str(
        c.get("proxy_host_lookup_api")
        or "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,org,as,hosting,proxy,mobile,query,isp"
    ).strip()
    url = template.replace("{ip}", urllib.parse.quote(ip))
    # direct, no proxy
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "grok-register/1.0"})
    if resp.status_code >= 400:
        raise RuntimeError(f"入口IP查询 HTTP {resp.status_code}: {(resp.text or '')[:160]}")
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"入口IP查询非JSON: {(resp.text or '')[:160]}")
    if not isinstance(data, dict):
        raise RuntimeError("入口IP查询格式错误")
    if str(data.get("status", "")).lower() == "fail":
        raise RuntimeError(f"入口IP查询失败: {data.get('message') or data}")
    data = _normalize_quality_info(data)
    data["ip"] = data.get("ip") or ip
    data["_source"] = "entry-host"
    return data


def probe_proxy_with_ippure(proxy_url: str, quality_api: str = "", timeout: int = 15) -> dict:
    """Call IPPure *through proxy* to get exit IP quality info.

    Docs: https://my.ippure.com/v1/info  (returns exit IP of the proxy path)
    Note: free responses often omit fraudScore/isResidential.
    """
    api = (quality_api or "https://my.ippure.com/v1/info").strip()
    proxies = {"http": proxy_url, "https": proxy_url}
    resp = requests.get(
        api,
        proxies=proxies,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"IPPure HTTP {resp.status_code}: {(resp.text or '')[:160]}")
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"IPPure 返回非 JSON: {(resp.text or '')[:160]}")
    if not isinstance(data, dict):
        raise RuntimeError(f"IPPure 返回格式错误: {type(data)}")
    data = _normalize_quality_info(data)
    data["_source"] = "exit-ippure"
    return data


def evaluate_proxy_quality(info: dict, cfg=None, *, stage: str = "exit") -> tuple:
    """Return (ok: bool, reason: str, summary: str).

    stage: entry|exit — entry is Cliproxy host IP; exit is path after proxy.
    """
    c = cfg if isinstance(cfg, dict) else config
    info = _normalize_quality_info(info or {})
    fraud = info.get("fraudScore")
    try:
        fraud_i = int(fraud) if fraud is not None and str(fraud) != "" else None
    except Exception:
        fraud_i = None
    is_res = info.get("isResidential")
    is_broadcast = bool(info.get("isBroadcast"))
    hosting_flag = info.get("hosting")
    country_code = str(info.get("countryCode") or "").strip().upper()
    ip = str(info.get("ip") or "").strip()
    org = str(info.get("asOrganization") or info.get("org") or info.get("isp") or "").strip()
    org_l = org.lower()
    expected = str(c.get("proxy_country", "US") or "US").strip().upper()
    if expected == "RAND":
        expected = ""

    max_fraud = int(c.get("proxy_max_fraud_score", 40) or 40)
    require_res = bool(c.get("proxy_require_residential", True))
    require_country = bool(c.get("proxy_require_country_match", True))
    reject_dc_org = bool(c.get("proxy_reject_datacenter_org", True))
    reject_hosting = bool(c.get("proxy_reject_hosting_flag", True))

    summary = (
        f"[{stage}] ip={ip or '?'} country={country_code or '?'} "
        f"fraud={fraud_i if fraud_i is not None else '?'} "
        f"residential={is_res} hosting={hosting_flag} org={org or '?'}"
    )

    # High risk score (IPPure full plan / web)
    if fraud_i is not None:
        if fraud_i >= 70:
            return False, f"极度风险 fraudScore={fraud_i}", summary
        if fraud_i > max_fraud:
            return False, f"风险分过高 fraudScore={fraud_i}>{max_fraud}", summary

    if is_broadcast:
        return False, "广播/异常 IP (isBroadcast)", summary

    # Explicit datacenter flags
    if reject_hosting and hosting_flag is True:
        return False, "机房IP (hosting=true)", summary
    if require_res and is_res is False:
        return False, "非住宅 IP (isResidential=false)", summary

    if require_country and expected and country_code and country_code != expected:
        return False, f"国家不匹配 want={expected} got={country_code}", summary

    # ASN / org heuristics (Zenlayer etc.)
    if reject_dc_org and org_l and any(k in org_l for k in _DATACENTER_ORG_KEYWORDS):
        return False, f"疑似机房/云厂商 ASN: {org}", summary

    # Entry host: if no residential/fraud fields, do NOT soft-pass when org empty either
    if stage == "entry":
        if require_res and is_res is None and fraud_i is None and hosting_flag is None:
            # only org-based pass; if org missing, reject to be safe
            if not org_l:
                return False, "入口IP信息不足，无法确认非机房", summary
        return True, "ok", summary

    # Exit path via IPPure free API often lacks fraud/residential
    if require_res and is_res is None and fraud_i is None:
        # require org not datacenter already checked; still warn-level ok only if org present
        if not org_l:
            return False, "出口IP信息不足(无fraud/residential/org)", summary
        return True, "ok(出口字段不完整，已按国家+ASN判断)", summary
    return True, "ok", summary


# Cache entry-host quality within one process run: host -> (ok, reason, summary)
_entry_host_quality_cache = {}


def quality_check_cliproxy_hostport(hostport: str, cfg=None, log_callback=None) -> tuple:
    """Full quality gate for one Cliproxy host:port.

    Cliproxy white API returns a shared DC gateway (e.g. 107.151.x.x:port). The real
    residential IP is the *exit* seen when traffic goes through that port — different
    ports on the same gateway often map to different residential exits.

    1) Optional entry host note (informational; NOT a hard reject by default)
    2) IPPure via proxy for exit IP (authoritative for residential / country / fraud)
    Returns (ok, proxy_url, detail)
    """
    global _entry_host_quality_cache
    c = cfg if isinstance(cfg, dict) else config
    hostport = str(hostport or "").strip()
    host, port = hostport.rsplit(":", 1)
    proxy_url = f"http://{hostport}"
    # Default OFF: entry is almost always Zenlayer/VpsQuan gateway for white API.
    check_entry = bool(c.get("proxy_check_entry_host", False))
    # Hard reject on entry only if user explicitly opts in (legacy / non-Cliproxy).
    entry_hard = bool(c.get("proxy_entry_hard_reject", False))
    check_exit = bool(c.get("proxy_check_exit_ippure", True))
    quality_api = str(c.get("proxy_quality_api") or "https://my.ippure.com/v1/info").strip()

    if check_entry:
        cached = _entry_host_quality_cache.get(host)
        if cached is not None:
            ok, reason, summary = cached
            if log_callback:
                mark = "[+]" if ok else ("[-]" if entry_hard else "[*]")
                log_callback(
                    f"{mark} 入口(缓存) host={host} | {reason}"
                    + ("" if ok or entry_hard else "（网关可忽略，以出口为准）")
                )
            if not ok and entry_hard:
                return False, proxy_url, reason
        else:
            try:
                entry = lookup_entry_ip_quality(host, c)
                ok, reason, summary = evaluate_proxy_quality(entry, c, stage="entry")
                _entry_host_quality_cache[host] = (ok, reason, summary)
                if log_callback:
                    if ok:
                        log_callback(f"[+] 入口检测 {summary} | {reason}")
                    elif entry_hard:
                        log_callback(f"[-] 入口检测 {summary} | {reason}")
                    else:
                        log_callback(
                            f"[*] 入口网关 {summary} | {reason} "
                            f"（Cliproxy 共享入口可忽略，以出口家宽为准）"
                        )
                if not ok and entry_hard:
                    return False, proxy_url, reason
            except Exception as exc:
                if log_callback:
                    log_callback(f"[*] 入口检测跳过 {host}: {exc}")
                _entry_host_quality_cache[host] = (True, f"入口查询失败已忽略: {exc}", "")

    exit_info = None
    if check_exit:
        try:
            exit_info = probe_proxy_with_ippure(proxy_url, quality_api=quality_api, timeout=15)
            ok, reason, summary = evaluate_proxy_quality(exit_info, c, stage="exit")
            if log_callback:
                mark = "[+]" if ok else "[-]"
                log_callback(f"{mark} 出口检测 {summary} | {reason}")
            if not ok:
                return False, proxy_url, reason
        except Exception as exc:
            if log_callback:
                log_callback(f"[-] 出口 IPPure 检测失败 {hostport}: {exc}")
            return False, proxy_url, f"出口检测异常: {exc}"
    else:
        if log_callback:
            log_callback("[!] 出口检测已关闭，无法确认是否家宽，不建议用于注册")

    # Attach last exit meta for logging (not part of public return contract)
    detail = "ok"
    if isinstance(exit_info, dict):
        exit_ip = str(exit_info.get("ip") or "").strip()
        exit_org = str(
            exit_info.get("asOrganization")
            or exit_info.get("org")
            or exit_info.get("isp")
            or ""
        ).strip()
        res = exit_info.get("isResidential")
        fraud = exit_info.get("fraudScore")
        detail = (
            f"ok | 入口网关={host}:{port} → 出口家宽={exit_ip or '?'} "
            f"org={exit_org or '?'} residential={res} fraud={fraud if fraud is not None else '?'}"
        )
        try:
            c["_last_proxy_exit"] = {
                "gateway": hostport,
                "exit_ip": exit_ip,
                "exit_org": exit_org,
                "isResidential": res,
                "fraudScore": fraud,
                "countryCode": exit_info.get("countryCode"),
            }
        except Exception:
            pass
    return True, proxy_url, detail


def fetch_cliproxy_white_proxy(cfg=None, log_callback=None) -> str:
    """Call Cliproxy white API, quality-check via IPPure, return http://ip:port.

    Cliproxy:
      https://api.cliproxy.io/white/api?region=US&num=5&time=10&format=n&type=txt
    IPPure (through proxy):
      https://my.ippure.com/v1/info
    """
    c = cfg if isinstance(cfg, dict) else config
    region = str(c.get("proxy_country", "US") or "US").strip() or "US"
    if region.upper() == "RAND":
        region = "Rand"
    duration = str(c.get("proxy_duration", "10") or "10").strip()
    if duration.lower().startswith("t-"):
        duration = duration[2:]
    duration = "".join(ch for ch in duration if ch.isdigit()) or "10"
    fmt = str(c.get("proxy_api_format", "n") or "n").strip() or "n"
    typ = str(c.get("proxy_api_type", "txt") or "txt").strip() or "txt"
    # Quality check is ON by default; env GROK_FORCE_PROXY_QUALITY=1 hard-forces it.
    quality_on = bool(c.get("proxy_quality_check", True))
    if os.environ.get("GROK_FORCE_PROXY_QUALITY", "1").strip() in ("1", "true", "TRUE", "yes", "YES"):
        quality_on = True
    max_tries = int(c.get("proxy_quality_max_tries", 8) or 8)
    batch = int(c.get("proxy_api_num", 5) or 5)
    if quality_on:
        batch = max(batch, 3)
    check_entry = bool(c.get("proxy_check_entry_host", False))
    check_exit = bool(c.get("proxy_check_exit_ippure", True))
    if log_callback:
        log_callback(
            f"[*] 代理质量检测: {'开启' if quality_on else '关闭'} "
            f"(入口备注={'开' if check_entry else '关'} / "
            f"出口IPPure={'开' if check_exit else '关'}；"
            f"Cliproxy 以出口家宽为准，同网关不同端口=不同出口)"
        )

    tested = 0
    last_err = ""
    # Track rejected host:port only — same gateway host can have good/bad exits per port.
    rejected_ports = set()
    for attempt in range(1, max_tries + 1):
        url = _cliproxy_build_url(c, region, batch, duration, fmt, typ)
        if log_callback:
            log_callback(
                f"[*] 请求 Cliproxy 白名单 IP: region={region} time={duration}m "
                f"num={batch} (第{attempt}/{max_tries}批)"
            )
        try:
            resp = requests.get(url, timeout=20)
            text = (resp.text or "").strip()
            if resp.status_code >= 400:
                raise RuntimeError(f"Cliproxy API HTTP {resp.status_code}: {text[:200]}")
            if not text:
                raise RuntimeError("Cliproxy API 返回为空")
        except Exception as exc:
            last_err = str(exc)
            if log_callback:
                log_callback(f"[!] Cliproxy 提取失败: {exc}")
            time.sleep(1)
            continue

        hostports = _parse_proxy_hostports(text)
        if not hostports:
            last_err = f"无法解析 IP: {text[:160]}"
            if log_callback:
                log_callback(f"[!] {last_err}")
            continue

        unique_hosts = sorted({hp.rsplit(":", 1)[0] for hp in hostports})
        fresh = [hp for hp in hostports if hp not in rejected_ports]
        if log_callback:
            log_callback(
                f"[*] 本批 {len(hostports)} 条，网关入口 {len(unique_hosts)} 个: "
                f"{', '.join(unique_hosts[:8])}{'...' if len(unique_hosts) > 8 else ''}；"
                f"待测端口 {len(fresh)}"
            )
            if len(unique_hosts) == 1:
                log_callback(
                    f"[*] 提示: 同一入口 {unique_hosts[0]} 的不同端口通常对应不同出口家宽，"
                    "将逐端口做出口 IPPure 检测"
                )
        if not fresh:
            if log_callback:
                log_callback("[*] 本批端口均已测过不合格，继续下一批")
            continue

        for hp in fresh:
            tested += 1
            if not quality_on:
                proxy_url = f"http://{hp}"
                if log_callback:
                    log_callback(
                        f"[!] 警告: 质量检测已关闭，直接使用 {hp}（未验证出口家宽）"
                    )
                return proxy_url
            ok, proxy_url, reason = quality_check_cliproxy_hostport(
                hp, c, log_callback=log_callback
            )
            if ok:
                if log_callback:
                    # reason already embeds gateway→exit when quality ran
                    if reason and reason != "ok" and "出口" in str(reason):
                        log_callback(f"[+] 选用合格代理: {hp}")
                        log_callback(f"[+] {reason}")
                        log_callback(
                            "[*] 说明: 日志里的 107.x/128.x 是 Cliproxy「入口网关」，"
                            "网站/Cloudflare 看到的是上面的「出口家宽 IP」，不是机房 IP。"
                        )
                    else:
                        log_callback(f"[+] 选用合格代理: {hp}（出口检测通过）")
                return proxy_url
            last_err = reason
            rejected_ports.add(hp)
            continue

    raise RuntimeError(
        f"未找到合格代理（已检测约 {tested} 个端口出口）。最后原因: {last_err or '无'}。\n"
        f"Cliproxy white 返回的是共享网关:端口；真实质量看「经代理出口」。\n"
        f"可调高 region=US、proxy_quality_max_tries，或放宽 fraud / 国家匹配。"
    )


def build_whitelist_proxy_url(cfg=None) -> str:
    """Build whitelist proxy URL with country/region and delimiter.

    Typical vendor username: user-region-US  (delimiter="-")
    Full URL: http://user-region-US:pass@host:port
    """
    c = cfg if isinstance(cfg, dict) else config
    host = str(c.get("proxy_host", "") or "").strip()
    port = str(c.get("proxy_port", "") or "").strip()
    user = str(c.get("proxy_user", "") or "").strip()
    password = str(c.get("proxy_pass", "") or "")
    country = str(c.get("proxy_country", "US") or "US").strip().upper()
    delim = str(c.get("proxy_delimiter", "-") or "-")
    duration = str(c.get("proxy_duration", "120") or "120").strip()
    # allow "120" or "t-120"
    if duration.lower().startswith("t-"):
        duration = duration[2:]
    duration = "".join(ch for ch in duration if ch.isdigit()) or "120"
    session = str(c.get("proxy_session", "") or "").strip()
    if not session:
        session = secrets.token_hex(4)
    template = str(
        c.get("proxy_user_template", "{user}{delimiter}region{delimiter}{country}")
        or "{user}{delimiter}region{delimiter}{country}"
    ).strip()
    if not host or not port:
        return ""
    username = template.format(
        user=user,
        pass_=password,
        password=password,
        host=host,
        port=port,
        country=country,
        delimiter=delim,
        session=session,
        duration=duration,
        t=f"t-{duration}",
    )
    # If no username, allow IP-whitelist-only host:port
    if username:
        auth = f"{_proxy_quote(username)}:{_proxy_quote(password)}@"
    else:
        auth = ""
    return f"http://{auth}{host}:{port}"


def resolve_airport_proxy(cfg=None, log_callback=None) -> str:
    """Local Mihomo mixed port backed by airport subscription (hysteria2/vless)."""
    c = cfg if isinstance(cfg, dict) else config
    url = str(
        c.get("proxy_airport_url")
        or c.get("proxy")
        or "http://127.0.0.1:7893"
    ).strip()
    if not url:
        url = "http://127.0.0.1:7893"
    if log_callback:
        log_callback(
            f"[*] 代理模式: 机场(Mihomo) | {url} "
            f"（订阅节点组 REGISTER-RESIDENTIAL，不是 Cliproxy ip:port）"
        )
    return url


def resolve_runtime_proxy(cfg=None, log_callback=None, fetch_live=True) -> str:
    """Resolve effective proxy URL from mode + API / whitelist / socks5 list / custom."""
    c = cfg if isinstance(cfg, dict) else config
    mode = str(c.get("proxy_mode", "") or "").strip().lower()
    custom = str(c.get("proxy", "") or "").strip()
    if not mode:
        return custom
    if mode in ("direct", "none", "off"):
        return ""
    if mode in ("airport", "mihomo", "kunlun", "airport_mihomo"):
        return resolve_airport_proxy(c, log_callback=log_callback)
    if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
        if not fetch_live:
            return custom
        return fetch_cliproxy_white_proxy(c, log_callback=log_callback)
    if mode in ("whitelist", "group", "proxy_group"):
        return build_whitelist_proxy_url(c)
    if mode in ("socks5_list", "socks5_pool", "proxy_list", "list", "socks5"):
        if not fetch_live and custom:
            return custom
        picked = pick_proxy_from_list(c, rotate=bool(c.get("proxy_rotate", True)))
        if log_callback:
            n = len(load_proxy_list(c))
            log_callback(f"[*] 代理模式: SOCKS5通用池 | {_mask_proxy_url(picked)} | 池大小={n}")
        return picked
    return custom


def apply_resolved_proxy_to_config(log_callback=None, fetch_live=True):
    """Write resolved proxy into config['proxy'] for existing get_proxies/browser code."""
    global config
    resolved = resolve_runtime_proxy(config, log_callback=log_callback, fetch_live=fetch_live)
    config["proxy"] = resolved
    return resolved


def get_configured_proxy():
    # 18r30: per-worker proxy override (SOCKS5 sequential bind)
    try:
        ov = get_thread_proxy_override()
        if ov is not None:
            return str(ov or "").strip()
    except Exception:
        pass
    mode = str(config.get("proxy_mode", "") or "").strip().lower()
    if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
        return str(config.get("proxy", "") or "").strip()
    if mode in ("socks5_list", "socks5_pool", "proxy_list", "list", "socks5"):
        sticky = str(config.get("proxy", "") or "").strip()
        if sticky:
            return sticky
        return pick_proxy_from_list(config, rotate=False)
    if mode in ("airport", "mihomo", "kunlun", "airport_mihomo"):
        return str(
            config.get("proxy")
            or config.get("proxy_airport_url")
            or "http://127.0.0.1:7893"
        ).strip()
    if mode in ("whitelist", "group", "proxy_group"):
        return build_whitelist_proxy_url(config)
    if mode in ("direct", "none", "off"):
        return ""
    if mode:
        return str(config.get("proxy", "") or "").strip()
    return str(config.get("proxy", "") or "").strip()


def get_proxies():
    proxy = get_configured_proxy()
    if proxy:
        return {"http": proxy, "https": proxy}
    return {}


_PROXY_POOL_LOCK = threading.Lock()
_PROXY_POOL_INDEX = 0
_PROXY_POOL_CACHE = {"mtime": None, "path": None, "items": []}


def _normalize_proxy_url(raw: str, default_scheme: str = "http") -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"{default_scheme}://{text}"
    return text


def parse_proxy_endpoint_line(line: str, default_scheme: str = "socks5h") -> str:
    """Parse host:port:user:pass / URL / user:pass@host:port into proxy URL."""
    raw = str(line or "").strip()
    if not raw or raw.startswith("#"):
        return ""
    raw = raw.strip().strip(",")
    if "://" in raw:
        return raw
    if "@" in raw and raw.count(":") >= 2:
        return _normalize_proxy_url(raw, default_scheme)
    parts = raw.split(":")
    if len(parts) >= 4:
        host = parts[0].strip()
        port = parts[1].strip()
        user = parts[2].strip()
        password = ":".join(parts[3:]).strip()
        if not host or not port:
            return ""
        user_q = urllib.parse.quote(user, safe="")
        pass_q = urllib.parse.quote(password, safe="")
        auth = f"{user_q}:{pass_q}@" if (user or password) else ""
        return f"{default_scheme}://{auth}{host}:{port}"
    if len(parts) == 2:
        host, port = parts[0].strip(), parts[1].strip()
        if host and port:
            return f"{default_scheme}://{host}:{port}"
    return ""


def _proxy_list_file_path(cfg=None) -> str:
    c = cfg if isinstance(cfg, dict) else config
    name = str(
        c.get("proxy_list_file")
        or c.get("email_proxy_list_file")
        or "socks5_proxies.txt"
    ).strip() or "socks5_proxies.txt"
    if os.path.isabs(name):
        return name
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def load_proxy_list(cfg=None, force_reload=False) -> list:
    """Load general proxy pool from proxy_list + proxy_list_file."""
    global _PROXY_POOL_CACHE
    c = cfg if isinstance(cfg, dict) else config
    scheme = str(c.get("proxy_scheme") or c.get("email_proxy_scheme") or "socks5h").strip() or "socks5h"
    items = []
    inline = str(c.get("proxy_list") or c.get("email_proxy_list") or "").strip()
    if inline:
        for line in re.split(r"[\r\n;]+", inline):
            url = parse_proxy_endpoint_line(line, default_scheme=scheme)
            if url:
                items.append(url)
    path = _proxy_list_file_path(c)
    mtime = None
    try:
        if os.path.isfile(path):
            mtime = os.path.getmtime(path)
    except Exception:
        mtime = None
    with _PROXY_POOL_LOCK:
        cache_hit = (
            not force_reload
            and not inline
            and _PROXY_POOL_CACHE.get("path") == path
            and _PROXY_POOL_CACHE.get("mtime") == mtime
            and _PROXY_POOL_CACHE.get("items")
        )
        if cache_hit:
            file_items = list(_PROXY_POOL_CACHE["items"])
        else:
            file_items = []
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            url = parse_proxy_endpoint_line(line, default_scheme=scheme)
                            if url:
                                file_items.append(url)
                except Exception:
                    file_items = []
            if not inline:
                _PROXY_POOL_CACHE = {"mtime": mtime, "path": path, "items": list(file_items)}
    seen = set()
    out = []
    for url in items + file_items:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _mask_proxy_url(proxy_url: str) -> str:
    """Return proxy URL as-is (user requested full logs, no redaction)."""
    return str(proxy_url or "")

def pick_proxy_from_list(cfg=None, rotate=None) -> str:
    global _PROXY_POOL_INDEX
    c = cfg if isinstance(cfg, dict) else config
    pool = load_proxy_list(c)
    if not pool:
        return ""
    do_rotate = bool(c.get("proxy_rotate", True)) if rotate is None else bool(rotate)
    with _PROXY_POOL_LOCK:
        if not do_rotate:
            return pool[_PROXY_POOL_INDEX % len(pool)]
        idx = _PROXY_POOL_INDEX % len(pool)
        _PROXY_POOL_INDEX = idx + 1
        return pool[idx]


# ===== 18r44d: SOCKS5 live precheck + bad-proxy cooldown =====
_PROXY_BAD_LOCK = threading.Lock()
_PROXY_BAD_UNTIL = {}  # proxy_url -> unix expire
_PROXY_PRECHECK_CACHE = {}  # proxy_url -> (ok, expire_ts)
_PROXY_BAD_COOLDOWN_SEC = 300
_PROXY_PRECHECK_OK_TTL_SEC = 45
_PROXY_PRECHECK_PROBE_URLS = (
    "https://cloudflare.com/cdn-cgi/trace",
    "https://accounts.x.ai/",
    "https://www.gstatic.com/generate_204",
)


def _proxy_cooldown_sec(cfg=None) -> int:
    c = cfg if isinstance(cfg, dict) else config
    try:
        return max(30, int(c.get("proxy_bad_cooldown_sec", _PROXY_BAD_COOLDOWN_SEC) or _PROXY_BAD_COOLDOWN_SEC))
    except Exception:
        return _PROXY_BAD_COOLDOWN_SEC


def mark_proxy_cooldown(proxy_url: str = "", seconds=None, reason: str = "", log_callback=None) -> None:
    """Mark a proxy dead for a cooldown window so workers skip it."""
    url = str(proxy_url or "").strip()
    if not url:
        return
    sec = int(seconds) if seconds is not None else _proxy_cooldown_sec()
    until = time.time() + max(10, sec)
    with _PROXY_BAD_LOCK:
        _PROXY_BAD_UNTIL[url] = until
        _PROXY_PRECHECK_CACHE.pop(url, None)
    if log_callback:
        try:
            log_callback(
                f"[*] 代理冷却 {sec}s | {_mask_proxy_url(url)}"
                + (f" | reason={reason}" if reason else "")
            )
        except Exception:
            pass


def is_proxy_in_cooldown(proxy_url: str = "") -> bool:
    url = str(proxy_url or "").strip()
    if not url:
        return False
    now = time.time()
    with _PROXY_BAD_LOCK:
        until = float(_PROXY_BAD_UNTIL.get(url) or 0)
        if until <= now:
            if url in _PROXY_BAD_UNTIL:
                _PROXY_BAD_UNTIL.pop(url, None)
            return False
        return True


def _tcp_check_proxy_endpoint(proxy_url: str, timeout: float = 4.0) -> tuple:
    """Return (ok, detail) for raw TCP reachability of proxy host:port."""
    parsed = _parse_proxy_url(proxy_url)
    if not parsed or not parsed.hostname:
        return False, "invalid_proxy_url"
    host = parsed.hostname
    port = _safe_proxy_port(parsed)
    if not port:
        scheme = (parsed.scheme or "").lower()
        port = 1080 if scheme.startswith("socks") else 8080
    try:
        port = int(port)
    except Exception:
        return False, f"bad_port={port}"
    sock = None
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=max(1.0, float(timeout)))
        elapsed = time.time() - t0
        return True, f"tcp_ok {host}:{port} {elapsed:.2f}s"
    except Exception as exc:
        return False, f"tcp_fail {host}:{port}: {exc}"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def quick_check_proxy(proxy_url: str = "", timeout: float = 8.0, log_callback=None, use_cache: bool = True) -> dict:
    """Fast pre-browser proxy health: TCP + HTTP(S) via proxy.

    Does NOT launch Chromium. Returns dict:
      ok, stage(tcp|http|cache), detail, elapsed, proxy
    """
    url = str(proxy_url or "").strip()
    out = {"ok": False, "stage": "", "detail": "", "elapsed": 0.0, "proxy": url}
    if not url:
        out["detail"] = "empty_proxy"
        return out
    if is_proxy_in_cooldown(url):
        out["stage"] = "cooldown"
        out["detail"] = "proxy_in_cooldown"
        return out
    now = time.time()
    if use_cache:
        with _PROXY_BAD_LOCK:
            cached = _PROXY_PRECHECK_CACHE.get(url)
        if cached is not None:
            ok_c, exp_c, detail_c = cached
            if exp_c > now:
                out["ok"] = bool(ok_c)
                out["stage"] = "cache"
                out["detail"] = detail_c or ("cached_ok" if ok_c else "cached_bad")
                return out
    t0 = time.time()
    # Stage 1: TCP
    tcp_ok, tcp_detail = _tcp_check_proxy_endpoint(url, timeout=min(4.0, float(timeout)))
    if not tcp_ok:
        out["stage"] = "tcp"
        out["detail"] = tcp_detail
        out["elapsed"] = time.time() - t0
        mark_proxy_cooldown(url, reason=tcp_detail, log_callback=log_callback)
        return out
    # Stage 2: HTTP(S) through proxy (SOCKS handshake + real egress)
    proxies = {"http": url, "https": url}
    # Prefer short timeout per probe; total budget ~timeout
    per = max(2.5, min(6.0, float(timeout)))
    last_err = ""
    for probe in _PROXY_PRECHECK_PROBE_URLS:
        if time.time() - t0 > float(timeout) + 2.0:
            break
        try:
            resp = requests.get(
                probe,
                proxies=proxies,
                timeout=per,
                allow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            code = int(getattr(resp, "status_code", 0) or 0)
            # Any HTTP response (incl 403/404/302) proves proxy path works
            if code > 0:
                out["ok"] = True
                out["stage"] = "http"
                out["detail"] = f"http_ok code={code} probe={probe} | {tcp_detail}"
                out["elapsed"] = time.time() - t0
                with _PROXY_BAD_LOCK:
                    _PROXY_PRECHECK_CACHE[url] = (
                        True,
                        time.time() + _PROXY_PRECHECK_OK_TTL_SEC,
                        out["detail"],
                    )
                if log_callback:
                    try:
                        log_callback(
                            f"[+] 代理预检通过 | {_mask_proxy_url(url)} | "
                            f"{out['detail']} | {out['elapsed']:.2f}s"
                        )
                    except Exception:
                        pass
                return out
            last_err = f"http_code={code} probe={probe}"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc} probe={probe}"
            # hard reject markers from SOCKS server
            err_l = str(exc).lower()
            if any(
                x in err_l
                for x in (
                    "rejected by the socks5",
                    "socks5",
                    "proxy",
                    "connection refused",
                    "timed out",
                    "timeout",
                    "curl: (97)",
                    "curl: (7)",
                    "curl: (28)",
                    "network is unreachable",
                )
            ):
                # keep trying next probe once if first is CF block weirdness; else continue
                continue
    out["stage"] = "http"
    out["detail"] = last_err or "http_probes_failed"
    out["elapsed"] = time.time() - t0
    mark_proxy_cooldown(url, reason=out["detail"], log_callback=log_callback)
    if log_callback:
        try:
            log_callback(
                f"[!] 代理预检失败 | {_mask_proxy_url(url)} | {out['detail']} | {out['elapsed']:.2f}s"
            )
        except Exception:
            pass
    return out


def pick_live_proxy(
    cfg=None,
    log_callback=None,
    prefer_url: str = "",
    start_index: int = None,
    max_try: int = None,
    timeout: float = 8.0,
) -> str:
    """Pick first LIVE proxy from SOCKS5 pool (skip cooldown, quick_check)."""
    global _PROXY_POOL_INDEX
    c = cfg if isinstance(cfg, dict) else config
    pool = load_proxy_list(c)
    if not pool:
        # non-list mode: check single configured proxy
        single = str(prefer_url or c.get("proxy") or "").strip()
        if single:
            chk = quick_check_proxy(single, timeout=timeout, log_callback=log_callback)
            return single if chk.get("ok") else ""
        return ""
    n = len(pool)
    try:
        limit = int(max_try) if max_try is not None else min(n, max(3, min(12, n)))
    except Exception:
        limit = min(n, 8)
    prefer = str(prefer_url or "").strip()
    order = []
    if prefer and prefer in pool:
        order.append(prefer)
    if start_index is not None:
        try:
            si = int(start_index) % n
        except Exception:
            si = 0
        for k in range(n):
            u = pool[(si + k) % n]
            if u not in order:
                order.append(u)
    else:
        with _PROXY_POOL_LOCK:
            base = int(_PROXY_POOL_INDEX) % n
        for k in range(n):
            u = pool[(base + k) % n]
            if u not in order:
                order.append(u)
    tried = 0
    for url in order:
        if tried >= limit:
            break
        if is_proxy_in_cooldown(url):
            continue
        tried += 1
        chk = quick_check_proxy(url, timeout=timeout, log_callback=log_callback)
        if chk.get("ok"):
            try:
                idx = pool.index(url)
                with _PROXY_POOL_LOCK:
                    _PROXY_POOL_INDEX = idx
            except Exception:
                pass
            return url
    return ""


def ensure_live_proxy_before_browser(log_callback=None, timeout: float = 8.0) -> str:
    """Ensure thread/config proxy is LIVE before launching Chromium.

    Returns the live proxy URL (may be empty for direct mode).
    Rotates SOCKS5 pool on failure; updates thread-local override when active.
    """
    global config
    cur = str(get_configured_proxy() or "").strip()
    mode = str(config.get("proxy_mode", "") or "").strip().lower()
    if mode in ("direct", "none", "off") or not cur:
        return ""
    # Only hard-precheck for SOCKS5 pool / explicit socks proxy; still check others lightly
    chk = quick_check_proxy(cur, timeout=timeout, log_callback=log_callback)
    if chk.get("ok"):
        return cur
    if log_callback:
        try:
            log_callback(
                f"[!] 当前代理预检未通过，轮换存活节点后再开浏览器 | "
                f"{_mask_proxy_url(cur)} | {chk.get('detail')}"
            )
        except Exception:
            pass
    live = ""
    if is_socks5_list_mode():
        pool = load_proxy_list()
        start_idx = 0
        try:
            if cur and pool and cur in pool:
                start_idx = (pool.index(cur) + 1) % len(pool)
        except Exception:
            start_idx = 0
        live = pick_live_proxy(
            log_callback=log_callback,
            prefer_url="",
            start_index=start_idx,
            timeout=timeout,
        )
    else:
        # try resolve a fresh one for cliproxy / other modes
        try:
            if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
                live = str(
                    resolve_runtime_proxy(config, log_callback=log_callback, fetch_live=True) or ""
                ).strip()
                if live:
                    chk2 = quick_check_proxy(live, timeout=timeout, log_callback=log_callback)
                    if not chk2.get("ok"):
                        live = ""
            else:
                live = pick_live_proxy(
                    prefer_url=cur, log_callback=log_callback, timeout=timeout
                )
        except Exception as exc:
            if log_callback:
                try:
                    log_callback(f"[!] 代理重解析失败: {exc}")
                except Exception:
                    pass
            live = ""
    if live:
        try:
            config["proxy"] = live
        except Exception:
            pass
        try:
            ov = get_thread_proxy_override()
            if ov is not None:
                set_thread_proxy(live)
        except Exception:
            # set_thread_proxy may not exist yet at import order — safe no-op
            try:
                set_thread_proxy(live)
            except Exception:
                pass
        if log_callback:
            try:
                log_callback(f"[+] 已切换到存活代理 | {_mask_proxy_url(live)}")
            except Exception:
                pass
        return live
    if log_callback:
        try:
            log_callback("[!] 代理池暂无通过预检的节点；仍将尝试启动浏览器（可能出现 interstitial）")
        except Exception:
            pass
    return cur


def mark_proxy_bad(proxy_url: str = "", log_callback=None):
    """Cooldown current bad proxy and switch to next LIVE pool entry when possible."""
    global _PROXY_POOL_INDEX, config
    cur = str(proxy_url or get_configured_proxy() or "").strip()
    if cur:
        mark_proxy_cooldown(cur, reason="mark_proxy_bad", log_callback=log_callback)
    pool = load_proxy_list()
    if not pool:
        return
    start_idx = 0
    try:
        if cur and cur in pool:
            start_idx = (pool.index(cur) + 1) % len(pool)
        else:
            with _PROXY_POOL_LOCK:
                start_idx = int(_PROXY_POOL_INDEX + 1) % len(pool)
    except Exception:
        start_idx = 0
    nxt = pick_live_proxy(
        prefer_url="",
        start_index=start_idx,
        log_callback=log_callback,
        max_try=min(len(pool), 8),
    )
    if not nxt:
        with _PROXY_POOL_LOCK:
            _PROXY_POOL_INDEX = start_idx % len(pool)
            nxt = pool[_PROXY_POOL_INDEX % len(pool)]
    try:
        config["proxy"] = nxt
    except Exception:
        pass
    # multi-worker: update thread-local override so next browser uses new node
    try:
        ov = get_thread_proxy_override()
        if ov is not None:
            set_thread_proxy(nxt)
    except Exception:
        try:
            set_thread_proxy(nxt)
        except Exception:
            pass
    if log_callback:
        log_callback(f"[*] 通用代理池切换下一条 | {_mask_proxy_url(nxt)} | 池大小={len(pool)}")


def is_socks5_list_mode(cfg=None) -> bool:
    c = cfg if isinstance(cfg, dict) else config
    mode = str(c.get("proxy_mode", "") or "").strip().lower()
    return mode in ("socks5_list", "socks5_pool", "proxy_list", "list", "socks5")


# backward-compat aliases
load_email_proxy_list = load_proxy_list
pick_email_proxy_url = pick_proxy_from_list
mark_email_proxy_bad = mark_proxy_bad


def get_email_proxies(cfg=None, proxy_url=None):
    url = proxy_url if proxy_url is not None else get_configured_proxy()
    if not url:
        return {}
    return {"http": url, "https": url}


def email_http_get(url, **kwargs):
    return http_get(url, **kwargs)


def email_http_post(url, **kwargs):
    return http_post(url, **kwargs)

def _parse_proxy_url(proxy):
    raw = str(proxy or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        return urllib.parse.urlsplit(raw)
    except Exception:
        return None


def _safe_proxy_port(parsed):
    try:
        return parsed.port
    except Exception:
        return None


def _proxy_has_auth(proxy):
    parsed = _parse_proxy_url(proxy)
    return bool(parsed and parsed.hostname and (parsed.username is not None or parsed.password is not None))


def _strip_proxy_auth(proxy):
    raw = str(proxy or "").strip()
    parsed = _parse_proxy_url(raw)
    if not parsed or not parsed.hostname:
        return raw
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = _safe_proxy_port(parsed)
    netloc = f"{host}:{port}" if port else host
    stripped = urllib.parse.urlunsplit((parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment))
    if "://" not in raw:
        return stripped.split("://", 1)[1]
    return stripped


def _proxy_endpoint_terms(proxy=None):
    parsed = _parse_proxy_url(proxy or get_configured_proxy())
    if not parsed or not parsed.hostname:
        return []
    terms = [parsed.hostname]
    port = _safe_proxy_port(parsed)
    if port:
        terms.append(f"{parsed.hostname}:{port}")
        terms.append(f"port {port}")
    return [x.lower() for x in terms if x]


def is_proxy_connection_error(exc):
    if not get_configured_proxy():
        return False
    err = str(exc or "").lower()
    if not err:
        return False
    if any(x in err for x in ("proxy", "tunnel", "socks")):
        return True
    connect_markers = (
        "could not connect",
        "failed to connect",
        "connection refused",
        "connection reset",
        "connect error",
        "timed out",
        "timeout",
    )
    if any(x in err for x in connect_markers):
        terms = _proxy_endpoint_terms()
        if not terms or any(t in err for t in terms):
            return True
    return False


def page_has_proxy_error(page_obj):
    """True for proxy failures AND generic Chromium interstitial error pages.

    18r35e: real failure is often Chromium default error HTML (title=host only,
    Copyright The Chromium Authors) without ERR_PROXY in body.innerText. Also
    callers must pass a fresh page handle after navigation.
    """
    if page_obj is None:
        return False
    try:
        url = str(getattr(page_obj, "url", "") or "")
    except Exception:
        url = ""
    title = ""
    body = ""
    html = ""
    try:
        title = str(page_obj.run_js("return document.title || ''") or "")
    except Exception:
        pass
    try:
        body = str(
            page_obj.run_js(
                "return document.body ? (document.body.innerText || '').slice(0, 3000) : ''"
            )
            or ""
        )
    except Exception:
        pass
    try:
        html = str(getattr(page_obj, "html", "") or "")[:6000]
    except Exception:
        html = ""
    text = f"{url}\n{title}\n{body}\n{html}".lower()
    markers = (
        "err_proxy",
        "err_tunnel",
        "err_connection",
        "err_timed_out",
        "err_name_not_resolved",
        "err_address_unreachable",
        "err_socks",
        "err_ssl",
        "err_network_changed",
        "err_empty_response",
        "err_connection_reset",
        "err_connection_closed",
        "err_connection_refused",
        "err_internet_disconnected",
        "proxy connection failed",
        "proxy server",
        "proxy authentication",
        "tunnel connection failed",
        "this site can't be reached",
        "this site can’t be reached",
        "took too long to respond",
        "dns_probe_finished",
        "checking the proxy",
        "unable to connect",
        "无法连接到代理服务器",
        "代理服务器",
        "无法访问此网站",
        "网页无法打开",
        "没有互联网",
        "连接已重置",
        "临时重定向",
        "err_proxy_connection_failed",
        "neterror",
        "network error",
        "#main-frame-error",
        "main-frame-error",
        "interstitial-wrapper",
        "copyright 2017 the chromium authors",
        "copyright 2015 the chromium authors",
    )
    if any(marker in text for marker in markers):
        return True
    # Chromium interstitial often keeps title=host while body is tiny error chrome UI
    try:
        host_hint = "accounts.x.ai"
        title_l = (title or "").strip().lower()
        body_l = (body or "").strip().lower()
        html_l = (html or "").lower()
        if title_l in (host_hint, "accounts.x.ai") and (
            "chromium authors" in html_l
            or "neterror" in html_l
            or "main-frame-error" in html_l
            or (len(body_l) < 80 and "sign" not in body_l and "邮箱" not in body_l)
        ):
            return True
    except Exception:
        pass
    return False


class _ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _proxy_recv_until_headers(sock, timeout=20, limit=65536):
    sock.settimeout(timeout)
    data = b""
    while b"\r\n\r\n" not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def _proxy_relay(left, right, timeout=60):
    left.settimeout(timeout)
    right.settimeout(timeout)
    sockets = [left, right]
    while True:
        readable, _, _ = select.select(sockets, [], [], timeout)
        if not readable:
            return
        for sock in readable:
            data = sock.recv(65536)
            if not data:
                return
            peer = right if sock is left else left
            peer.sendall(data)


class _LocalAuthProxyBridgeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        bridge = self.server.bridge
        upstream = None
        try:
            initial = _proxy_recv_until_headers(self.request, timeout=bridge.timeout)
            if not initial:
                return
            first_line = initial.split(b"\r\n", 1)[0].decode("latin1", "ignore")
            if first_line.upper().startswith("CONNECT "):
                target = first_line.split()[1]
                if target.startswith("[") and "]:" in target:
                    h, p = target.rsplit("]:", 1)
                    th, tp = h[1:], int(p)
                elif ":" in target:
                    th, tp = target.rsplit(":", 1)
                    tp = int(tp)
                else:
                    th, tp = target, 443
                if getattr(bridge, "upstream_scheme", "http") in ("socks5", "socks5h"):
                    upstream = bridge.open_upstream(th, tp)
                    self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    _proxy_relay(self.request, upstream, timeout=bridge.relay_timeout)
                else:
                    upstream = bridge.open_upstream()
                    req = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
                    if bridge.auth_header:
                        req.append(f"Proxy-Authorization: Basic {bridge.auth_header}")
                    upstream.sendall(("\r\n".join(req) + "\r\n\r\n").encode("latin1"))
                    response = _proxy_recv_until_headers(upstream, timeout=bridge.timeout)
                    if response:
                        self.request.sendall(response)
                    status = response.split(b"\r\n", 1)[0] if response else b""
                    if b" 200 " not in status:
                        return
                    _proxy_relay(self.request, upstream, timeout=bridge.relay_timeout)
            else:
                if getattr(bridge, "upstream_scheme", "http") in ("socks5", "socks5h"):
                    try:
                        parts = first_line.split()
                        url = parts[1] if len(parts) >= 2 else ""
                        pu = urllib.parse.urlsplit(url)
                        th = pu.hostname or ""
                        tp = pu.port or 80
                        if not th:
                            for line in initial.split(b"\r\n")[1:]:
                                if line.lower().startswith(b"host:"):
                                    hv = line.split(b":", 1)[1].strip().decode("latin1")
                                    if ":" in hv:
                                        th, tps = hv.rsplit(":", 1)
                                        tp = int(tps)
                                    else:
                                        th = hv
                                    break
                        upstream = bridge.open_upstream(th, tp)
                        path = pu.path or "/"
                        if pu.query:
                            path += "?" + pu.query
                        lines = initial.split(b"\r\n")
                        if len(parts) >= 3:
                            lines[0] = f"{parts[0]} {path} {parts[2]}".encode("latin1")
                        lines = [
                            ln
                            for ln in lines
                            if not ln.lower().startswith(b"proxy-connection:")
                        ]
                        upstream.sendall(b"\r\n".join(lines))
                        _proxy_relay(self.request, upstream, timeout=bridge.relay_timeout)
                    except Exception:
                        return
                else:
                    upstream = bridge.open_upstream()
                    upstream.sendall(bridge.inject_proxy_auth(initial))
                    _proxy_relay(self.request, upstream, timeout=bridge.relay_timeout)
        except Exception:
            return
        finally:
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:
                    pass

class LocalAuthProxyBridge:
    """Local HTTP proxy bridge for Chromium.

    Supports http/https upstream (Proxy-Authorization) and socks5/socks5h
    upstream with username/password (RFC1929). Chromium uses 127.0.0.1 without auth.
    """

    def __init__(self, proxy_url):
        parsed = _parse_proxy_url(proxy_url)
        if not parsed or not parsed.hostname:
            raise ValueError("认证代理地址格式无效")
        scheme = (parsed.scheme or "http").lower()
        if scheme not in ("http", "https", "socks5", "socks5h"):
            raise ValueError(f"本地认证代理桥不支持协议: {scheme}")
        self.upstream_scheme = scheme
        self.upstream_host = parsed.hostname
        self.upstream_port = _safe_proxy_port(parsed) or (
            443 if scheme == "https" else 1080 if scheme.startswith("socks") else 80
        )
        self.username = urllib.parse.unquote(parsed.username or "")
        self.password = urllib.parse.unquote(parsed.password or "")
        raw_auth = f"{self.username}:{self.password}".encode("utf-8")
        self.auth_header = (
            base64.b64encode(raw_auth).decode("ascii")
            if (self.username or self.password) and scheme in ("http", "https")
            else ""
        )
        self.timeout = 20
        self.relay_timeout = 90
        self.server = None
        self.thread = None
        self.local_proxy = ""

    def open_upstream_http(self):
        sock = socket.create_connection(
            (self.upstream_host, self.upstream_port), timeout=self.timeout
        )
        if self.upstream_scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.upstream_host)
        sock.settimeout(self.timeout)
        return sock

    def open_upstream_socks5(self, target_host: str, target_port: int):
        sock = socket.create_connection(
            (self.upstream_host, self.upstream_port), timeout=self.timeout
        )
        sock.settimeout(self.timeout)
        if self.username or self.password:
            sock.sendall(b"\x05\x01\x02")
            resp = sock.recv(2)
            if len(resp) < 2 or resp[0] != 5 or resp[1] != 2:
                sock.close()
                raise OSError("SOCKS5 上游不接受用户名密码认证")
            u = self.username.encode("utf-8")
            p = self.password.encode("utf-8")
            if len(u) > 255 or len(p) > 255:
                sock.close()
                raise OSError("SOCKS5 用户名/密码过长")
            sock.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            aresp = sock.recv(2)
            if len(aresp) < 2 or aresp[1] != 0:
                sock.close()
                raise OSError("SOCKS5 用户名密码认证失败")
        else:
            sock.sendall(b"\x05\x01\x00")
            resp = sock.recv(2)
            if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
                sock.close()
                raise OSError("SOCKS5 握手失败")
        host_b = str(target_host).encode("idna")
        if len(host_b) > 255:
            sock.close()
            raise OSError("目标主机名过长")
        req = (
            b"\x05\x01\x00\x03"
            + bytes([len(host_b)])
            + host_b
            + struct.pack("!H", int(target_port))
        )
        sock.sendall(req)
        hdr = sock.recv(4)
        if len(hdr) < 4 or hdr[0] != 5 or hdr[1] != 0:
            sock.close()
            raise OSError(f"SOCKS5 CONNECT 失败 code={hdr[1] if len(hdr) > 1 else -1}")
        atyp = hdr[3]
        if atyp == 1:
            sock.recv(4 + 2)
        elif atyp == 3:
            ln = sock.recv(1)
            n = ln[0] if ln else 0
            sock.recv(n + 2)
        elif atyp == 4:
            sock.recv(16 + 2)
        else:
            sock.close()
            raise OSError(f"SOCKS5 未知地址类型 {atyp}")
        sock.settimeout(self.timeout)
        return sock

    def open_upstream(self, target_host=None, target_port=None):
        if self.upstream_scheme in ("socks5", "socks5h"):
            if not target_host or not target_port:
                raise OSError("SOCKS5 上游需要目标 host:port")
            return self.open_upstream_socks5(target_host, int(target_port))
        return self.open_upstream_http()

    def inject_proxy_auth(self, data):
        if not self.auth_header or b"\r\n\r\n" not in data:
            return data
        if b"\r\nproxy-authorization:" in data.lower():
            return data
        head, body = data.split(b"\r\n\r\n", 1)
        auth_line = f"Proxy-Authorization: Basic {self.auth_header}".encode("latin1")
        return head + b"\r\n" + auth_line + b"\r\n\r\n" + body

    def start(self):
        self.server = _ReusableThreadingTCPServer(("127.0.0.1", 0), _LocalAuthProxyBridgeHandler)
        self.server.bridge = self
        port = self.server.server_address[1]
        self.local_proxy = f"http://127.0.0.1:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.local_proxy

    def stop(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        self.server = None
        self.thread = None
        self.local_proxy = ""


def prepare_browser_proxy(use_proxy=True, log_callback=None):
    proxy = get_configured_proxy()
    if not use_proxy or not proxy:
        return "", None
    if _proxy_has_auth(proxy):
        parsed = _parse_proxy_url(proxy)
        scheme = (parsed.scheme or "http").lower() if parsed else ""
        if scheme in ("http", "https", "socks5", "socks5h"):
            try:
                bridge = LocalAuthProxyBridge(proxy)
                browser_proxy = bridge.start()
                if log_callback:
                    log_callback(
                        f"[*] 已为 Chromium 启动本地认证代理桥: {browser_proxy} <- {_mask_proxy_url(proxy)}"
                    )
                return browser_proxy, bridge
            except Exception as exc:
                if log_callback:
                    log_callback(f"[!] 本地认证代理桥启动失败: {exc}")
                return _strip_proxy_auth(proxy), None
        stripped = _strip_proxy_auth(proxy)
        if log_callback:
            log_callback("[!] Chromium 暂不直接支持该认证代理协议，已使用去认证代理地址，失败将回退直连")
        return stripped, None
    parsed = _parse_proxy_url(proxy)
    scheme = (parsed.scheme or "http").lower() if parsed else "http"
    if scheme == "socks5h":
        proxy = proxy.replace("socks5h://", "socks5://", 1)
    return proxy, None

def get_duckmail_api_key():
    return config.get("duckmail_api_key", "")


def get_cloudflare_api_base():
    return str(config.get("cloudflare_api_base", "") or "").rstrip("/")


def get_cloudflare_api_key():
    return config.get("cloudflare_api_key", "")


def get_cloudflare_auth_mode():
    return str(config.get("cloudflare_auth_mode", "none") or "none").lower()


def get_cloudflare_path(key, default_path):
    raw = str(config.get(key, default_path) or default_path).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw


def cloudflare_build_headers(content_type=False):
    headers = {"Content-Type": "application/json"} if content_type else {}
    key = get_cloudflare_api_key()
    mode = get_cloudflare_auth_mode()
    if key:
        if mode == "x-api-key":
            headers["X-API-Key"] = key
        elif mode == "x-admin-auth":
            headers["x-admin-auth"] = key
        elif mode != "none":
            headers["Authorization"] = f"Bearer {key}"
    return headers


def cloudflare_apply_auth_params(params=None):
    merged = dict(params or {})
    key = get_cloudflare_api_key()
    mode = get_cloudflare_auth_mode()
    if key and mode == "query-key":
        merged["key"] = key
    return merged


def cloudflare_next_default_domain():
    """按配置轮换选择 Cloudflare 临时邮箱域名。"""
    global _cf_domain_index
    domains = [x.strip() for x in str(config.get("defaultDomains", "") or "").split(",") if x.strip()]
    if not domains:
        return ""
    domain = domains[_cf_domain_index % len(domains)]
    _cf_domain_index += 1
    return domain


def cloudflare_is_admin_create_path(path):
    """判断当前创建邮箱路径是否为 cloudflare_temp_email 管理员创建接口。"""
    return str(path or "").rstrip("/").lower() == "/admin/new_address"


def _pick_list_payload(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            return data.get("results")
        if isinstance(data.get("hydra:member"), list):
            return data.get("hydra:member")
        if isinstance(data.get("data"), list):
            return data.get("data")
        if isinstance(data.get("messages"), list):
            return data.get("messages")
        if isinstance(data.get("data"), dict):
            nested = data.get("data")
            if isinstance(nested.get("messages"), list):
                return nested.get("messages")
    return []


def cloudflare_create_temp_address(api_base):
    """适配 cloudflare_temp_email 新建地址接口并兼容 admin 创建模式。"""
    path = get_cloudflare_path("cloudflare_path_accounts", "/api/new_address")
    url = f"{api_base}{path}"
    domain = cloudflare_next_default_domain()
    is_admin_create = cloudflare_is_admin_create_path(path)
    if is_admin_create:
        payload = {"name": generate_username(10), "enablePrefix": True}
        if domain:
            payload["domain"] = domain
        headers = cloudflare_build_headers(content_type=True)
    else:
        payload = {}
        if domain:
            payload["domain"] = domain
        headers = {"Content-Type": "application/json"}
    resp = http_post(url, json=payload, headers=headers)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"Cloudflare {path} 返回非JSON: {resp.text[:300]}")
    address = data.get("address")
    jwt = data.get("jwt")
    if not address or not jwt:
        raise Exception(f"Cloudflare {path} 缺少 address/jwt: {data}")
    return address, jwt


def get_user_agent():
    return config.get(
        "user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    )


def resolve_grok2api_local_token_file():
    configured = str(config.get("grok2api_local_token_file", "") or "").strip()
    if configured:
        return configured
    return os.path.join(os.path.dirname(__file__), "token.json")


def _normalize_sso_token(raw_token):
    try:
        from protocol.sso_util import normalize_sso_token
        return normalize_sso_token(raw_token)
    except Exception:
        token = str(raw_token or "").strip()
        if token.startswith("sso="):
            token = token[4:]
        while token.startswith("-") and token[1:].count(".") == 2:
            token = token[1:].strip()
        return token


def _is_importable_session_sso(raw_token):
    """True only for real xAI session SSO; never Outlook mail_token."""
    try:
        from protocol.sso_util import is_mail_token_blob, is_session_sso
        if is_mail_token_blob(raw_token):
            return False
        return bool(is_session_sso(raw_token))
    except Exception:
        token = _normalize_sso_token(raw_token)
        if not token or token.lower().startswith("b64:"):
            return False
        if '"access_token"' in token and '"refresh_token"' in token:
            return False
        return token.count(".") == 2 and 40 <= len(token) <= 800



# 18r44c: process-wide SSO session_id registry (prevent cross-account collision import)
_SSO_SESSION_CLAIM_LOCK = threading.Lock()
_SSO_SESSION_CLAIMS = {}  # session_id -> email


def _extract_sso_session_id(raw_token):
    """Decode xAI session JWT payload.session_id; empty if not parseable."""
    token = _normalize_sso_token(raw_token)
    if not token or token.count(".") != 2:
        return ""
    try:
        import base64 as _b64
        import json as _json
        pl = token.split(".")[1]
        pad = "=" * ((4 - len(pl) % 4) % 4)
        data = _json.loads(_b64.urlsafe_b64decode(pl + pad))
        sid = str((data or {}).get("session_id") or "").strip()
        return sid
    except Exception:
        return ""


def claim_sso_session_or_reject(raw_token, email="", log_callback=None):
    """Claim session_id for email. Returns (ok, session_id, owner_email).

    If another email already claimed this session_id, returns ok=False.
    Same email re-claim is allowed (idempotent).
    """
    log = log_callback or (lambda m: None)
    sid = _extract_sso_session_id(raw_token)
    em = str(email or "").strip().lower()
    if not sid:
        # no sid: allow but warn (cannot dedupe)
        try:
            log(f"[!] sso session_id missing email={email or '-'} — cannot hard-dedupe")
        except Exception:
            pass
        return True, "", ""
    with _SSO_SESSION_CLAIM_LOCK:
        owner = _SSO_SESSION_CLAIMS.get(sid)
        if owner and owner != em:
            try:
                log(
                    f"[!] SSO session collision REJECTED email={email} "
                    f"sid={sid[:13]}... already_owned_by={owner}"
                )
            except Exception:
                pass
            return False, sid, owner
        _SSO_SESSION_CLAIMS[sid] = em or owner or sid
        try:
            log(f"[*] SSO session claimed email={email or '-'} sid={sid[:13]}...")
        except Exception:
            pass
        return True, sid, em


def release_sso_session_claim(raw_token, email=""):
    """Optional release if registration fails after claim (not required for hard reject path)."""
    sid = _extract_sso_session_id(raw_token)
    em = str(email or "").strip().lower()
    if not sid:
        return
    with _SSO_SESSION_CLAIM_LOCK:
        owner = _SSO_SESSION_CLAIMS.get(sid)
        if owner and (not em or owner == em):
            _SSO_SESSION_CLAIMS.pop(sid, None)


def add_token_to_grok2api_local_pool(raw_token, email="", log_callback=None):
    token = _normalize_sso_token(raw_token)
    if not token:
        return False
    if not _is_importable_session_sso(token):
        if log_callback:
            log_callback(
                f"[!] 跳过 G2A 本地入池：值不是 session SSO（疑似邮箱 mail_token/wrapper/reason）"
                f" email={email or '-'} token_len={len(token)}"
            )
        return False
    token_file = resolve_grok2api_local_token_file()
    pool_name = str(config.get("grok2api_pool_name", "ssoBasic") or "ssoBasic").strip()
    if not pool_name:
        pool_name = "ssoBasic"
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    data = {}
    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    pool = data.get(pool_name)
    if not isinstance(pool, list):
        pool = []
    existing = set()
    for item in pool:
        if isinstance(item, str):
            existing.add(_normalize_sso_token(item))
        elif isinstance(item, dict):
            existing.add(_normalize_sso_token(item.get("token", "")))
    if token in existing:
        if log_callback:
            log_callback(f"[*] 号池本地已存在 token: {pool_name}")
        return True
    entry = {"token": token, "tags": ["auto-register"], "note": email}
    pool.append(entry)
    data[pool_name] = pool
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if log_callback:
        log_callback(f"[+] 已写入号池本地: {pool_name} ({token_file})")
    return True


def get_grok2api_remote_api_bases(base):
    """生成号池管理 API 候选根路径。

    参数:
      - base str: 用户配置的号池远端地址

    返回:
      - list[str]: 依次尝试的管理 API 根路径
    """
    normalized = str(base or "").strip().rstrip("/")
    if not normalized:
        return []
    lower = normalized.lower()
    candidates = [normalized]
    if lower.endswith("/admin/api"):
        return candidates
    if lower.endswith("/admin"):
        candidates.append(f"{normalized}/api")
    else:
        candidates.append(f"{normalized}/admin/api")
    seen = set()
    unique = []
    for item in candidates:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def get_grok2api_remote_targets(cfg=None):
    """Return all G2A remote pool targets (primary 8010 + optional mirror 8011/v3).

    Supports:
      - grok2api_remote_base + grok2api_remote_app_key  (primary)
      - grok2api_mirror_remote_base + grok2api_mirror_remote_app_key  (8020 via bridge 8011)
      - grok2api_extra_remote_targets: list[str|dict]
    """
    c = cfg if isinstance(cfg, dict) else config
    targets = []
    pool_name = str(c.get("grok2api_pool_name", "ssoBasic") or "ssoBasic").strip() or "ssoBasic"

    def _add(base, app_key, pool=None, label="primary"):
        b = str(base or "").strip().rstrip("/")
        k = str(app_key or "").strip()
        if not b or not k:
            return
        for t in targets:
            if t.get("base") == b:
                return
        targets.append(
            {
                "base": b,
                "app_key": k,
                "pool_name": str(pool or pool_name).strip() or pool_name,
                "label": str(label or "remote"),
            }
        )

    _add(
        c.get("grok2api_remote_base"),
        c.get("grok2api_remote_app_key"),
        pool_name,
        "primary",
    )
    _add(
        c.get("grok2api_mirror_remote_base"),
        c.get("grok2api_mirror_remote_app_key") or c.get("grok2api_extra_remote_app_key"),
        pool_name,
        "mirror_v3",
    )
    extra = c.get("grok2api_extra_remote_targets") or c.get("grok2api_mirror_targets") or []
    if isinstance(extra, str) and extra.strip():
        extra = [x.strip() for x in re.split(r"[\r\n,;]+", extra) if x.strip()]
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str):
                _add(
                    item,
                    c.get("grok2api_mirror_remote_app_key")
                    or c.get("grok2api_extra_remote_app_key")
                    or c.get("grok2api_remote_app_key"),
                    pool_name,
                    "extra",
                )
            elif isinstance(item, dict):
                _add(
                    item.get("base") or item.get("url") or item.get("remote_base"),
                    item.get("app_key")
                    or item.get("key")
                    or c.get("grok2api_mirror_remote_app_key")
                    or c.get("grok2api_remote_app_key"),
                    item.get("pool_name") or pool_name,
                    item.get("label") or "extra",
                )
    return targets


def add_token_to_grok2api_remote_pool(
    raw_token,
    email="",
    log_callback=None,
    *,
    max_http_tries=None,
    http_timeout=None,
    remote_base=None,
    remote_app_key=None,
    remote_pool_name=None,
    remote_label=None,
):
    token = _normalize_sso_token(raw_token)
    if not token:
        return False
    if not _is_importable_session_sso(token):
        if log_callback:
            log_callback(
                f"[!] 跳过 G2A 远端入池：值不是 session SSO（疑似邮箱 mail_token/wrapper）"
                f" email={email or '-'} token_len={len(token)}"
            )
        return False
    # 长跑 matrix/web 进程热重载，避免 config.json 已改 app_key 但内存仍用旧值导致 401
    try:
        load_config()
    except Exception:
        pass
    base = str(remote_base if remote_base is not None else config.get("grok2api_remote_base", "") or "").strip().rstrip("/")
    app_key = str(remote_app_key if remote_app_key is not None else config.get("grok2api_remote_app_key", "") or "").strip()
    pool_name = str(
        remote_pool_name
        if remote_pool_name is not None
        else (config.get("grok2api_pool_name", "ssoBasic") or "ssoBasic")
    ).strip() or "ssoBasic"
    label = str(remote_label or "primary").strip() or "primary"
    if not base or not app_key:
        if log_callback:
            log_callback(f"[Debug] 号池远端未配置 base/app_key，跳过 label={label}")
        return False
    if app_key.lower() in ("grok2api", "app_key", "your_app_key", "changeme", "admin"):
        msg = (
            f"[!] G2A 远端 app_key 仍是占位字面量 {app_key!r}，"
            "请改为 G2A data/config.toml 的真实 app_key，否则 /tokens/add 会 401"
        )
        if log_callback:
            log_callback(msg)
        raise RuntimeError(msg)
    headers = {"Content-Type": "application/json"}
    query = {"app_key": app_key}
    pool_map = {"ssoBasic": "basic", "ssoSuper": "super"}
    remote_pool = pool_map.get(pool_name, "basic")
    api_bases = get_grok2api_remote_api_bases(base)
    add_errors = []
    # 优先使用 add 接口，避免全量覆盖远端池
    add_payload = {"tokens": [token], "pool": remote_pool, "tags": ["auto-register"]}
    # Retry on 502/503 when pool API is temporarily overloaded (low-RAM hosts + Chromium)
    if max_http_tries is None:
        max_http_tries = 4
    try:
        max_http_tries = int(max_http_tries)
    except (TypeError, ValueError):
        max_http_tries = 4
    max_http_tries = max(1, min(max_http_tries, 10))
    if http_timeout is None:
        http_timeout = 30
    try:
        http_timeout = float(http_timeout)
    except (TypeError, ValueError):
        http_timeout = 30.0
    http_timeout = max(3.0, min(http_timeout, 60.0))
    for api_base in api_bases:
        endpoint = f"{api_base}/tokens/add"
        for attempt in range(1, max_http_tries + 1):
            try:
                if log_callback and attempt == 1:
                    mode = "直连" if _is_loopback_url(endpoint) else "走代理"
                    log_callback(
                        f"[*] 号池远端[{label}] POST {endpoint} | pool={remote_pool}/{pool_name} | {mode}"
                    )
                resp_add = http_post(
                    endpoint,
                    headers=headers,
                    params=query,
                    json=add_payload,
                    timeout=http_timeout,
                )
                resp_add.raise_for_status()
                if log_callback:
                    log_callback(f"[+] 已写入号池远端[{label}]: {pool_name} ({endpoint})")
                return True
            except Exception as add_exc:
                err_s = str(add_exc)
                add_errors.append(f"{endpoint}#{attempt}: {err_s[:160]}")
                status_code = None
                try:
                    status_code = int(getattr(getattr(add_exc, "response", None), "status_code", 0) or 0)
                except Exception:
                    status_code = None
                if status_code in (401, 403):
                    if log_callback:
                        log_callback(
                            f"[!] G2A 远端[{label}] 鉴权失败 status={status_code} endpoint={endpoint}。"
                            "请核对 app_key 是否匹配目标号池。"
                        )
                    raise RuntimeError(
                        f"G2A 远端[{label}] 鉴权失败 status={status_code} endpoint={endpoint}"
                    ) from add_exc
                transient = status_code in (502, 503, 504) or any(
                    x in err_s.lower()
                    for x in ("timeout", "timed out", "connection", "temporarily", "reset")
                )
                if transient and attempt < max_http_tries:
                    wait = min(1.5 * attempt, 6.0)
                    if log_callback:
                        log_callback(
                            f"[Debug] 号池[{label}] /tokens/add 暂失败 ({err_s[:120]})，"
                            f"{wait}s 后重试 {attempt}/{max_http_tries}"
                        )
                    time.sleep(wait)
                    continue
                # Non-retryable for this base (e.g. 404 wrong path) → next api_base
                break
    if log_callback:
        log_callback(
            f"[Debug] [{label}] /tokens/add 写入失败，尝试 /tokens 全量模式: {' '.join(add_errors)}"
        )

    # 兜底：旧版全量保存接口
    current = {}
    fallback_base = api_bases[0] if api_bases else base
    for api_base in api_bases or [base]:
        try:
            resp = http_get(
                f"{api_base}/tokens",
                headers=headers,
                params=query,
                timeout=min(http_timeout, 20),
            )
            if resp.status_code == 200:
                payload = resp.json()
                current = payload.get("tokens", {}) if isinstance(payload, dict) else {}
                fallback_base = api_base
                break
        except Exception:
            continue
    if not isinstance(current, dict):
        # bridge may return list form {"tokens":[...]} — convert for merge safety
        if isinstance(current, list):
            current = {pool_name: current}
        else:
            current = {}
    # bridge list shape: tokens is list not dict-of-pools
    if isinstance(current, list):
        current = {pool_name: current}
    pool = current.get(pool_name)
    if not isinstance(pool, list):
        # if remote returns flat list under tokens already handled; else empty
        pool = []
        # if GET returned list-like under wrong key, keep empty and use add-only path fail
    existing = set()
    for item in pool:
        if isinstance(item, str):
            existing.add(_normalize_sso_token(item))
        elif isinstance(item, dict):
            existing.add(_normalize_sso_token(item.get("token", "") or item.get("sso", "") or item.get("value", "")))
    if token not in existing:
        pool.append({"token": token, "tags": ["auto-register"], "note": email})
    current[pool_name] = pool
    save_errors = []
    save_bases = []
    for item in [fallback_base, *(api_bases or [base])]:
        if item and item not in save_bases:
            save_bases.append(item)
    for api_base in save_bases:
        try:
            resp2 = http_post(
                f"{api_base}/tokens",
                headers=headers,
                params=query,
                json=current,
                timeout=http_timeout,
            )
            resp2.raise_for_status()
            if log_callback:
                log_callback(f"[+] 已写入号池远端[{label}]: {pool_name} ({api_base}/tokens)")
            return True
        except Exception as save_exc:
            save_errors.append(f"{api_base}/tokens: {save_exc}")
    raise RuntimeError(f"号池远端[{label}] /tokens 全量模式写入失败: {' '.join(save_errors)}")


def add_token_to_grok2api_pools(
    raw_token,
    email="",
    log_callback=None,
    *,
    max_http_tries=None,
    http_timeout=None,
):
    if config.get("grok2api_auto_add_local", True):
        try:
            add_token_to_grok2api_local_pool(raw_token, email=email, log_callback=log_callback)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] 写入号池本地失败: {exc}")
    if config.get("grok2api_auto_add_remote", False):
        targets = []
        try:
            targets = get_grok2api_remote_targets()
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] 解析 G2A 远端目标失败: {exc}")
            targets = []
        if not targets:
            # backward path: single primary
            try:
                add_token_to_grok2api_remote_pool(
                    raw_token,
                    email=email,
                    log_callback=log_callback,
                    max_http_tries=max_http_tries,
                    http_timeout=http_timeout,
                )
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] 写入号池远端失败: {exc}")
            return
        ok_n = 0
        fail_n = 0
        for tgt in targets:
            try:
                ok = add_token_to_grok2api_remote_pool(
                    raw_token,
                    email=email,
                    log_callback=log_callback,
                    max_http_tries=max_http_tries,
                    http_timeout=http_timeout,
                    remote_base=tgt.get("base"),
                    remote_app_key=tgt.get("app_key"),
                    remote_pool_name=tgt.get("pool_name"),
                    remote_label=tgt.get("label"),
                )
                if ok:
                    ok_n += 1
                else:
                    fail_n += 1
            except Exception as exc:
                fail_n += 1
                if log_callback:
                    log_callback(
                        f"[Debug] 写入号池远端[{tgt.get('label') or tgt.get('base')}] 失败: {exc}"
                    )
        if log_callback and len(targets) > 1:
            log_callback(f"[*] G2A 多目标入池完成 ok={ok_n} fail={fail_n} targets={len(targets)}")


def _config_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n", ""):
        return False
    return bool(default)


def _post_success_worker_loop():
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
                        log(f"[bg] NSFW 异常: {nsfw_exc}")
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


def ensure_post_success_worker(log_callback=None, workers=None):
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


def wait_post_success_queue(timeout=None, log_callback=None):
    """Wait until background post-success jobs drain (call at job end).

    18r43d: default timeout scales with queue depth so workers=20 backlog
    (awaiting_pool 100+) is not abandoned after a hard 90s.
    """
    log = log_callback or (lambda m: None)
    try:
        with _post_success_pending_lock:
            depth0 = int(_post_success_pending or 0)
        depth0 = max(depth0, int(getattr(_post_success_q, "unfinished_tasks", 0) or 0))
    except Exception:
        depth0 = 0
    if timeout is None:
        # ~25s/item + base 90s, min 90s, max 1h
        timeout = max(90.0, min(3600.0, float(depth0) * 25.0 + 90.0))
    else:
        try:
            timeout = float(timeout)
        except Exception:
            timeout = 90.0
        # never shorter than depth-scaled floor when backlog is large
        if depth0 >= 20:
            timeout = max(timeout, min(3600.0, float(depth0) * 20.0 + 60.0))
    log(f"[*] 等待后处理队列 drain timeout={timeout:.0f}s depth≈{depth0}")
    deadline = time.time() + max(0.0, float(timeout or 0))
    last_log = 0.0
    while True:
        with _post_success_pending_lock:
            pending = _post_success_pending
        unfinished = getattr(_post_success_q, "unfinished_tasks", 0)
        if pending <= 0 and unfinished <= 0:
            log("[*] 后处理队列已清空")
            try:
                if _config_bool(config.get("sub2api_auto_reconcile", True), default=True):
                    from sub2api_client import reconcile_sub2api_pools
                    reconcile_sub2api_pools(config=config, log_callback=log, limit=int(config.get("sub2api_reconcile_limit") or 0))
            except Exception as rec_exc:
                log(f"[!] Sub2API 结束对账异常: {rec_exc}")
            return True
        if time.time() >= deadline:
            log(f"[!] 后处理队列仍有约 {pending} 个未完成（超时返回，后台会继续）")
            return False
        now = time.time()
        # Log every 10s only — avoid flooding Web console every second
        if pending > 0 and (now - last_log) >= 10.0:
            log(f"[*] 等待后处理队列… 剩余约 {pending}（CPA/NSFW 后台中）")
            last_log = now
            # 18r43i: re-ensure drain workers while waiting (replace dead threads)
            try:
                ensure_post_success_worker(log_callback=log)
            except Exception:
                pass
        time.sleep(1.0)


def schedule_post_registration(
    email, password, sso, page=None, cookies=None, log_callback=None
):
    """After sso saved: NSFW + g2a + CPA. Prefer async so next account starts sooner.

    - enable_nsfw + nsfw_async=False → NSFW 同步（你需要立刻开时）
    - post_success_async=True → g2a / Sub2API / CPA（及 async NSFW）进后台
    - cookies: optional pre-exported jar (hybrid path has no live page)
    """
    log = log_callback or (lambda m: print(m, flush=True))
    # 18r44c: never import colliding session_id into G2A/Sub2
    try:
        ok_claim, sid, owner = claim_sso_session_or_reject(sso, email=email, log_callback=log)
        if not ok_claim:
            log(
                f"[!] skip post_registration due to SSO collision email={email} "
                f"sid={(sid or '')[:13]} owner={owner}"
            )
            return {"async": False, "queued": False, "skipped": "sso_session_collision", "owner": owner}
    except Exception as claim_exc:
        try:
            log(f"[!] sso session claim check fail (continue): {claim_exc}")
        except Exception:
            pass
    out_cookies = []
    if isinstance(cookies, list) and cookies:
        out_cookies = [c for c in cookies if isinstance(c, dict)]
        if out_cookies:
            log(f"[cpa] 使用调用方 cookie {len(out_cookies)} 条（供后台 OIDC mint）")
    try:
        import cpa_export

        if not out_cookies and page is not None:
            out_cookies = cpa_export.export_cookies_from_page(page) or []
            if out_cookies:
                log(f"[cpa] 已预导出 cookie {len(out_cookies)} 条（供后台 OIDC mint）")
    except Exception as exc:
        log(f"[cpa] cookie 预导出失败(仍可用 sso): {exc}")
        if not out_cookies:
            out_cookies = []
    cookies = out_cookies

    do_nsfw = bool(config.get("enable_nsfw", True))
    nsfw_async = _config_bool(config.get("nsfw_async", True), default=True)
    post_async = _config_bool(config.get("post_success_async", True), default=True)
    do_g2a = bool(config.get("grok2api_auto_add_remote") or config.get("grok2api_auto_add_local"))
    do_sub2api = _config_bool(config.get("sub2api_auto_add", True), default=True)
    do_cpa = bool(config.get("cpa_export_enabled", True)) and bool(config.get("cpa_auto_add", True))

    # Optional sync NSFW before queueing the rest
    if do_nsfw and not nsfw_async:
        log("[*] 6. 开启 NSFW（同步）")
        try:
            nsfw_ok, nsfw_msg = enable_nsfw_for_token(sso, log_callback=log)
            if nsfw_ok:
                log(f"[+] NSFW 开启成功: {nsfw_msg}")
            else:
                log(f"[!] NSFW 未开启，继续: {nsfw_msg}")
        except Exception as nsfw_exc:
            log(f"[!] NSFW 异常，继续: {nsfw_exc}")
        do_nsfw = False  # already done

    need_queue = do_g2a or do_sub2api or do_cpa or do_nsfw
    if not need_queue:
        return {"async": False, "queued": False}

    if not post_async:
        # Fully synchronous path (old behavior)
        if do_nsfw:
            log("[*] 6. 开启 NSFW")
            try:
                nsfw_ok, nsfw_msg = enable_nsfw_for_token(sso, log_callback=log)
                if nsfw_ok:
                    log(f"[+] NSFW 开启成功: {nsfw_msg}")
                else:
                    log(f"[!] NSFW 未开启，继续: {nsfw_msg}")
            except Exception as nsfw_exc:
                log(f"[!] NSFW 异常，继续: {nsfw_exc}")
        if do_g2a:
            add_token_to_grok2api_pools(sso, email=email, log_callback=log)
        cpa_result = None
        if do_cpa:
            try:
                cpa_result = export_cpa_after_success(
                    email,
                    password or "",
                    sso,
                    page=None,
                    cookies=cookies,
                    log_callback=log,
                )
            except Exception as cpa_exc:
                log(f"[cpa] 导出未成功（SSO 仍已保存）: {cpa_exc}")
                cpa_result = {"ok": False, "error": str(cpa_exc)}
        if do_sub2api:
            try:
                from sub2api_client import import_after_success_prefer_cpa

                import_after_success_prefer_cpa(
                    sso,
                    email=email,
                    password=password or "",
                    cpa_result=cpa_result,
                    config=config,
                    log_callback=log,
                )
            except Exception as sub2api_exc:
                log(f"[!] Sub2API 入池未成功（注册结果保留）: {sub2api_exc}")
                try:
                    from sub2api_client import record_sub2api_import_failure

                    record_sub2api_import_failure(
                        email=email,
                        sso=sso,
                        password=password or "",
                        error=str(sub2api_exc),
                        config=config,
                        log_callback=log,
                    )
                except Exception as rec_exc:
                    log(f"[!] Sub2API 失败落盘异常: {rec_exc}")
        try:
            from sub2api_client import log_pool_counts

            log_pool_counts(config=config, log_callback=log, email=email)
        except Exception:
            pass
        return {"async": False, "queued": False}

    ensure_post_success_worker(log_callback=log)
    global _post_success_pending
    with _post_success_pending_lock:
        _post_success_pending += 1
    _post_success_q.put(
        {
            "email": email,
            "password": password or "",
            "sso": sso,
            "cookies": cookies,
            "do_nsfw": do_nsfw,
            "do_g2a": do_g2a,
            "do_sub2api": do_sub2api,
            "do_cpa": do_cpa,
            "log": log,
        }
    )
    parts = []
    if do_nsfw:
        parts.append("NSFW")
    if do_g2a:
        parts.append("g2a入池")
    if do_sub2api:
        parts.append("Sub2API入池")
    if do_cpa:
        parts.append("CPA")
    log(f"[*] 后处理已入队后台: {'+'.join(parts) or '无'} → 立即开下一号")
    return {"async": True, "queued": True}


def export_cpa_after_success(email, password, sso, page=None, cookies=None, log_callback=None):
    """After successful registration: mint OIDC for free Grok 4.5 (CPA / Build path).

    SSO alone powers web pool models (4.20/4.3). Free grok-4.5 needs OIDC
    via accounts.x.ai device-flow → cpa_auths/xai-*.json → CLIProxyAPI.
    """
    log = log_callback or (lambda m: print(m, flush=True))
    if config.get("cpa_export_enabled", True) is False or config.get("cpa_auto_add", True) is False:
        log("[cpa] export disabled, skip")
        return {"ok": False, "skipped": True, "reason": "disabled"}
    if not email:
        log("[cpa] 缺少 email，跳过 CPA 导出")
        return {"ok": False, "error": "missing email"}
    # protocol path only needs sso; password needed for browser fallback
    if not password and not sso:
        log("[cpa] 缺少 password/sso，跳过 CPA 导出")
        return {"ok": False, "error": "missing password/sso"}
    try:
        import cpa_export
    except Exception as exc:
        log(f"[cpa] 导入 cpa_export 失败: {exc}")
        return {"ok": False, "error": f"import: {exc}"}

    if cookies is None:
        cookies = []
        try:
            cookies = cpa_export.export_cookies_from_page(page) if page is not None else []
        except Exception as exc:
            log(f"[cpa] cookie 导出失败，继续用 sso/协议 mint: {exc}")
            cookies = []
    if cookies:
        log(f"[cpa] 已导出 cookie {len(cookies)} 条供 OIDC mint")

    cpa_cfg = dict(config)
    # Prefer airport/local proxy for mint if cpa_proxy empty
    if not str(cpa_cfg.get("cpa_proxy") or "").strip():
        mode = str(cpa_cfg.get("proxy_mode") or "").strip().lower()
        if mode in ("airport", "mihomo", "kunlun", "airport_mihomo"):
            cpa_cfg["cpa_proxy"] = str(
                cpa_cfg.get("proxy_airport_url")
                or cpa_cfg.get("proxy")
                or "http://127.0.0.1:7893"
            ).strip()
        elif mode in ("socks5", "socks5_list", "proxy_list", "list", "pool"):
            try:
                picked = pick_proxy_from_list(cpa_cfg)
            except Exception:
                picked = ""
            if picked:
                cpa_cfg["cpa_proxy"] = picked
            elif str(cpa_cfg.get("proxy") or "").strip():
                cpa_cfg["cpa_proxy"] = str(cpa_cfg.get("proxy")).strip()
        elif str(cpa_cfg.get("proxy") or "").strip():
            cpa_cfg["cpa_proxy"] = str(cpa_cfg.get("proxy")).strip()
    # Always attach multi-candidate list for CPA mint SOCKS failover + direct
    try:
        pool = load_proxy_list(cpa_cfg) or []
    except Exception:
        pool = []
    if pool:
        primary = str(cpa_cfg.get("cpa_proxy") or "").strip()
        ordered = []
        if primary:
            ordered.append(primary)
        for u in pool:
            if u and u not in ordered:
                ordered.append(u)
        cpa_cfg["cpa_proxy_candidates"] = ordered[:8]
        if not primary and ordered:
            cpa_cfg["cpa_proxy"] = ordered[0]
        log(f"[cpa] proxy pool candidates={len(cpa_cfg['cpa_proxy_candidates'])}")
    if _config_bool(config.get("cpa_gui_close_mint_browser", True), default=True):
        cpa_cfg["cpa_mint_browser_reuse"] = False

    with _cpa_export_lock:
        # Space out device-code mints — auth.x.ai rate-limits bursts (429/slow_down)
        global _cpa_last_mint_ts
        try:
            gap = float(config.get("cpa_mint_gap_sec", 25) or 0)
        except (TypeError, ValueError):
            gap = 25.0
        if gap > 0 and _cpa_last_mint_ts > 0:
            wait = gap - (time.time() - _cpa_last_mint_ts)
            if wait > 0.5:
                log(f"[cpa] mint 间隔保护: 等待 {wait:.1f}s (gap={gap}s)")
                time.sleep(wait)
        try:
            result = cpa_export.export_cpa_xai_for_account(
                email,
                password or "",
                page=page,
                cookies=cookies,
                sso=sso,
                config=cpa_cfg,
                log_callback=log,
            )
        except Exception as exc:
            _cpa_last_mint_ts = time.time()
            log(f"[cpa] CPA 导出异常: {exc}")
            if config.get("cpa_mint_required", False):
                raise
            return {"ok": False, "error": str(exc)}
        _cpa_last_mint_ts = time.time()

    if result.get("ok"):
        log(f"[cpa] CPA/OIDC 已导出: {result.get('path')}")
        if result.get("probe"):
            log(f"[cpa] probe: {result.get('probe')}")
    else:
        log(f"[cpa] CPA 导出失败: {result.get('error') or result}")
    return result


def apply_browser_proxy_option(options, proxy):
    if not proxy:
        return
    if hasattr(options, "set_proxy"):
        try:
            options.set_proxy(proxy)
            return
        except Exception:
            pass
    if not hasattr(options, "set_argument"):
        raise AttributeError("当前 DrissionPage ChromiumOptions 不支持设置浏览器代理")
    try:
        options.set_argument(f"--proxy-server={proxy}")
    except TypeError:
        options.set_argument("--proxy-server", proxy)


def _set_browser_argument(options, arg, value=None):
    if not hasattr(options, "set_argument"):
        return
    try:
        if value is None:
            options.set_argument(arg)
        else:
            options.set_argument(arg, value)
    except TypeError:
        if value is None:
            options.set_argument(arg)
        else:
            options.set_argument(f"{arg}={value}")


def _detect_linux_browser_path():
    """Prefer real Chromium binaries over snap wrapper (/snap/bin/chromium).

    DrissionPage fails to connect CDP when launched via the snap wrapper script,
    but works with .../usr/lib/chromium-browser/chrome.
    """
    env = os.environ.get("GROK_REGISTER_BROWSER_PATH", "").strip()
    # If user pointed at snap wrapper, rewrite to real binary when present.
    snap_real = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
    if env in ("/snap/bin/chromium", "chromium") and os.path.exists(snap_real):
        env = snap_real
    candidates = [
        env,
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        snap_real,
        # versioned snap fallback
        "/snap/chromium/current/usr/lib/chromium-browser/chrome",
        "/snap/bin/chromium",
    ]
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            return path
    return ""


def _linux_display_socket_ok(display: str = "") -> bool:
    display = (display or os.environ.get("DISPLAY", "") or "").strip()
    if not display:
        return False
    try:
        num = display.split(":")[-1].split(".")[0]
        if not num.isdigit():
            return False
        return os.path.exists(f"/tmp/.X11-unix/X{num}")
    except Exception:
        return False


def _ensure_xvfb(log_callback=None) -> bool:
    """Ensure Xvfb is up for DISPLAY (default :99). Returns True if socket ready."""
    if sys.platform == "win32":
        return False
    display = os.environ.get("DISPLAY", "").strip() or ":99"
    os.environ["DISPLAY"] = display
    if _linux_display_socket_ok(display):
        return True
    # Only manage classic :N displays
    try:
        num = display.split(":")[-1].split(".")[0]
        if not num.isdigit():
            return False
    except Exception:
        return False
    if log_callback:
        log_callback(f"[*] DISPLAY={display} 无 X socket，尝试启动 Xvfb...")
    try:
        import subprocess

        log_path = "/var/log/xvfb-99.log" if num == "99" else f"/tmp/xvfb-{num}.log"
        with open(log_path, "a", encoding="utf-8", errors="ignore") as lf:
            subprocess.Popen(
                [
                    "Xvfb",
                    display,
                    "-screen",
                    "0",
                    "1920x1080x24",
                    "-ac",
                    "+extension",
                    "GLX",
                    "+render",
                    "-noreset",
                ],
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )
        for _ in range(20):
            time.sleep(0.25)
            if _linux_display_socket_ok(display):
                if log_callback:
                    log_callback(f"[+] Xvfb 已就绪 DISPLAY={display}")
                return True
    except Exception as exc:
        if log_callback:
            log_callback(f"[!] 启动 Xvfb 失败: {exc}")
    if log_callback:
        log_callback(f"[!] Xvfb 仍不可用 DISPLAY={display}")
    return False


def _linux_should_headless():
    """Prefer headed Chromium under Xvfb when DISPLAY works.

    Pure headless is heavily flagged by Cloudflare on accounts.x.ai.
    GROK_REGISTER_HEADLESS=1 forces headless.
    GROK_REGISTER_HEADLESS=0 prefers headed, but falls back to headless if no X.
    """
    flag = os.environ.get("GROK_REGISTER_HEADLESS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    # Prefer headed when X is available (auto-start Xvfb if needed)
    if _ensure_xvfb():
        if flag in ("0", "false", "no", "off"):
            return False
        return False
    # No display: must headless even if user asked for headed
    return True


def _pick_free_local_port():
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        try:
            sock.close()
        except Exception:
            pass



def _browser_silent_enabled(cfg=None):
    """18r42: silent headed mode (Windows). Env GROK_BROWSER_SILENT overrides."""
    env = (os.environ.get("GROK_BROWSER_SILENT") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        c = cfg if isinstance(cfg, dict) else (config if isinstance(config, dict) else {})
    except Exception:
        c = {}
    if "browser_silent" in c:
        return bool(c.get("browser_silent"))
    # default silent on Windows multi-thread to avoid focus theft
    return sys.platform == "win32"


_SILENCE_KEEPER_LOCK = threading.Lock()
_SILENCE_KEEPER_STOP = None
_SILENCE_KEEPER_THREAD = None
_SILENCE_SCRIPT_PIDS = set()  # only these PIDs may be minimized


def _browser_root_pid(browser):
    try:
        proc = getattr(browser, "process", None) or getattr(browser, "browser_process", None)
        if proc is not None and getattr(proc, "pid", None):
            return int(proc.pid)
    except Exception:
        pass
    return None


def _process_tree_pids(root_pid):
    """Return root + descendants (Windows Toolhelp)."""
    out = set()
    try:
        root_pid = int(root_pid)
    except Exception:
        return out
    out.add(root_pid)
    if sys.platform != "win32":
        return out
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return out
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        children = {}
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                pid = int(pe.th32ProcessID)
                ppid = int(pe.th32ParentProcessID)
                children.setdefault(ppid, []).append(pid)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(snap)
        stack = [root_pid]
        while stack:
            cur = stack.pop()
            for ch in children.get(cur, []):
                if ch not in out:
                    out.add(ch)
                    stack.append(ch)
    except Exception:
        pass
    return out


def _collect_script_chrome_pids(browser=None):
    """PIDs of script chrome.exe only. NEVER include Microsoft Edge/msedge."""
    pids = set()
    browsers = []
    if browser is not None:
        browsers.append(browser)
    try:
        with _ACTIVE_BROWSERS_LOCK:
            browsers.extend([b for b in _ACTIVE_BROWSERS.values() if b is not None])
    except Exception:
        pass
    for b in browsers:
        rp = _browser_root_pid(b)
        if rp:
            pids |= _process_tree_pids(rp)
    # Only Google Chrome automation profiles (DrissionPage). Never msedge.
    if sys.platform == "win32":
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if "msedge" in name:
                        continue
                    if name != "chrome.exe":
                        continue
                    cl = " ".join(proc.info.get("cmdline") or [])
                    if "DrissionPage" not in cl:
                        continue
                    pids.add(int(proc.info["pid"]))
                except Exception:
                    pass
        except Exception:
            pass
    return pids


def _silence_browser_windows(browser=None, log_callback=None, only_pids=None):
    """Minimize SCRIPT Chrome only — never touch the user's normal browser.

    Headed silent mode (not headless) so CF/Turnstile still works.
    Without a PID whitelist this is a no-op (safe for user Chrome).
    """
    if sys.platform != "win32":
        return 0
    if not _browser_silent_enabled():
        return 0

    # Do NOT call DrissionPage mini() — it can activate/focus windows.

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_SHOWMINNOACTIVE = 7
        HWND_BOTTOM = 1
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010

        if only_pids is not None:
            pids = set(int(x) for x in only_pids)
        else:
            pids = _collect_script_chrome_pids(browser)
            with _SILENCE_KEEPER_LOCK:
                if pids:
                    _SILENCE_SCRIPT_PIDS.clear()
                    _SILENCE_SCRIPT_PIDS.update(pids)
                elif _SILENCE_SCRIPT_PIDS:
                    pids = set(_SILENCE_SCRIPT_PIDS)

        if not pids:
            # Safety: without PID whitelist, do nothing (avoids minimizing user Chrome)
            return 0

        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible = user32.IsWindowVisible
        GetClassNameW = user32.GetClassNameW
        ShowWindow = user32.ShowWindow
        SetWindowPos = user32.SetWindowPos
        IsIconic = user32.IsIconic

        targets = []

        def _cb(hwnd, _lparam):
            try:
                if not IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) not in pids:
                    return True  # leave user browser alone
                cls = ctypes.create_unicode_buffer(256)
                GetClassNameW(hwnd, cls, 256)
                cname = cls.value or ""
                if cname not in ("Chrome_WidgetWin_1", "Chrome_WidgetWin_0"):
                    return True
                targets.append(int(hwnd))
            except Exception:
                pass
            return True

        EnumWindows(EnumWindowsProc(_cb), 0)
        n = 0
        for hwnd in targets:
            try:
                ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
                SetWindowPos(
                    hwnd,
                    HWND_BOTTOM,
                    -32000,
                    0,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOACTIVATE,
                )
                if not IsIconic(hwnd):
                    ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
                n += 1
            except Exception:
                pass
        if log_callback and n and os.environ.get("GROK_SILENCE_VERBOSE"):
            log_callback(f"[*] 静默浏览器: 已最小化 {n} 个脚本窗口(不动用户Chrome)")
        return n
    except Exception as exc:
        if log_callback:
            log_callback(f"[Debug] 静默浏览器最小化失败: {exc}")
        return 0


def start_browser_silence_keeper(interval=1.2, log_callback=None):
    """Background re-minimize script Chrome only (page nav restores windows)."""
    global _SILENCE_KEEPER_STOP, _SILENCE_KEEPER_THREAD
    if sys.platform != "win32" or not _browser_silent_enabled():
        return False
    with _SILENCE_KEEPER_LOCK:
        if _SILENCE_KEEPER_THREAD is not None and _SILENCE_KEEPER_THREAD.is_alive():
            return True
        _SILENCE_KEEPER_STOP = threading.Event()
        stop_ev = _SILENCE_KEEPER_STOP

        def _loop():
            while not stop_ev.is_set():
                try:
                    _silence_browser_windows(browser=None, log_callback=None)
                except Exception:
                    pass
                stop_ev.wait(max(0.6, float(interval or 1.2)))

        t = threading.Thread(target=_loop, name="browser-silence-keeper", daemon=True)
        _SILENCE_KEEPER_THREAD = t
        t.start()
    if log_callback:
        log_callback("[*] 浏览器静默守护已启动: 仅最小化脚本Chrome, 不影响用户浏览器")
    return True


def stop_browser_silence_keeper(log_callback=None):
    global _SILENCE_KEEPER_STOP, _SILENCE_KEEPER_THREAD
    with _SILENCE_KEEPER_LOCK:
        if _SILENCE_KEEPER_STOP is not None:
            _SILENCE_KEEPER_STOP.set()
        _SILENCE_KEEPER_STOP = None
        _SILENCE_KEEPER_THREAD = None
        _SILENCE_SCRIPT_PIDS.clear()
    if log_callback:
        log_callback("[*] 浏览器静默守护已停止")


def create_browser_options(browser_proxy="", force_headless=None):
    options = ChromiumOptions()
    # DrissionPage auto_port() may leave address empty on some versions;
    # always pin an explicit local debugging port.
    try:
        options.auto_port()
    except Exception:
        pass
    if not getattr(options, "address", None) or ":" not in str(options.address):
        port = _pick_free_local_port()
        if hasattr(options, "set_local_port"):
            options.set_local_port(port)
        else:
            try:
                options._address = f"127.0.0.1:{port}"
            except Exception:
                pass
    # Give Chromium more time to open remote-debugging port (snap is slow)
    try:
        options.set_timeouts(base=3, page_load=30, script=20)
    except TypeError:
        try:
            options.set_timeouts(base=3)
        except Exception:
            pass
    apply_browser_proxy_option(options, browser_proxy)
    if sys.platform != "win32":
        browser_path = _detect_linux_browser_path()
        if browser_path and hasattr(options, "set_browser_path"):
            try:
                options.set_browser_path(browser_path)
            except Exception:
                pass
        # Fresh user-data dir per launch avoids SingletonLock / zombie chrome conflicts
        base_data = os.environ.get("GROK_REGISTER_USER_DATA", "").strip() or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".chrome-data"
        )
        user_data = os.path.join(
            base_data, f"run-{os.getpid()}-{int(time.time())}-{secrets.token_hex(2)}"
        )
        try:
            os.makedirs(user_data, exist_ok=True)
            if hasattr(options, "set_user_data_path"):
                options.set_user_data_path(user_data)
            elif hasattr(options, "set_paths"):
                options.set_paths(user_data_path=user_data)
        except Exception:
            pass
        _set_browser_argument(options, "--no-sandbox")
        _set_browser_argument(options, "--disable-setuid-sandbox")
        _set_browser_argument(options, "--disable-dev-shm-usage")
        _set_browser_argument(options, "--no-first-run")
        _set_browser_argument(options, "--no-default-browser-check")
        _set_browser_argument(options, "--window-size=900,640")
        # Snap + Xvfb: disable GPU to avoid ANGLE/XCB init failures
        _set_browser_argument(options, "--disable-gpu")
        _set_browser_argument(options, "--disable-software-rasterizer")
        _set_browser_argument(options, "--disable-features=TranslateUI,BlinkGenPropertyTrees")
        # Reduce automation fingerprints (helps Cloudflare / Turnstile)
        _set_browser_argument(options, "--disable-blink-features=AutomationControlled")
        _set_browser_argument(options, "--lang=en-US")
        # Note: do not pass invalid --excludeSwitches=... as a bare chromium flag
        try:
            if hasattr(options, "set_pref"):
                options.set_pref("credentials_enable_service", False)
                options.set_pref("profile.password_manager_enabled", False)
        except Exception:
            pass
        if force_headless is None:
            headless = _linux_should_headless()
        else:
            headless = bool(force_headless)
        if headless:
            try:
                if hasattr(options, "headless"):
                    options.headless(True)
            except Exception:
                pass
            _set_browser_argument(options, "--headless=new")
        if os.path.exists(EXTENSION_PATH) and not headless:
            options.add_extension(EXTENSION_PATH)
        return options
    # 18r31d/18r42: Windows headed window (NOT headless — CF/Turnstile needs real chrome).
    # 18r42 silent: off-screen + --start-minimized + post-launch SW_SHOWMINNOACTIVE.
    try:
        _cfg = config if isinstance(config, dict) else {}
    except Exception:
        _cfg = {}
    try:
        w = int(_cfg.get("browser_window_width") or os.environ.get("GROK_BROWSER_WIDTH") or 900)
    except Exception:
        w = 900
    try:
        h = int(_cfg.get("browser_window_height") or os.environ.get("GROK_BROWSER_HEIGHT") or 640)
    except Exception:
        h = 640
    w = max(640, min(int(w), 1400))
    h = max(480, min(int(h), 1000))
    _set_browser_argument(options, f"--window-size={w},{h}")
    silent = _browser_silent_enabled(_cfg)
    if silent:
        try:
            x = int(_cfg.get("browser_window_x") if _cfg.get("browser_window_x") is not None else os.environ.get("GROK_BROWSER_X") or -32000)
        except Exception:
            x = -32000
        try:
            y = int(_cfg.get("browser_window_y") if _cfg.get("browser_window_y") is not None else os.environ.get("GROK_BROWSER_Y") or 0)
        except Exception:
            y = 0
        _set_browser_argument(options, f"--window-position={x},{y}")
        if bool(_cfg.get("browser_start_minimized", True)):
            _set_browser_argument(options, "--start-minimized")
        # Reduce focus-stealing / flash on multi-thread launch
        _set_browser_argument(options, "--disable-features=CalculateNativeWinOcclusion,MediaRouter")
        _set_browser_argument(options, "--no-first-run")
        _set_browser_argument(options, "--no-default-browser-check")
    else:
        _set_browser_argument(options, "--window-position=40,40")
    if os.path.exists(EXTENSION_PATH):
        options.add_extension(EXTENSION_PATH)
    # 18r44a: per-launch user-data on Windows too (isolate multi-thread cookies/profile)
    try:
        base_data = os.environ.get("GROK_REGISTER_USER_DATA", "").strip() or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".chrome-data"
        )
        user_data = os.path.join(
            base_data, f"win-{os.getpid()}-{int(time.time())}-{secrets.token_hex(3)}"
        )
        os.makedirs(user_data, exist_ok=True)
        if hasattr(options, "set_user_data_path"):
            options.set_user_data_path(user_data)
        elif hasattr(options, "set_paths"):
            options.set_paths(user_data_path=user_data)
    except Exception:
        pass
    return options


def _is_loopback_url(url) -> bool:
    """True for local management APIs that must never go through SOCKS/HTTP proxy."""
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        return True
    if host.endswith(".localhost"):
        return True
    # IPv6 loopback variants
    if host.startswith("127."):
        return True
    return False


def _build_request_kwargs(url=None, **kwargs):
    request_kwargs = dict(kwargs)
    proxies = request_kwargs.pop("proxies", None)
    # Local services (grok2api/CPA on 127.0.0.1) must be direct; SOCKS5 to
    # remote would timeout and look like "号池失败".
    if proxies is None:
        if url and _is_loopback_url(url):
            proxies = {}
        else:
            proxies = get_proxies()
    elif proxies and url and _is_loopback_url(url):
        proxies = {}
    if proxies:
        request_kwargs["proxies"] = proxies
    elif "proxies" in kwargs or (url and _is_loopback_url(url)):
        # Explicit empty proxies disables env/system proxy for curl_cffi
        request_kwargs["proxies"] = {}
    request_kwargs.setdefault("timeout", 15)
    return request_kwargs


def http_get(url, **kwargs):
    request_kwargs = _build_request_kwargs(url=url, **kwargs)
    try:
        return requests.get(url, **request_kwargs)
    except Exception as exc:
        err_l = str(exc).lower()
        if request_kwargs.get("proxies") and (
            is_proxy_connection_error(exc) or "socks" in err_l
        ):
            if is_socks5_list_mode():
                pool = load_proxy_list()
                last = exc
                for _ in range(max(0, len(pool) - 1)):
                    mark_proxy_bad(get_configured_proxy())
                    try:
                        return requests.get(url, **_build_request_kwargs(url=url, **kwargs))
                    except Exception as exc2:
                        last = exc2
                        if not (
                            is_proxy_connection_error(exc2)
                            or "socks" in str(exc2).lower()
                        ):
                            raise
                if bool(config.get("proxy_no_direct_fallback", True)):
                    raise last
            if not is_socks5_list_mode():
                retry_kwargs = dict(kwargs)
                retry_kwargs["proxies"] = {}
                return requests.get(url, **_build_request_kwargs(url=url, **retry_kwargs))
        raise


def http_post(url, **kwargs):
    request_kwargs = _build_request_kwargs(url=url, **kwargs)
    try:
        return requests.post(url, **request_kwargs)
    except Exception as exc:
        err_l = str(exc).lower()
        if request_kwargs.get("proxies") and (
            is_proxy_connection_error(exc) or "socks" in err_l
        ):
            if is_socks5_list_mode():
                pool = load_proxy_list()
                last = exc
                for _ in range(max(0, len(pool) - 1)):
                    mark_proxy_bad(get_configured_proxy())
                    try:
                        return requests.post(url, **_build_request_kwargs(url=url, **kwargs))
                    except Exception as exc2:
                        last = exc2
                        if not (
                            is_proxy_connection_error(exc2)
                            or "socks" in str(exc2).lower()
                        ):
                            raise
                if bool(config.get("proxy_no_direct_fallback", True)):
                    raise last
            if not is_socks5_list_mode():
                retry_kwargs = dict(kwargs)
                retry_kwargs["proxies"] = {}
                return requests.post(url, **_build_request_kwargs(url=url, **retry_kwargs))
        raise

def raise_if_cancelled(cancel_callback=None):
    if cancel_callback and cancel_callback():
        raise RegistrationCancelled("鐢ㄦ埛鍋滄娉ㄥ唽")


def sleep_with_cancel(seconds, cancel_callback=None):
    deadline = time.time() + max(seconds, 0)
    while True:
        raise_if_cancelled(cancel_callback)
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def get_domains(api_key=None):
    headers = {}
    key = api_key or get_duckmail_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = http_get(f"{DUCKMAIL_API_BASE}/domains", headers=headers)
    resp.raise_for_status()
    return resp.json().get("hydra:member", [])


def create_account(address, password, api_key=None, expires_in=0):
    headers = {"Content-Type": "application/json"}
    key = api_key or get_duckmail_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = {"address": address, "password": password, "expiresIn": expires_in}
    resp = http_post(f"{DUCKMAIL_API_BASE}/accounts", json=data, headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_token(address, password):
    data = {"address": address, "password": password}
    resp = http_post(f"{DUCKMAIL_API_BASE}/token", json=data)
    resp.raise_for_status()
    return resp.json().get("token")


def get_messages(token):
    headers = {"Authorization": f"Bearer {token}"}
    resp = http_get(f"{DUCKMAIL_API_BASE}/messages", headers=headers)
    resp.raise_for_status()
    return resp.json().get("hydra:member", [])


def get_message_detail(token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    resp = http_get(f"{DUCKMAIL_API_BASE}/messages/{message_id}", headers=headers)
    resp.raise_for_status()
    return resp.json()


def cloudflare_get_domains(api_base, api_key=None):
    headers = cloudflare_build_headers(content_type=False)
    if api_key and "Authorization" in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    if api_key and "X-API-Key" in headers:
        headers["X-API-Key"] = api_key
    path = get_cloudflare_path("cloudflare_path_domains", "/domains")
    params = cloudflare_apply_auth_params()
    resp = http_get(f"{api_base}{path}", headers=headers, params=params)
    resp.raise_for_status()
    return _pick_list_payload(resp.json())


def cloudflare_create_account(api_base, address, password, api_key=None, expires_in=0):
    headers = cloudflare_build_headers(content_type=True)
    if api_key and "Authorization" in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    if api_key and "X-API-Key" in headers:
        headers["X-API-Key"] = api_key
    payload = {"address": address, "password": password, "expiresIn": expires_in}
    path = get_cloudflare_path("cloudflare_path_accounts", "/accounts")
    params = cloudflare_apply_auth_params()
    resp = http_post(f"{api_base}{path}", json=payload, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def cloudflare_get_token(api_base, address, password, api_key=None):
    headers = cloudflare_build_headers(content_type=True)
    if api_key and "Authorization" in headers:
        headers["Authorization"] = f"Bearer {api_key}"
    if api_key and "X-API-Key" in headers:
        headers["X-API-Key"] = api_key
    path = get_cloudflare_path("cloudflare_path_token", "/token")
    resp = http_post(
        f"{api_base}{path}",
        json={"address": address, "password": password},
        headers=headers,
        params=cloudflare_apply_auth_params(),
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        if data.get("token"):
            return data.get("token")
        if isinstance(data.get("data"), dict) and data["data"].get("token"):
            return data["data"].get("token")
    return None


def cloudflare_get_messages(api_base, token):
    headers = {"Authorization": f"Bearer {token}"}
    path = get_cloudflare_path("cloudflare_path_messages", "/messages")
    params = {"limit": 20, "offset": 0}
    params = cloudflare_apply_auth_params(params)
    resp = http_get(f"{api_base}{path}", headers=headers, params=params)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"Cloudflare messages 返回非JSON: {resp.text[:300]}")
    return _pick_list_payload(data)


def cloudflare_get_message_detail(api_base, token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    candidates = [
        f"{api_base}/api/mail/{message_id}",
        f"{api_base}{get_cloudflare_path('cloudflare_path_messages', '/messages')}/{message_id}",
    ]
    last_err = None
    for url in candidates:
        try:
            resp = http_get(
                url,
                headers=headers,
                params=cloudflare_apply_auth_params(),
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                return data["data"]
            return data
        except Exception as exc:
            last_err = exc
            continue
    raise Exception(f"Cloudflare 获取邮件详情失败: {last_err}")


YYDS_API_BASE = "https://maliapi.215.im/v1"


def get_yyds_api_key():
    return config.get("yyds_api_key", "")


def get_yyds_jwt():
    return config.get("yyds_jwt", "")


def yyds_get_domains(api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    token = jwt or get_yyds_jwt()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif key:
        headers["X-API-Key"] = key
    resp = email_http_get(f"{YYDS_API_BASE}/domains", headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []) if data.get("success") else []


def yyds_create_account(address=None, domain=None, api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    token = jwt or get_yyds_jwt()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif key:
        headers["X-API-Key"] = key
    payload = {}
    if address:
        payload["address"] = address
    if domain:
        payload["domain"] = domain
    elif key or token:
        payload["autoDomainStrategy"] = "prefer_owned"
    resp = email_http_post(f"{YYDS_API_BASE}/accounts", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if data.get("success"):
        return data.get("data", {})
    raise Exception(f"YYDS 鍒涘缓閭澶辫触: {data}")


def yyds_get_token(address, api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    token = jwt or get_yyds_jwt()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif key:
        headers["X-API-Key"] = key
    resp = email_http_post(
        f"{YYDS_API_BASE}/token", json={"address": address}, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("success"):
        return data.get("data", {}).get("token")
    raise Exception(f"YYDS 鑾峰彇token澶辫触: {data}")


def yyds_get_messages(address, token=None, api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    temp_token = token or jwt or get_yyds_jwt()
    headers = {}
    if temp_token:
        headers["Authorization"] = f"Bearer {temp_token}"
    elif key:
        headers["X-API-Key"] = key
    resp = email_http_get(
        f"{YYDS_API_BASE}/messages",
        params={"address": address},
        headers=headers,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("success"):
        return data.get("data", {}).get("messages", [])
    return []


def yyds_get_message_detail(message_id, token=None, api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    temp_token = token or jwt or get_yyds_jwt()
    headers = {}
    if temp_token:
        headers["Authorization"] = f"Bearer {temp_token}"
    elif key:
        headers["X-API-Key"] = key
    resp = email_http_get(f"{YYDS_API_BASE}/messages/{message_id}", headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if data.get("success"):
        return data.get("data", {})
    raise Exception(f"YYDS 鑾峰彇閭欢璇︽儏澶辫触: {data}")


def yyds_generate_username(length=10):
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def yyds_pick_domain(api_key=None, jwt=None):
    domains = yyds_get_domains(api_key=api_key, jwt=jwt)
    if not domains:
        raise Exception("YYDS 娌℃湁杩斿洖浠讳綍鍙敤鍩熷悕")
    private = [d for d in domains if d.get("isVerified") and not d.get("isPublic")]
    if private:
        return private[0]["domain"]
    public = [d for d in domains if d.get("isVerified") and d.get("isPublic")]
    if public:
        return public[0]["domain"]
    verified = [d for d in domains if d.get("isVerified")]
    if verified:
        return verified[0]["domain"]
    raise Exception("YYDS 鏃犲凡楠岃瘉鍩熷悕鍙敤")


def yyds_get_email_and_token(api_key=None, jwt=None):
    key = api_key or get_yyds_api_key()
    token = jwt or get_yyds_jwt()
    if not token and not key:
        raise Exception("YYDS API Key 或 JWT 未配置")
    domain = yyds_pick_domain(api_key=key, jwt=token)
    username = yyds_generate_username(10)
    result = yyds_create_account(
        address=username, domain=domain, api_key=key, jwt=token
    )
    address = result.get("address") or f"{username}@{domain}"
    temp_token = result.get("token")
    if not temp_token:
        temp_token = yyds_get_token(address, api_key=key, jwt=token)
    if not temp_token:
        raise Exception("鑾峰彇 YYDS token 澶辫触")
    ep = pick_email_proxy_url(rotate=False)
    print(f"[*] YYDS mailbox: {address} | proxy={_mask_proxy_url(ep)}")
    return address, temp_token


def yyds_get_oai_code(
    token,
    address,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    jwt=None,
    cancel_callback=None,
):
    deadline = time.time() + timeout
    seen_ids = set()
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        try:
            messages = yyds_get_messages(address, token=token, jwt=jwt)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] YYDS 鎷夊彇閭欢鍒楄〃澶辫触: {exc}")
            sleep_with_cancel(poll_interval, cancel_callback)
            continue
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            to_addrs = [t.get("address", "").lower() for t in (msg.get("to") or [])]
            if address.lower() not in to_addrs:
                continue
            try:
                detail = yyds_get_message_detail(msg_id, token=token, jwt=jwt)
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] YYDS 鑾峰彇閭欢璇︽儏澶辫触: {exc}")
                continue
            parts = []
            text_body = detail.get("text") or ""
            if text_body:
                parts.append(text_body)
            html_list = detail.get("html") or []
            for h in html_list:
                parts.append(re.sub(r"<[^>]+>", " ", h))
            combined = "\n".join(parts)
            subject = detail.get("subject", "")
            if log_callback:
                log_callback(f"[Debug] YYDS 鏀跺埌閭欢: {subject}")
            code = extract_verification_code(combined, subject)
            if code:
                if log_callback:
                    log_callback(f"[*] YYDS 浠庨偖浠朵腑鎻愬彇鍒伴獙璇佺爜: {code}")
                return code
        sleep_with_cancel(poll_interval, cancel_callback)
    raise Exception(f"YYDS 在 {timeout}s 内未收到验证码邮件")


def generate_username(length=10):
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def pick_domain(api_key=None):
    domains = get_domains(api_key=api_key)
    if not domains:
        raise Exception("DuckMail 娌℃湁杩斿洖浠讳綍鍙敤鍩熷悕")
    private = [d for d in domains if d.get("ownerId")]
    verified_private = [d for d in private if d.get("isVerified")]
    if verified_private:
        return verified_private[0]["domain"]
    public = [d for d in domains if d.get("isVerified")]
    if public:
        return public[0]["domain"]
    raise Exception("DuckMail 鏃犲凡楠岃瘉鍩熷悕鍙敤")


def get_email_provider():
    return config.get("email_provider", "duckmail")


def get_email_and_token(api_key=None, log_callback=None):
    """Create one mailbox for current email_provider with detailed logs."""
    provider = get_email_provider()
    provider_key = str(provider or "").strip().lower()

    def _lg(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    _lg(f"[*] 准备获取邮箱 | 当前 email_provider={provider_key}")

    if public_email is not None and public_email.is_public_provider(provider):
        proxies = get_proxies() or None
        try:
            email, token = public_email.create_public_email(
                provider,
                proxies=proxies,
                log_callback=log_callback,
            )
            return email, token
        except Exception as exc:
            # Match http_get/http_post: dead local proxy falls back to direct.
            if proxies and is_proxy_connection_error(exc):
                _lg(f"[!] 公共邮箱经代理失败，改直连重试: {exc}")
                return public_email.create_public_email(
                    provider,
                    proxies=None,
                    log_callback=log_callback,
                )
            raise

    if outlook_mail is not None and outlook_mail.is_outlook_provider(provider_key):
        proxies = get_proxies() or None
        _lg("[*] 邮箱来源: 微软 Outlook / Hotmail / Microsoft 账号池")
        _lg("[*] 获取方式: password+TOTP 登录或 refresh_token 刷新 → Microsoft Graph Mail.Read")
        _lg(f"[*] 账号池文件: {config.get('outlook_accounts_file') or 'outlook_accounts.txt'}")
        try:
            email, token = outlook_mail.get_email_and_token(
                config, proxies=proxies, log_callback=log_callback
            )
            _lg(f"[+] Outlook 邮箱获取成功: {email}")
            return email, token
        except Exception as exc:
            if proxies and is_proxy_connection_error(exc):
                _lg(f"[!] Outlook 经代理失败，改直连重试: {exc}")
                email, token = outlook_mail.get_email_and_token(
                    config, proxies=None, log_callback=log_callback
                )
                _lg(f"[+] Outlook 邮箱获取成功(直连): {email}")
                return email, token
            raise


    if aol_mail is not None and aol_mail.is_aol_provider(provider_key):
        proxies = get_proxies() or None
        _lg("[*] 邮箱来源: AOL / AIM 账号池")
        _lg("[*] 获取方式: IMAP 协议登录 imap.aol.com:993（email----password 或应用专用密码）")
        _lg(f"[*] 账号池文件: {config.get('aol_accounts_file') or 'aol_accounts.txt'}")
        try:
            email, token = aol_mail.get_email_and_token(
                config, proxies=proxies, log_callback=log_callback
            )
            _lg(f"[+] AOL 邮箱获取成功: {email}")
            return email, token
        except Exception as exc:
            if proxies and is_proxy_connection_error(exc):
                _lg(f"[!] AOL 经代理路径失败，改直连重试: {exc}")
                email, token = aol_mail.get_email_and_token(
                    config, proxies=None, log_callback=log_callback
                )
                _lg(f"[+] AOL 邮箱获取成功(直连): {email}")
                return email, token
            raise

    if provider_key == "yyds":
        _lg("[*] 邮箱来源: YYDS 付费邮箱 API")
        _lg("[*] 获取方式: 调用 YYDS 接口创建临时地址")
        email, token = yyds_get_email_and_token(api_key=api_key, jwt=get_yyds_jwt())
        _lg(f"[+] YYDS 邮箱获取成功: {email}")
        return email, token

    if provider_key == "cloudflare":
        api_base = get_cloudflare_api_base()
        if not api_base:
            raise Exception("Cloudflare API Base 未配置")
        _lg(f"[*] 邮箱来源: Cloudflare Worker 自建临时邮箱")
        _lg(f"[*] 调用接口: {api_base}")
        try:
            # cloudflare_temp_email 专用模式
            _lg("[*] Cloudflare 步骤: 专用 create_temp_address")
            email, token = cloudflare_create_temp_address(api_base)
            _lg(f"[+] Cloudflare 邮箱获取成功: {email}")
            return email, token
        except Exception as primary_exc:
            _lg(f"[!] Cloudflare 专用建箱失败，回退 Mail.tm 风格: {primary_exc}")
            key = api_key or get_cloudflare_api_key()
            domains = cloudflare_get_domains(api_base, api_key=key)
            if not domains:
                raise Exception(f"Cloudflare 创建邮箱失败: {primary_exc}")
            verified = [d for d in domains if d.get("isVerified")]
            target = verified[0] if verified else domains[0]
            domain = target.get("domain")
            if not domain:
                raise Exception("Cloudflare 域名数据格式错误，缺少 domain 字段")
            username = generate_username(10)
            address = f"{username}@{domain}"
            password = secrets.token_urlsafe(12)
            _lg(f"[*] Cloudflare 回退建箱: {address} @ {api_base}")
            cloudflare_create_account(
                api_base, address, password, api_key=key, expires_in=0
            )
            token = cloudflare_get_token(api_base, address, password, api_key=key)
            if not token:
                raise Exception("获取 Cloudflare 邮箱 token 失败")
            _lg(f"[+] Cloudflare 回退邮箱获取成功: {address}")
            return address, token

    # duckmail default
    key = api_key or get_duckmail_api_key()
    _lg("[*] 邮箱来源: DuckMail")
    _lg("[*] 获取方式: pick_domain + create_account + get_token")
    domain = pick_domain(api_key=key)
    username = generate_username(10)
    address = f"{username}@{domain}"
    password = secrets.token_urlsafe(12)
    _lg(f"[*] DuckMail 建箱: {address}")
    create_account(address, password, api_key=key, expires_in=0)
    token = get_token(address, password)
    if not token:
        raise Exception("获取 DuckMail token 失败")
    _lg(f"[+] DuckMail 邮箱获取成功: {address}")
    return address, token




def resolve_mailbox_provider(email: str = "", configured: str = "", token_blob: str = "") -> str:
    """Route mailbox ops by email domain / token shape first, then global config.

    18r28f: when UI email_provider=aol, Outlook forced re-register still must use Graph.
    Previously get_oai_code only looked at get_email_provider() and called aol_mail,
    raising "AOL missing password for user@outlook.com" after CreateEmail already sent.
    """
    em = str(email or "").strip().lower()
    conf = str(configured or "").strip().lower()
    tb = str(token_blob or "").strip()
    aol_suffixes = (
        "@aol.com", "@aim.com", "@verizon.net", "@love.com",
        "@ygm.com", "@games.com", "@wow.com",
    )
    outlook_suffixes = (
        "@outlook.com", "@hotmail.com", "@live.com", "@msn.com",
        "@office365.com", "@outlook.jp", "@outlook.fr", "@hotmail.co.uk",
    )
    if em.endswith(outlook_suffixes):
        return "outlook"
    if em.endswith(aol_suffixes):
        return "aol"
    if tb.startswith("{") and (
        "access_token" in tb or "refresh_token" in tb or '"client_id"' in tb
    ):
        return "outlook"
    if "----" in tb:
        left, right = tb.split("----", 1)
        left_l = left.strip().lower()
        right_s = right.strip()
        if "@" in left_l and (
            left_l.endswith(outlook_suffixes)
            or "refresh" in right_s.lower()
            or right_s.startswith("M.")
            or len(right_s) > 80
        ):
            return "outlook"
    if not conf:
        try:
            conf = str(get_email_provider() or "").strip().lower()
        except Exception:
            conf = ""
    try:
        if outlook_mail is not None and outlook_mail.is_outlook_provider(conf):
            return "outlook"
    except Exception:
        pass
    try:
        if aol_mail is not None and aol_mail.is_aol_provider(conf):
            return "aol"
    except Exception:
        pass
    if conf in {"outlook", "microsoft", "hotmail", "graph", "ms", "outlook_mail"}:
        return "outlook"
    if conf in {"aol", "aol_mail", "aol.com", "aim", "verizon_aol"}:
        return "aol"
    return conf or "outlook"


def get_oai_code(
    dev_token,
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
    resend_callback=None,
    since_ts=None,
    ignore_existing=True,
    **kwargs,
):
    # 18r28f: domain/token-first routing (do not trust global provider alone)
    configured = ""
    try:
        configured = str(get_email_provider() or "")
    except Exception:
        configured = ""
    provider = resolve_mailbox_provider(email, configured=configured, token_blob=dev_token)
    if log_callback:
        try:
            log_callback(
                f"[mail] get_oai_code route email={email} provider={provider} "
                f"configured={configured or '-'} token_len={len(str(dev_token or ''))}"
            )
        except Exception:
            pass
    if public_email is not None and public_email.is_public_provider(provider):
        proxies = get_proxies() or None
        try:
            return public_email.get_public_code(
                provider,
                dev_token,
                email,
                timeout=timeout,
                poll_interval=poll_interval,
                log_callback=log_callback,
                cancel_callback=cancel_callback,
                extract_fn=extract_verification_code,
                proxies=proxies,
            )
        except Exception as exc:
            if proxies and is_proxy_connection_error(exc):
                return public_email.get_public_code(
                    provider,
                    dev_token,
                    email,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    log_callback=log_callback,
                    cancel_callback=cancel_callback,
                    extract_fn=extract_verification_code,
                    proxies=None,
                )
            raise
    if outlook_mail is not None and outlook_mail.is_outlook_provider(provider):
        proxies = get_proxies() or None
        try:
            return outlook_mail.get_oai_code(
                config,
                dev_token,
                email,
                timeout=timeout,
                poll_interval=poll_interval,
                log_callback=log_callback,
                cancel_callback=cancel_callback,
                extract_fn=extract_verification_code,
                proxies=proxies,
                ignore_existing=ignore_existing,
                since_ts=since_ts,
                early_no_new_s=kwargs.get("early_no_new_s"),
            )
        except Exception as exc:
            if proxies and is_proxy_connection_error(exc):
                return outlook_mail.get_oai_code(
                config,
                dev_token,
                email,
                timeout=timeout,
                poll_interval=poll_interval,
                log_callback=log_callback,
                cancel_callback=cancel_callback,
                extract_fn=extract_verification_code,
                proxies=None,
                ignore_existing=ignore_existing,
                since_ts=since_ts,
                early_no_new_s=kwargs.get("early_no_new_s"),
            )
            raise
    
    if aol_mail is not None and aol_mail.is_aol_provider(provider):
        proxies = get_proxies() or None
        try:
            return aol_mail.get_oai_code(
                config,
                dev_token,
                email,
                timeout=timeout,
                poll_interval=poll_interval,
                log_callback=log_callback,
                cancel_callback=cancel_callback,
                extract_fn=extract_verification_code,
                proxies=proxies,
                ignore_existing=ignore_existing,
                since_ts=since_ts,
            )
        except Exception as exc:
            if proxies and is_proxy_connection_error(exc):
                if log_callback:
                    log_callback(f"[!] AOL 收信经代理失败，改直连: {exc}")
                return aol_mail.get_oai_code(
                    config,
                    dev_token,
                    email,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    log_callback=log_callback,
                    cancel_callback=cancel_callback,
                    extract_fn=extract_verification_code,
                    proxies=None,
                    ignore_existing=ignore_existing,
                    since_ts=since_ts,
                )
            raise
    if provider == "yyds":
        return yyds_get_oai_code(
            dev_token,
            email,
            timeout=timeout,
            poll_interval=poll_interval,
            log_callback=log_callback,
            jwt=get_yyds_jwt(),
            cancel_callback=cancel_callback,
        )
    if provider == "cloudflare":
        return cloudflare_get_oai_code(
            dev_token,
            email,
            timeout=timeout,
            poll_interval=poll_interval,
            log_callback=log_callback,
            cancel_callback=cancel_callback,
            resend_callback=resend_callback,
        )
    return duckmail_get_oai_code(
        dev_token,
        email,
        timeout=timeout,
        poll_interval=poll_interval,
        log_callback=log_callback,
        cancel_callback=cancel_callback,
    )


def extract_verification_code(text, subject=""):
    """Extract xAI/Grok verification code; never accept bare XXX-XXX from unrelated mail."""
    subject = subject or ""
    text = text or ""
    # Official subject style: "ABC-123 xAI"
    match = re.search(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI\b", subject, re.IGNORECASE)
    if match:
        return match.group(1)
    blob = f"{subject}\n{text}"
    has_xai = bool(
        re.search(
            r"\b(xai|x\.ai|grok|verify(?:\s+your)?\s+email|email\s+verification|"
            r"confirmation\s+code|verification\s+code)\b",
            blob,
            re.IGNORECASE,
        )
    )
    # Dash code only when xAI/Grok context is present (blocks bank "855-730")
    if has_xai:
        match = re.search(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", blob, re.IGNORECASE)
        if match:
            return match.group(1)
    patterns = [
        r"verification\s+code[:\s]+(\d{4,8})",
        r"your\s+code[:\s]+(\d{4,8})",
        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob, re.IGNORECASE)
        if match and has_xai:
            return match.group(1)
    return None


def duckmail_get_oai_code(
    dev_token,
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
):
    deadline = time.time() + timeout
    seen_ids = set()
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        try:
            messages = get_messages(dev_token)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] 鎷夊彇閭欢鍒楄〃澶辫触: {exc}")
            sleep_with_cancel(poll_interval, cancel_callback)
            continue
        for msg in messages:
            msg_id = msg.get("id") or msg.get("msgid")
            if not msg_id or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            recipients = [t.get("address", "").lower() for t in (msg.get("to") or [])]
            if email.lower() not in recipients:
                continue
            try:
                detail = get_message_detail(dev_token, msg_id)
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] 鑾峰彇閭欢璇︽儏澶辫触: {exc}")
                continue
            parts = []
            text_body = detail.get("text") or ""
            if text_body:
                parts.append(text_body)
            html_list = detail.get("html") or []
            for h in html_list:
                parts.append(re.sub(r"<[^>]+>", " ", h))
            combined = "\n".join(parts)
            subject = detail.get("subject", "")
            if log_callback:
                log_callback(f"[Debug] 鏀跺埌閭欢: {subject}")
            code = extract_verification_code(combined, subject)
            if code:
                if log_callback:
                    log_callback(f"[*] 浠庨偖浠朵腑鎻愬彇鍒伴獙璇佺爜: {code}")
                return code
        sleep_with_cancel(poll_interval, cancel_callback)
    raise Exception(f"在 {timeout}s 内未收到验证码邮件")


def cloudflare_get_oai_code(
    dev_token,
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
    resend_callback=None,
):
    api_base = get_cloudflare_api_base()
    if not api_base:
        raise Exception("Cloudflare API Base 未配置")
    deadline = time.time() + timeout
    # 同一封邮件正文可能延迟可读，允许多次重试解析，避免偶发漏码
    seen_attempts = {}
    next_resend_at = time.time() + 35
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        if resend_callback and time.time() >= next_resend_at:
            try:
                resend_callback()
                if log_callback:
                    log_callback("[*] 已触发重新发送验证码")
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] 触发重发验证码失败: {exc}")
            next_resend_at = time.time() + 35
        try:
            messages = cloudflare_get_messages(api_base, dev_token)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] Cloudflare 拉取邮件列表失败: {exc}")
            sleep_with_cancel(poll_interval, cancel_callback)
            continue
        if log_callback:
            log_callback(f"[Debug] Cloudflare 本轮邮件数量: {len(messages)}")

        for msg in messages:
            msg_id = msg.get("id") or msg.get("msgid")
            if not msg_id:
                continue
            attempt = int(seen_attempts.get(msg_id, 0))
            if attempt >= 5:
                continue
            seen_attempts[msg_id] = attempt + 1
            recipients = [t.get("address", "").lower() for t in (msg.get("to") or [])]
            msg_addr = str(msg.get("address", "")).lower()
            # 优先匹配目标邮箱；若结构不一致也允许继续解析，避免接口字段漂移导致漏码
            address_matched = True
            if recipients:
                address_matched = email.lower() in recipients
            elif msg_addr:
                address_matched = msg_addr == email.lower()
            if not address_matched and log_callback:
                log_callback(f"[Debug] 跳过疑似非目标邮件 id={msg_id} address={msg_addr} to={recipients}")
                continue
            parts = []
            # 先直接从列表项取内容，避免 detail 接口差异导致漏码
            for field in ("text", "raw", "content", "intro", "body", "snippet"):
                value = msg.get(field)
                if isinstance(value, str) and value.strip():
                    parts.append(value)
            html_list = msg.get("html") or []
            if isinstance(html_list, str):
                html_list = [html_list]
            for h in html_list:
                parts.append(re.sub(r"<[^>]+>", " ", h))
            subject = str(msg.get("subject", "") or "")
            combined = "\n".join(parts)
            # 再尝试 detail 接口补全内容
            try:
                detail = cloudflare_get_message_detail(api_base, dev_token, msg_id)
                for field in ("text", "raw", "content", "intro", "body", "snippet"):
                    value = detail.get(field)
                    if isinstance(value, str) and value.strip():
                        combined += "\n" + value
                html_list2 = detail.get("html") or []
                if isinstance(html_list2, str):
                    html_list2 = [html_list2]
                for h in html_list2:
                    combined += "\n" + re.sub(r"<[^>]+>", " ", h)
                if not subject:
                    subject = str(detail.get("subject", "") or "")
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] Cloudflare detail接口失败，改用列表内容解析: {exc}")
            if log_callback:
                log_callback(f"[Debug] Cloudflare 收到邮件: {subject}")
            code = extract_verification_code(combined, subject)
            if code:
                if log_callback:
                    log_callback(f"[*] Cloudflare 从邮件中提取到验证码: {code}")
                return code
            elif log_callback:
                log_callback(f"[Debug] 邮件已解析但未提取到验证码 id={msg_id} attempt={seen_attempts[msg_id]}")
        sleep_with_cancel(poll_interval, cancel_callback)
    raise Exception(f"Cloudflare 在 {timeout}s 内未收到验证码邮件")


def generate_random_birthdate():
    import datetime as dt

    today = dt.date.today()
    age = random.randint(20, 40)
    birth_year = today.year - age
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    return f"{birth_year}-{birth_month:02d}-{birth_day:02d}T16:00:00.000Z"


def response_preview(res, limit=200):
    try:
        text = str(res.text or "")
    except Exception:
        text = ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def is_cloudflare_block_response(res):
    try:
        headers = {str(k).lower(): str(v).lower() for k, v in dict(res.headers).items()}
        text = str(res.text or "").lower()
        server = headers.get("server", "")
        content_type = headers.get("content-type", "")
        return (
            res.status_code in (403, 429, 503)
            and (
                "cloudflare" in server
                or "cloudflare" in text
                or "cf-error" in text
                or "__cf_chl" in text
                or "text/html" in content_type
            )
        )
    except Exception:
        return False


def set_birth_date(session, log_callback=None):
    url = "https://grok.com/rest/auth/set-birth-date"
    new_headers = {
        "content-type": "application/json",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
    }
    payload = {"birthDate": generate_random_birthdate()}
    try:
        res = session.post(url, json=payload, headers=new_headers, timeout=15)
        if log_callback:
            log_callback(
                f"[Debug] set_birth_date status: {res.status_code}, body: {response_preview(res)}"
            )
        if 200 <= res.status_code < 300:
            return True, "ok"
        if is_cloudflare_block_response(res):
            return (
                False,
                "set_birth_date 被 grok.com 的 Cloudflare 防护拦截，HTTP "
                f"{res.status_code}",
            )
        return False, f"set_birth_date HTTP {res.status_code}: {response_preview(res)}"
    except Exception as e:
        if log_callback:
            log_callback(f"[set_birth_date] 异常: {e}")
        return False, f"set_birth_date 异常: {e}"


def set_tos_accepted(session, log_callback=None):
    url = "https://accounts.x.ai/auth_mgmt.AuthManagement/SetTosAcceptedVersion"
    payload = struct.pack("B", (2 << 3) | 0) + struct.pack("B", 1)
    data = b"\x00" + struct.pack(">I", len(payload)) + payload
    new_headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": "https://accounts.x.ai",
        "referer": "https://accounts.x.ai/accept-tos",
    }
    try:
        res = session.post(url, data=data, headers=new_headers, timeout=15)
        if log_callback:
            log_callback(f"[Debug] set_tos_accepted status: {res.status_code}")
        if 200 <= res.status_code < 300:
            return True, "ok"
        if is_cloudflare_block_response(res):
            return (
                False,
                "set_tos_accepted 被 accounts.x.ai 的 Cloudflare 防护拦截，HTTP "
                f"{res.status_code}",
            )
        return False, f"set_tos_accepted HTTP {res.status_code}: {response_preview(res)}"
    except Exception as e:
        if log_callback:
            log_callback(f"[set_tos_accepted] 异常: {e}")
        return False, f"set_tos_accepted 异常: {e}"


def encode_grpc_nsfw_settings():
    field1_content = bytes([0x10, 0x01])
    field1 = bytes([0x0A, len(field1_content)]) + field1_content
    nsfw_string = b"always_show_nsfw_content"
    field2_inner = bytes([0x0A, len(nsfw_string)]) + nsfw_string
    field2 = bytes([0x12, len(field2_inner)]) + field2_inner
    payload = field1 + field2
    return b"\x00" + struct.pack(">I", len(payload)) + payload


def update_nsfw_settings(session, log_callback=None):
    url = "https://grok.com/auth_mgmt.AuthManagement/UpdateUserFeatureControls"
    data = encode_grpc_nsfw_settings()
    new_headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
    }
    try:
        res = session.post(url, data=data, headers=new_headers, timeout=15)
        if log_callback:
            log_callback(
                f"[Debug] update_nsfw status: {res.status_code}, body: {response_preview(res)}"
            )
        if 200 <= res.status_code < 300:
            return True, "ok"
        if is_cloudflare_block_response(res):
            return (
                False,
                "update_nsfw_settings 被 grok.com 的 Cloudflare 防护拦截，HTTP "
                f"{res.status_code}",
            )
        return False, f"update_nsfw_settings HTTP {res.status_code}: {response_preview(res)}"
    except Exception as e:
        if log_callback:
            log_callback(f"[update_nsfw] 异常: {e}")
        return False, f"update_nsfw_settings 异常: {e}"


def enable_nsfw_for_token(token, cf_clearance="", log_callback=None):
    """Enable NSFW. Prefer current proxy; on SOCKS/proxy transport fail, retry direct."""
    user_agent = get_user_agent()
    cookie_parts = [f"sso={token}", f"sso-rw={token}"]
    if cf_clearance:
        cookie_parts.append(f"cf_clearance={cf_clearance}")
    cookie_hdr = "; ".join(cookie_parts)

    def _proxy_transport_fail(msg: str) -> bool:
        s = (msg or "").lower()
        keys = (
            "socks",
            "proxy",
            "curl: (97)",
            "curl: (7)",
            "curl: (28)",
            "cannot complete socks",
            "failed to perform",
            "connection refused",
            "tunnel",
            "proxy connect",
        )
        return any(k in s for k in keys)

    def _run(proxies, label: str):
        log = log_callback or (lambda m: None)
        log(f"[nsfw] try path={label} proxy={'yes' if proxies else 'direct'}")
        with requests.Session(impersonate="chrome120", proxies=proxies or None) as session:
            session.headers.update({"user-agent": user_agent, "cookie": cookie_hdr})
            ok, message = set_tos_accepted(session, log_callback)
            if not ok:
                return False, message
            ok, message = set_birth_date(session, log_callback)
            if not ok:
                return False, message
            ok, message = update_nsfw_settings(session, log_callback)
            if not ok:
                return False, message
            return True, f"成功开启 NSFW ({label})"

    try:
        proxies = get_proxies() or None
    except Exception:
        proxies = None
    attempts = []
    if proxies:
        attempts.append((proxies, "proxy"))
    attempts.append((None, "direct"))
    last_msg = ""
    seen = set()
    for proxies, label in attempts:
        if label in seen:
            continue
        seen.add(label)
        try:
            ok, message = _run(proxies, label)
            if ok:
                return True, message
            last_msg = message
            if label == "proxy":
                if log_callback:
                    log_callback(f"[nsfw] proxy path failed, fallback direct: {message}")
                continue
            return False, message
        except Exception as e:
            last_msg = str(e)
            if log_callback:
                log_callback(f"[nsfw] path={label} exception: {e}")
            if label == "proxy":
                continue
            return False, f"异常: {e}"
    return False, last_msg or "NSFW 开启失败"


SIGNUP_URL = "https://accounts.x.ai/sign-up?redirect=grok-com"

# ===== 18r30 thread-local browser + per-worker proxy =====
_tls = threading.local()
_ACTIVE_BROWSERS_LOCK = threading.Lock()
_ACTIVE_BROWSERS = {}  # thread_id -> Chromium


def _tls_browser_state():
    """Per-thread browser state (each worker has its own Chromium)."""
    t = _tls
    if not getattr(t, "_browser_inited", False):
        t.browser = None
        t.page = None
        t.browser_proxy_bridge = None
        t.browser_started_with_proxy = False
        t.proxy_override = None
        t._browser_inited = True
    return t


def set_thread_proxy(proxy_url: str = "") -> None:
    """Bind proxy URL for this worker thread (SOCKS5 per-thread sequential reuse)."""
    _tls_browser_state().proxy_override = str(proxy_url or "")


def clear_thread_proxy() -> None:
    st = _tls_browser_state()
    st.proxy_override = None


def get_thread_proxy_override():
    st = _tls_browser_state()
    return getattr(st, "proxy_override", None)


def _register_active_browser(b) -> None:
    tid = threading.get_ident()
    with _ACTIVE_BROWSERS_LOCK:
        if b is None:
            _ACTIVE_BROWSERS.pop(tid, None)
        else:
            _ACTIVE_BROWSERS[tid] = b


def _stop_all_thread_browsers(log_callback=None) -> int:
    """Quit every worker Chromium. Does NOT stop Grok2API/Sub2API/CLIProxy/CPA."""
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    with _ACTIVE_BROWSERS_LOCK:
        items = list(_ACTIVE_BROWSERS.items())
        _ACTIVE_BROWSERS.clear()
    n = 0
    for tid, b in items:
        if b is None:
            continue
        try:
            b.quit(del_data=True)
            n += 1
        except Exception as exc:
            _lg(f"[!] stop thread browser tid={tid}: {exc}")
    try:
        st = _tls_browser_state()
        st.browser = None
        st.page = None
        st.browser_proxy_bridge = None
        st.browser_started_with_proxy = False
    except Exception:
        pass
    if n:
        _lg(f"[*] 已关闭 {n} 个 worker 浏览器实例")
    return n


def _sync_module_browser_aliases():
    """Mirror current-thread TLS onto module attrs (compat for single-thread code)."""
    global browser, page, browser_proxy_bridge, browser_started_with_proxy
    st = _tls_browser_state()
    browser = st.browser
    page = st.page
    browser_proxy_bridge = st.browser_proxy_bridge
    browser_started_with_proxy = bool(st.browser_started_with_proxy)


browser = None
page = None
browser_proxy_bridge = None
browser_started_with_proxy = False


def setup_light_theme(root):
    try:
        root.option_add("*Background", UI_BG)
        root.option_add("*Foreground", UI_FG)
        root.option_add("*selectBackground", UI_ACTIVE_BG)
        root.option_add("*selectForeground", UI_FG)
        root.option_add("*insertBackground", UI_FG)
        root.option_add("*Entry.Background", UI_ENTRY_BG)
        root.option_add("*Text.Background", UI_ENTRY_BG)
        root.option_add("*Menu.Background", UI_ENTRY_BG)
        root.option_add("*Menu.Foreground", UI_FG)
        style = ttk.Style(root)
        available = set(style.theme_names())
        if "clam" in available:
            style.theme_use("clam")
        elif "default" in available:
            style.theme_use("default")
        root.configure(bg=UI_BG)
        style.configure(".", background=UI_BG, foreground=UI_FG, fieldbackground=UI_ENTRY_BG)
        style.configure("TFrame", background=UI_BG)
        style.configure("TLabelframe", background=UI_BG, foreground=UI_FG)
        style.configure("TLabelframe.Label", background=UI_BG, foreground=UI_FG)
        style.configure("TLabel", background=UI_BG, foreground=UI_FG)
        style.configure("TCheckbutton", background=UI_BG, foreground=UI_FG)
        style.configure("TButton", background=UI_BUTTON_BG, foreground=UI_FG)
        style.configure("TEntry", fieldbackground=UI_ENTRY_BG, foreground=UI_FG)
        style.configure("TCombobox", fieldbackground=UI_ENTRY_BG, foreground=UI_FG)
        style.configure("TSpinbox", fieldbackground=UI_ENTRY_BG, foreground=UI_FG)
    except Exception:
        pass


def tk_label(parent, text="", **kwargs):
    return tk.Label(parent, text=text, bg=kwargs.pop("bg", UI_BG), fg=kwargs.pop("fg", UI_FG), **kwargs)


def tk_entry(parent, textvariable=None, width=30, **kwargs):
    return tk.Entry(
        parent,
        textvariable=textvariable,
        width=width,
        bg=UI_ENTRY_BG,
        fg=UI_FG,
        insertbackground=UI_FG,
        disabledbackground="#2f2f2f",
        disabledforeground=UI_MUTED_FG,
        highlightthickness=1,
        highlightbackground="#555555",
        relief=tk.SOLID,
        **kwargs,
    )


def tk_button(parent, text="", command=None, state=None, **kwargs):
    if state is None:
        state = tk.NORMAL if HAS_TK else "normal"
    return tk.Button(
        parent,
        text=text,
        command=command,
        state=state,
        bg=UI_BUTTON_BG,
        fg=UI_FG,
        activebackground=UI_ACTIVE_BG,
        activeforeground=UI_FG,
        disabledforeground="#777777",
        relief=tk.RAISED,
        padx=10,
        pady=3,
        **kwargs,
    )


def tk_checkbutton(parent, text="", variable=None, **kwargs):
    return tk.Checkbutton(
        parent,
        text=text,
        variable=variable,
        bg=UI_BG,
        fg=UI_FG,
        activebackground=UI_BG,
        activeforeground=UI_FG,
        selectcolor="#3d7be0",
        **kwargs,
    )


def tk_option_menu(parent, variable, values, width=12):
    menu = tk.OptionMenu(parent, variable, *values)
    menu.configure(
        width=width,
        bg=UI_ENTRY_BG,
        fg=UI_FG,
        activebackground=UI_ACTIVE_BG,
        activeforeground=UI_FG,
        highlightthickness=1,
        highlightbackground="#555555",
        relief=tk.SOLID,
    )
    menu["menu"].configure(bg=UI_ENTRY_BG, fg=UI_FG, activebackground=UI_ACTIVE_BG, activeforeground=UI_FG)
    return menu


def _apply_browser_stealth(tab, log_callback=None):
    """Best-effort anti-automation patches after tab is ready."""
    if tab is None:
        return
    js = r"""
try {
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
} catch (e) {}
try {
  if (!window.chrome) { window.chrome = { runtime: {} }; }
} catch (e) {}
try {
  Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
} catch (e) {}
try {
  Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
} catch (e) {}
"""
    try:
        tab.run_js(js)
    except Exception as exc:
        if log_callback:
            log_callback(f"[Debug] stealth 脚本注入失败: {exc}")



def start_browser(log_callback=None, use_proxy=True):
    """Start Chromium for *this thread* only (18r30 TLS; multi-worker safe)."""
    st = _tls_browser_state()
    last_exc = None
    # 18r44d: precheck SOCKS5 / proxy LIVE before launching Chromium (avoid interstitial on first open)
    if use_proxy and get_configured_proxy():
        try:
            ensure_live_proxy_before_browser(log_callback=log_callback)
        except Exception as _pre_exc:
            if log_callback:
                try:
                    log_callback(f"[!] 代理预检异常(继续启动): {_pre_exc}")
                except Exception:
                    pass
    proxy_enabled = bool(use_proxy and get_configured_proxy())
    if sys.platform != "win32":
        _ensure_xvfb(log_callback=log_callback)
    for attempt in range(1, 5):
        bridge = None
        force_hl = None
        if sys.platform != "win32" and attempt >= 3:
            force_hl = True
            if log_callback and attempt == 3:
                log_callback("[!] 有头模式多次失败，回退无头 headless=new 重试")
        try:
            browser_proxy, bridge = prepare_browser_proxy(use_proxy=use_proxy, log_callback=log_callback)
            b = Chromium(
                create_browser_options(browser_proxy=browser_proxy, force_headless=force_hl)
            )
            st.browser = b
            st.browser_proxy_bridge = bridge
            st.browser_started_with_proxy = bool(browser_proxy)
            tabs = b.get_tabs()
            p = tabs[-1] if tabs else b.new_tab()
            st.page = p
            _register_active_browser(b)
            _sync_module_browser_aliases()
            _apply_browser_stealth(p, log_callback=log_callback)
            try:
                start_browser_silence_keeper(interval=1.0, log_callback=None)
                _silence_browser_windows(b, log_callback=log_callback)
            except Exception:
                pass
            if log_callback and sys.platform == "win32" and _browser_silent_enabled():
                log_callback("[*] 浏览器静默模式: headed+屏外+PID白名单守护 (只压脚本Chrome, CF可用)")
            if log_callback and getattr(b, "user_data_path", None):
                log_callback(f"[Debug] 当前浏览器资料目录: {b.user_data_path}")
            if log_callback:
                if sys.platform != "win32":
                    hl = force_hl if force_hl is not None else _linux_should_headless()
                    log_callback(
                        f"[*] 浏览器显示模式: {'无头 headless' if hl else '有头 headed(Xvfb/DISPLAY)'} "
                        f"DISPLAY={os.environ.get('DISPLAY') or '(空)'} "
                        f"Xsocket={'ok' if _linux_display_socket_ok() else 'missing'}"
                    )
                if get_configured_proxy():
                    mode = "代理" if st.browser_started_with_proxy else "直连"
                    log_callback(f"[*] 浏览器网络模式: {mode}")
                    meta = config.get("_last_proxy_exit") if isinstance(config, dict) else None
                    if isinstance(meta, dict) and meta.get("exit_ip"):
                        log_callback(
                            f"[*] 出口家宽提醒: {meta.get('exit_ip')} "
                            f"({meta.get('exit_org') or '?'}) "
                            f"res={meta.get('isResidential')} fraud={meta.get('fraudScore')} "
                            f"| 入口网关仅={meta.get('gateway')}"
                        )
            if log_callback and attempt > 1:
                log_callback(f"[*] 浏览器第 {attempt} 次启动成功")
            return st.browser, st.page
        except Exception as exc:
            last_exc = exc
            if bridge is not None:
                try:
                    bridge.stop()
                except Exception:
                    pass
            if log_callback:
                mode = "代理" if proxy_enabled else "直连"
                log_callback(f"[Debug] 浏览器{mode}启动失败(第{attempt}/4次): {exc}")
            try:
                if st.browser is not None:
                    st.browser.quit(del_data=True)
            except Exception:
                pass
            st.browser = None
            st.page = None
            st.browser_proxy_bridge = None
            st.browser_started_with_proxy = False
            _register_active_browser(None)
            _sync_module_browser_aliases()
            if sys.platform != "win32" and attempt == 1:
                _ensure_xvfb(log_callback=log_callback)
            time.sleep(min(1.5 * attempt, 4))
    raise Exception(f"浏览器启动失败，已重试4次: {last_exc}")



def stop_browser_proxy_bridge(log_callback=None):
    """Stop local Chromium auth proxy bridge if running (this thread only)."""
    st = _tls_browser_state()
    bridge = st.browser_proxy_bridge
    st.browser_proxy_bridge = None
    _sync_module_browser_aliases()
    if bridge is None:
        return
    try:
        bridge.stop()
        if log_callback:
            log_callback("[*] 本地认证代理桥已关闭")
    except Exception as exc:
        if log_callback:
            log_callback(f"[!] 关闭本地认证代理桥失败: {exc}")



def stop_browser(log_callback=None):
    """Close DrissionPage browser + local proxy bridge for *this thread*."""
    st = _tls_browser_state()
    _lg = log_callback if callable(log_callback) else None
    b = st.browser
    st.browser = None
    st.page = None
    st.browser_started_with_proxy = False
    _register_active_browser(None)
    _sync_module_browser_aliases()
    if b is not None:
        try:
            b.quit(del_data=True)
            if _lg:
                _lg("[*] 浏览器已关闭")
        except Exception as exc:
            if _lg:
                _lg(f"[!] browser.quit 失败: {exc}")
    stop_browser_proxy_bridge(log_callback=log_callback)


def force_kill_registration_browsers(log_callback=None):
    """Kill leftover SCRIPT Chrome only. NEVER touch msedge/Edge/WebView2 (user browser).

    18r42 Edge-safe: do NOT match bare userData — Microsoft Edge always has --user-data-dir.
    Only chrome.exe / chromedriver.exe with script markers (DrissionPage / project paths).
    """
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    killed = []
    if sys.platform != "win32":
        return killed
    try:
        import subprocess

        # Never include msedge. Never match bare userData (kills personal Edge).
        ps = r"""
$pat = 'DrissionPage|\.chrome-data|grok-regkit|auto_port|accounts\.x\.ai'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|chromedriver)\.exe$' -and
    $_.CommandLine -and ($_.CommandLine -match $pat)
  } |
  ForEach-Object {
    try {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
      $_.ProcessId
    } catch {}
  }
"""
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stderr=subprocess.STDOUT,
            timeout=20,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        for line in (out or "").splitlines():
            line = line.strip()
            if line.isdigit():
                killed.append(int(line))
        # second pass — only chrome under project .chrome-data (never msedge)
        try:
            ps2 = r"""
$root = 'C:\Users\zhang\grok-regkit\.chrome-data'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|chromedriver)\.exe$' -and
    $_.CommandLine -and (
      $_.CommandLine -like ('*' + $root + '*') -or
      ($_.CommandLine -match 'DrissionPage' -and $_.CommandLine -match 'run-\d+-\d+-[0-9a-f]{4}')
    )
  } |
  ForEach-Object {
    try {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
      $_.ProcessId
    } catch {}
  }
"""
            out2 = subprocess.check_output(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps2],
                stderr=subprocess.STDOUT,
                timeout=20,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            for line in (out2 or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid not in killed:
                        killed.append(pid)
        except Exception as _e2:
            _lg(f"[!] force_kill second pass: {_e2}")
        if killed:
            _lg(f"[*] 已强制结束残留脚本 Chrome 进程(Edge-safe): {killed}")
        else:
            _lg("[*] 无匹配的残留脚本 Chrome 进程(Edge 不受影响)")
    except Exception as exc:
        _lg(f"[!] 强制结束浏览器失败: {exc}")
    return killed



def force_stop_registration(log_callback=None, reason="user_stop"):
    """Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA/web."""
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    _lg(f"[!] force_stop_registration: {reason}")
    try:
        config["stop_requested"] = True
    except Exception:
        pass
    try:
        stop_browser_silence_keeper(log_callback=_lg)
    except Exception:
        pass
    try:
        from worker_coord import stop_continuous_preflight
        stop_continuous_preflight(log=_lg)
    except Exception as _cpf:
        _lg(f"[!] stop continuous preflight in force_stop: {_cpf}")
    try:
        stop_browser(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] stop_browser in force_stop: {exc}")
    try:
        _stop_all_thread_browsers(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] stop_all_thread_browsers: {exc}")
    try:
        force_kill_registration_browsers(log_callback=_lg)
    except Exception as exc:
        _lg(f"[!] force_kill in force_stop: {exc}")


def shutdown_browser():
    """Alias for hybrid/token_harvester (grok_reg API)."""
    stop_browser()



def _get_browser():
    """Alias for hybrid/token_harvester (thread-local)."""
    return _tls_browser_state().browser


def _get_page():
    """Alias for hybrid/token_harvester; refresh tab if needed (thread-local)."""
    st = _tls_browser_state()
    if st.browser is None:
        return None
    if st.page is None:
        try:
            return refresh_active_page()
        except Exception:
            return None
    return st.page


def restart_browser(log_callback=None, use_proxy=True):
    stop_browser()
    return start_browser(log_callback=log_callback, use_proxy=use_proxy)


def cleanup_runtime_memory(log_callback=None, reason="定期清理"):
    if log_callback:
        log_callback(f"[*] {reason}: 关闭浏览器并清理内存")
    stop_browser()
    collected = gc.collect()
    if log_callback:
        log_callback(f"[*] Python GC 已回收对象数: {collected}")


def refresh_active_page():
    st = _tls_browser_state()
    if st.browser is None:
        restart_browser()
        st = _tls_browser_state()
    try:
        tabs = st.browser.get_tabs()
        if tabs:
            st.page = tabs[-1]
        else:
            st.page = st.browser.new_tab()
    except Exception:
        restart_browser()
        st = _tls_browser_state()
    _sync_module_browser_aliases()
    return st.page


def click_email_signup_button(timeout=10, log_callback=None, cancel_callback=None):
    page = _get_page()
    if page is None:
        raise Exception('浏览器 page 未就绪')
    deadline = time.time() + timeout
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = _get_page() or page
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.4, cancel_callback)
            continue
        if log_callback:
            log_callback("[Debug] 尝试查找“使用邮箱注册”按钮...")

        # 18r35e: do not burn full timeout on Chromium error interstitial
        try:
            if page_has_proxy_error(page):
                if log_callback:
                    try:
                        log_callback(f"[!] click_email abort: browser error page url={getattr(page, 'url', '')}")
                    except Exception:
                        log_callback("[!] click_email abort: browser error page")
                raise Exception("未找到「使用邮箱注册」按钮(浏览器错误页/代理失败)")
        except Exception as _early_pe:
            if "未找到「使用邮箱注册」按钮" in str(_early_pe):
                raise
            # detection itself failed — continue normal click path

        try:
            clicked = page.run_js(r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
function nodeText(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
        node.getAttribute('href'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
function scoreEntry(node) {
    const compact = nodeText(node).replace(/\s+/g, '');
    const lower = compact.toLowerCase();
    if (compact.includes('使用邮箱注册')) return 100;
    if (lower.includes('signupwithemail')) return 95;
    if (lower.includes('continuewithemail')) return 90;
    if (lower.includes('email') && (lower.includes('sign') || lower.includes('continue') || lower.includes('use') || lower.includes('with'))) return 80;
    if (lower === 'email' || lower.includes('邮箱')) return 70;
    return 0;
}
const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter((node) => isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true')
    .map((node) => ({ node, score: scoreEntry(node), text: nodeText(node) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);
const target = candidates[0]?.node || null;
if (!target) {
    return false;
}
target.click();
return candidates[0].text || true;
        """)
        except Exception as _ce_exc:
            em = str(_ce_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] click_email page disconnected: {_ce_exc}")
                try:
                    page = refresh_active_page()
                except Exception:
                    page = _get_page()
                sleep_with_cancel(0.5, cancel_callback)
                continue
            raise

        if clicked:
            if log_callback:
                detail = f": {clicked}" if isinstance(clicked, str) else ""
                log_callback(f"[*] 已点击「使用邮箱注册」按钮{detail}")
            sleep_with_cancel(2, cancel_callback)
            return True

        if log_callback:
            current_url = page.url if page else "none"
            log_callback(f"[Debug] 当前URL: {current_url}")

        sleep_with_cancel(1, cancel_callback)

    if log_callback:
        page_html = page.html[:500] if page else "no page"
        log_callback(f"[Debug] 页面内容片段: {page_html}")

    raise Exception("未找到「使用邮箱注册」按钮")



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


def page_is_cloudflare_challenge(page_obj=None):
    """Detect Cloudflare interstitial / attention page."""
    p = page_obj or page
    if p is None:
        return False
    try:
        title = str(getattr(p, "title", "") or "")
        url = str(getattr(p, "url", "") or "")
        html = ""
        try:
            html = str(p.html or "")[:4000]
        except Exception:
            html = ""
        blob = f"{title}\n{url}\n{html}".lower()
        markers = (
            "attention required",
            "just a moment",
            "cf-browser-verification",
            "cf-challenge",
            "cf-turnstile",
            "checking your browser",
            "enable javascript and cookies",
            "cloudflare",
            "blocked due to abusive traffic",
            "sorry, you have been blocked",
        )
        # real signup pages also load on cloudflare-backed domains; require strong signal
        strong = (
            "attention required" in blob
            or "just a moment" in blob
            or "cf-browser-verification" in blob
            or "checking your browser" in blob
            or "blocked due to abusive traffic" in blob
            or "sorry, you have been blocked" in blob
            or ("cloudflare" in title.lower() and "sign" not in title.lower())
        )
        return strong
    except Exception:
        return False


def wait_cloudflare_passthrough(timeout=45, log_callback=None, cancel_callback=None):
    """Wait for CF challenge page to clear (JS challenge may auto-pass)."""
    deadline = time.time() + timeout
    reported = False
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = None
        try:
            page = refresh_active_page()
        except Exception:
            page = _get_page()
        if page is None:
            sleep_with_cancel(1, cancel_callback)
            continue
        if not page_is_cloudflare_challenge(page):
            if reported and log_callback:
                log_callback("[*] Cloudflare 挑战已通过")
            return True
        if log_callback and not reported:
            meta = config.get("_last_proxy_exit") if isinstance(config, dict) else None
            if isinstance(meta, dict) and meta.get("exit_ip"):
                log_callback(
                    f"[!] 检测到 Cloudflare 拦截页（出口={meta.get('exit_ip')} "
                    f"{meta.get('exit_org') or ''}，不是入口网关），等待自动放行..."
                )
            else:
                log_callback("[!] 检测到 Cloudflare 拦截页，等待自动放行...")
            if sys.platform != "win32" and _linux_should_headless():
                log_callback(
                    "[!] 当前为无头浏览器，CF 通过率偏低；建议 Xvfb + GROK_REGISTER_HEADLESS=0"
                )
            reported = True
        # try click common verify buttons if present
        try:
            page.run_js(
                """
const btn = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a'))
  .find(n => /verify|继续|human|确认|i am human/i.test((n.innerText||n.value||'')));
if (btn) btn.click();
"""
            )
        except Exception:
            pass
        sleep_with_cancel(2, cancel_callback)
    page = _get_page()
    return (not page_is_cloudflare_challenge(page)) if page is not None else False


def refresh_cliproxy_and_restart_browser(log_callback=None):
    """Fetch a new Cliproxy IP / rotate SOCKS5 live node and restart browser with it."""
    mode = str(config.get("proxy_mode", "") or "").strip().lower()
    if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
        try:
            apply_resolved_proxy_to_config(log_callback=log_callback, fetch_live=True)
        except Exception as exc:
            if log_callback:
                log_callback(f"[!] 更换 Cliproxy IP 失败: {exc}")
    elif is_socks5_list_mode():
        # 18r44d: interstitial / proxy error page -> cooldown + pick LIVE then restart
        try:
            mark_proxy_bad(get_configured_proxy(), log_callback=log_callback)
        except Exception as exc:
            if log_callback:
                log_callback(f"[!] SOCKS5 切换失败: {exc}")
        try:
            ensure_live_proxy_before_browser(log_callback=log_callback)
        except Exception as exc:
            if log_callback:
                log_callback(f"[!] SOCKS5 存活预检失败: {exc}")
    else:
        try:
            cur = get_configured_proxy()
            if cur:
                mark_proxy_cooldown(cur, reason="refresh_browser_proxy", log_callback=log_callback)
        except Exception:
            pass
    restart_browser(log_callback=log_callback, use_proxy=True)


def open_signup_page(log_callback=None, cancel_callback=None):
    st = _tls_browser_state()
    browser = st.browser
    page = st.page
    raise_if_cancelled(cancel_callback)
    # 18r44a: wipe previous account session before navigating signup
    try:
        if page is not None:
            _clear_xai_session_cookies(page=page, log_callback=log_callback)
    except Exception:
        pass
    if browser is None:
        start_browser(log_callback=log_callback)
        if log_callback:
            log_callback("[*] 浏览器已启动")

    def _open_with_current_browser():
        page = _get_page()
        browser = _get_browser()
        st = _tls_browser_state()
        try:
            page = browser.get_tab(0)
            st = _tls_browser_state()
            st.page = page
            if browser is not None:
                st.browser = browser
            _sync_module_browser_aliases()
            page.get(SIGNUP_URL)
        except Exception as e:
            if log_callback:
                log_callback(f"[Debug] 打开URL异常: {e}")
            # Web 停止会先关闭全局 browser；此时绝不能继续 browser.new_tab。
            raise_if_cancelled(cancel_callback)
            current_browser = browser
            if current_browser is None:
                raise RegistrationCancelled("浏览器已按停止请求关闭")
            page = current_browser.new_tab(SIGNUP_URL)
            st = _tls_browser_state()
            st.page = page
            if browser is not None:
                st.browser = browser
            _sync_module_browser_aliases()
        try:
            page.wait.doc_loaded()
        except Exception:
            pass
        sleep_with_cancel(2, cancel_callback)

    max_proxy_rounds = 4
    last_err = None
    for round_i in range(1, max_proxy_rounds + 1):
        raise_if_cancelled(cancel_callback)
        try:
            _open_with_current_browser()
        except RegistrationCancelled:
            raise
        except Exception as e:
            last_err = e
            if _tls_browser_state().browser_started_with_proxy and get_configured_proxy():
                if log_callback:
                    log_callback(f"[!] 浏览器代理访问注册页失败，换 IP/重试 ({round_i}/{max_proxy_rounds}): {e}")
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                continue
            raise

        # 18r35e: ALWAYS refresh TLS page before error detection (stale handle missed Chromium interstitial)
        try:
            page = _get_page() or page
        except Exception:
            pass
        try:
            if page_has_proxy_error(page):
                if log_callback:
                    log_callback("[!] 浏览器页面显示代理/网络错误页(Chromium interstitial)，更换代理重试")
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                continue
        except Exception as _pe:
            if log_callback:
                try:
                    log_callback(f"[!] page_has_proxy_error check failed: {_pe}")
                except Exception:
                    pass

        # 18r30b: after proxy rotate / multi-thread, page handle may be dead — refresh TLS page.
        try:
            page = _get_page() or page
        except Exception:
            pass
        try:
            cur_url = page.url if page is not None else ""
        except Exception as url_exc:
            last_err = url_exc
            if log_callback:
                log_callback(
                    f"[!] 读取注册页 URL 失败(页面断开?): {url_exc}；更换代理重试 ({round_i}/{max_proxy_rounds})"
                )
            try:
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
            except Exception as re_exc:
                if log_callback:
                    log_callback(f"[!] restart browser after page disconnect: {re_exc}")
            continue

        if log_callback:
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
        try:
            page = _get_page() or page
        except Exception:
            pass
        if page_is_cloudflare_challenge(page):
            ok = wait_cloudflare_passthrough(
                timeout=50, log_callback=log_callback, cancel_callback=cancel_callback
            )
            if not ok:
                if log_callback:
                    log_callback(
                        f"[!] Cloudflare 仍拦截（第 {round_i}/{max_proxy_rounds} 次），更换代理 IP 重试"
                    )
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                continue

        try:
            click_email_signup_button(
                timeout=15,
                log_callback=log_callback,
                cancel_callback=cancel_callback,
            )
            return
        except Exception as e:
            last_err = e
            emsg = str(e)
            disconnected = (
                "PageDisconnected" in type(e).__name__
                or "连接已断开" in emsg
                or "disconnected" in emsg.lower()
            )
            # If still CF / button missing / page dead, rotate and retry
            try:
                still_cf = page_is_cloudflare_challenge(page)
            except Exception:
                still_cf = False
                disconnected = True
            if still_cf or page_is_tos_gate(page) or "未找到" in emsg or disconnected or "tos-gate" in emsg.lower():
                if log_callback:
                    log_callback(
                        f"[!] 注册页未就绪: {e}；更换代理重试 ({round_i}/{max_proxy_rounds})"
                        + (" page_disconnected=1" if disconnected else "")
                    )
                refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                continue
            raise

    # last resort: try direct once if proxy kept failing
    if get_configured_proxy():
        if log_callback:
            log_callback("[!] 代理多次失败，最后尝试直连打开注册页")
        restart_browser(log_callback=log_callback, use_proxy=False)
        _open_with_current_browser()
        wait_cloudflare_passthrough(
            timeout=40, log_callback=log_callback, cancel_callback=cancel_callback
        )
        click_email_signup_button(
            timeout=15, log_callback=log_callback, cancel_callback=cancel_callback
        )
        return

    if last_err:
        raise last_err
    raise Exception("打开注册页失败")


def has_profile_form(log_callback=None):
    refresh_active_page()
    try:
        return bool(
            page.run_js(
                """
const givenInput = document.querySelector('input[data-testid="givenName"], input[name="givenName"], input[autocomplete="given-name"]');
const familyInput = document.querySelector('input[data-testid="familyName"], input[name="familyName"], input[autocomplete="family-name"]');
const passwordInput = document.querySelector('input[data-testid="password"], input[name="password"], input[type="password"]');
return !!(givenInput && familyInput && passwordInput);
            """
            )
        )
    except Exception:
        return False




# 18r35c: serialize CreateEmail across workers to cut IP-level rate limit
import threading as _rl_threading
_CREATE_EMAIL_GATE = _rl_threading.Lock()
_CREATE_EMAIL_LAST_TS = 0.0
_CREATE_EMAIL_MIN_GAP_SEC = 4.0  # 18r35k: wider MT gap vs per-mailbox 验证码过多


def _wait_create_email_gate(log_callback=None):
    """Stagger CreateEmail submissions so many workers do not fire at once."""
    global _CREATE_EMAIL_LAST_TS
    import time as _t
    with _CREATE_EMAIL_GATE:
        now = _t.time()
        wait = float(_CREATE_EMAIL_MIN_GAP_SEC) - (now - float(_CREATE_EMAIL_LAST_TS or 0.0))
        if wait > 0:
            if log_callback:
                try:
                    log_callback(f"[*] CreateEmail gate wait {wait:.2f}s (anti rate-limit)")
                except Exception:
                    pass
            _t.sleep(wait)
        _CREATE_EMAIL_LAST_TS = _t.time()


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


def fill_email_and_submit(timeout=75, log_callback=None, cancel_callback=None):
    raise_if_cancelled(cancel_callback)
    email, dev_token = get_email_and_token(log_callback=log_callback)
    if not email or not dev_token:
        raise Exception("获取邮箱失败")
    if log_callback:
        log_callback(f"[+] 注册将使用邮箱: {email} | provider={get_email_provider()}")
    deadline = time.time() + timeout
    last_diag_time = 0
    last_reclick_time = 0
    last_snapshot = None
    last_hard_recover_time = 0
    hard_recover_count = 0
    not_ready_since = None
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = _get_page()
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.5, cancel_callback)
            continue

        try:
            filled = page.run_js(
            """
const email = arguments[0];
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
function textOf(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
        node.getAttribute('placeholder'),
        node.getAttribute('data-testid'),
        node.getAttribute('name'),
        node.getAttribute('id'),
        node.getAttribute('autocomplete'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
function describeInput(node) {
    return [
        `type=${node.getAttribute('type') || ''}`,
        `name=${node.getAttribute('name') || ''}`,
        `id=${node.getAttribute('id') || ''}`,
        `placeholder=${node.getAttribute('placeholder') || ''}`,
        `aria=${node.getAttribute('aria-label') || ''}`,
        `testid=${node.getAttribute('data-testid') || ''}`,
    ].join(' ').replace(/\\s+/g, ' ').trim().slice(0, 160);
}
function describeAction(node) {
    return textOf(node).slice(0, 120);
}
function emailCandidates() {
    const direct = Array.from(document.querySelectorAll('input[data-testid="email"], input[name="email"], input[type="email"], input[autocomplete="email"], input[placeholder*="mail" i], input[aria-label*="mail" i]'));
    const all = Array.from(document.querySelectorAll('input, textarea'));
    for (const node of all) {
        const type = (node.getAttribute('type') || '').toLowerCase();
        if (['hidden', 'submit', 'button', 'checkbox', 'radio', 'file', 'search'].includes(type)) continue;
        const meta = textOf(node).toLowerCase();
        if (meta.includes('email') || meta.includes('e-mail') || meta.includes('mail') || meta.includes('邮箱') || meta.includes('电子邮件')) {
            direct.push(node);
        }
    }
    return Array.from(new Set(direct));
}
const visibleInputs = Array.from(document.querySelectorAll('input, textarea'))
    .filter((node) => isVisible(node) && !node.disabled && !node.readOnly)
    .map(describeInput)
    .slice(0, 8);
const visibleActions = Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter((node) => isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true')
    .map(describeAction)
    .filter(Boolean)
    .slice(0, 10);
const input = emailCandidates().find((node) => isVisible(node) && !node.disabled && !node.readOnly) || null;
if (!input) {
    return {
        state: 'not-ready',
        url: location.href,
        title: document.title,
        inputs: visibleInputs,
        buttons: visibleActions,
    };
}
input.focus(); input.click();
const valueProto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
const valueSetter = Object.getOwnPropertyDescriptor(valueProto, 'value')?.set;
const tracker = input._valueTracker;
if (tracker) tracker.setValue('');
if (valueSetter) valueSetter.call(input, email); else input.value = email;
input.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, data: email, inputType: 'insertText' }));
input.dispatchEvent(new InputEvent('input', { bubbles: true, data: email, inputType: 'insertText' }));
input.dispatchEvent(new Event('change', { bubbles: true }));
const inputType = (input.getAttribute('type') || '').toLowerCase();
const isValid = inputType !== 'email' || input.checkValidity();
if ((input.value || '').trim() !== email || !isValid) {
    return {
        state: 'fill-failed',
        value: input.value || '',
        valid: isValid,
        input: describeInput(input),
        url: location.href,
    };
}
input.blur();
return {
    state: 'filled',
    input: describeInput(input),
    url: location.href,
};
            """,
            email,
        )
        except Exception as _fe_exc:
            em = str(_fe_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] fill_email page disconnected: {_fe_exc}")
                try:
                    refresh_active_page()
                except Exception:
                    try:
                        restart_browser(log_callback=log_callback)
                        open_signup_page(log_callback=log_callback, cancel_callback=cancel_callback)
                    except Exception:
                        pass
                sleep_with_cancel(0.8, cancel_callback)
                continue
            raise
        state = filled.get("state") if isinstance(filled, dict) else filled
        if isinstance(filled, dict):
            last_snapshot = filled
        if state != "not-ready":
            not_ready_since = None
        if state == "not-ready":
            now = time.time()
            if not_ready_since is None:
                not_ready_since = now
            # 18r29h: after ~12s still no email input, hard reload signup + re-click entry.
            # Under proxy, after 2 hard recovers still stuck, rotate proxy once.
            if (now - not_ready_since) >= 12 and (now - last_hard_recover_time) >= 14 and hard_recover_count < 3:
                hard_recover_count += 1
                last_hard_recover_time = now
                if log_callback:
                    log_callback(
                        f"[Debug] 邮箱输入框持续未出现 {now - not_ready_since:.0f}s，"
                        f"硬刷新注册页恢复 ({hard_recover_count}/3)"
                    )
                try:
                    if hard_recover_count >= 2 and _tls_browser_state().browser_started_with_proxy and get_configured_proxy():
                        if log_callback:
                            log_callback("[Debug] 代理下邮箱表单仍未出现，更换代理 IP 后重开注册页")
                        refresh_cliproxy_and_restart_browser(log_callback=log_callback)
                        raise_if_cancelled(cancel_callback)
                        open_signup_page(log_callback=log_callback, cancel_callback=cancel_callback)
                    else:
                        raise_if_cancelled(cancel_callback)
                        page.get(SIGNUP_URL)
                        try:
                            page.wait.doc_loaded()
                        except Exception:
                            pass
                        sleep_with_cancel(2.0, cancel_callback)
                        if page_is_cloudflare_challenge(page):
                            wait_cloudflare_passthrough(
                                timeout=40, log_callback=log_callback, cancel_callback=cancel_callback
                            )
                        try:
                            click_email_signup_button(
                                timeout=12,
                                log_callback=log_callback,
                                cancel_callback=cancel_callback,
                            )
                        except Exception as e:
                            if log_callback:
                                log_callback(f"[Debug] 硬刷新后重点邮箱入口失败: {e}")
                except RegistrationCancelled:
                    raise
                except Exception as e:
                    if log_callback:
                        log_callback(f"[Debug] 邮箱表单硬恢复异常: {e}")
                not_ready_since = now  # reset streak after recover attempt
                last_reclick_time = 0
                sleep_with_cancel(0.8, cancel_callback)
                continue
            if now - last_reclick_time >= 3:
                reclicked = page.run_js(r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
function nodeText(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
        node.getAttribute('href'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
function scoreEntry(node) {
    const compact = nodeText(node).replace(/\s+/g, '');
    const lower = compact.toLowerCase();
    if (compact.includes('使用邮箱注册')) return 100;
    if (lower.includes('signupwithemail')) return 95;
    if (lower.includes('continuewithemail')) return 90;
    if (lower.includes('email') && (lower.includes('sign') || lower.includes('continue') || lower.includes('use') || lower.includes('with'))) return 80;
    if (lower === 'email' || lower.includes('邮箱')) return 70;
    return 0;
}
const candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'))
    .filter((node) => isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true')
    .map((node) => ({ node, score: scoreEntry(node), text: nodeText(node) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);
if (!candidates.length) return false;
candidates[0].node.click();
return candidates[0].text || true;
                """)
                last_reclick_time = now
                if reclicked and log_callback:
                    detail = f": {reclicked}" if isinstance(reclicked, str) else ""
                    log_callback(f"[Debug] 邮箱输入框未出现，已再次触发邮箱注册入口{detail}")
            if log_callback and now - last_diag_time >= 5:
                last_diag_time = now
                inputs = " | ".join((filled or {}).get("inputs", [])[:6]) if isinstance(filled, dict) else ""
                buttons = " | ".join((filled or {}).get("buttons", [])[:8]) if isinstance(filled, dict) else ""
                url = (filled or {}).get("url", page.url if page else "") if isinstance(filled, dict) else (page.url if page else "")
                log_callback(f"[Debug] 等待邮箱输入框: url={url}; inputs={inputs or 'none'}; buttons={buttons or 'none'}")
            sleep_with_cancel(0.5, cancel_callback)
            continue
        if state != "filled":
            if log_callback:
                log_callback(f"[Debug] 邮箱输入框已出现，但写入失败: {filled}")
            sleep_with_cancel(0.5, cancel_callback)
            continue
        sleep_with_cancel(0.8, cancel_callback)
        _wait_create_email_gate(log_callback)  # 18r35c_gate_call
        clicked = page.run_js(
            r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
function textOf(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
        node.getAttribute('placeholder'),
        node.getAttribute('data-testid'),
        node.getAttribute('name'),
        node.getAttribute('id'),
        node.getAttribute('autocomplete'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
function emailCandidates() {
    const direct = Array.from(document.querySelectorAll('input[data-testid="email"], input[name="email"], input[type="email"], input[autocomplete="email"], input[placeholder*="mail" i], input[aria-label*="mail" i]'));
    const all = Array.from(document.querySelectorAll('input, textarea'));
    for (const node of all) {
        const type = (node.getAttribute('type') || '').toLowerCase();
        if (['hidden', 'submit', 'button', 'checkbox', 'radio', 'file', 'search'].includes(type)) continue;
        const meta = textOf(node).toLowerCase();
        if (meta.includes('email') || meta.includes('e-mail') || meta.includes('mail') || meta.includes('邮箱') || meta.includes('电子邮件')) {
            direct.push(node);
        }
    }
    return Array.from(new Set(direct));
}
const input = emailCandidates().find((node) => isVisible(node) && !node.disabled && !node.readOnly) || null;
if (!input || !(input.value || '').trim()) return false;
const inputType = (input.getAttribute('type') || '').toLowerCase();
if (inputType === 'email' && !input.checkValidity()) return false;
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]'))
    .filter((node) => isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true');
const submitButton = buttons.find((node) => {
    const text = textOf(node).replace(/\s+/g, '');
    const lower = text.toLowerCase();
    return (
        text === '注册' ||
        text.includes('注册') ||
        text.includes('继续') ||
        text.includes('下一步') ||
        text.includes('确认') ||
        lower.includes('signup') ||
        lower.includes('sign up') ||
        lower.includes('continue') ||
        lower.includes('next') ||
        lower.includes('createaccount') ||
        lower.includes('submit')
    );
});
if (submitButton) {
    submitButton.click();
    return textOf(submitButton) || true;
}
const form = input.closest('form');
if (form) {
    if (form.requestSubmit) form.requestSubmit();
    else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    return 'form-submit';
}
input.focus();
input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
return 'enter';
            """
        )
        if clicked:
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
        sleep_with_cancel(0.5, cancel_callback)
    if last_snapshot:
        inputs = " | ".join(last_snapshot.get("inputs", [])[:6])
        buttons = " | ".join(last_snapshot.get("buttons", [])[:8])
        url = last_snapshot.get("url", page.url if page else "")
        raise Exception(
            f"未找到邮箱输入框或注册按钮，最后页面: url={url}; inputs={inputs or 'none'}; buttons={buttons or 'none'}"
        )
    raise Exception("未找到邮箱输入框或注册按钮")


def fill_code_and_submit(email, dev_token, timeout=180, log_callback=None, cancel_callback=None):
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

            r"""
const nodes = Array.from(document.querySelectorAll('button, a, [role="button"]'));
const target = nodes.find((node) => {
  const t = (node.innerText || node.textContent || '').replace(/\s+/g, '').toLowerCase();
  return t.includes('重新发送') || t.includes('resend') || t.includes('再次发送');
});
if (target && !target.disabled) { target.click(); return true; }
return false;
            """
        )

    code = get_oai_code(
        dev_token,
        email,
        log_callback=log_callback,
        cancel_callback=cancel_callback,
        resend_callback=_resend_code,
    )
    if not code:
        raise Exception("获取验证码失败")
    clean_code = str(code).replace("-", "").strip()
    deadline = time.time() + timeout

    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = _get_page()
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.5, cancel_callback)
            continue

        try:
            filled = page.run_js(
            """
const code = String(arguments[0] || '').trim();
if (!code) return 'empty-code';

function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

function setInputValue(input, value) {
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    const tracker = input._valueTracker;
    if (tracker) tracker.setValue('');
    if (nativeSetter) nativeSetter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, data: value, inputType: 'insertText' }));
    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
}

const aggregate = Array.from(document.querySelectorAll(
  'input[data-input-otp=\"true\"], input[name=\"code\"], input[autocomplete=\"one-time-code\"], input[inputmode=\"numeric\"], input[inputmode=\"text\"]'
)).find((node) => isVisible(node) && !node.disabled && !node.readOnly && Number(node.maxLength || 6) > 1);

if (aggregate) {
    aggregate.focus();
    aggregate.click();
    setInputValue(aggregate, code);
    return String(aggregate.value || '').replace(/\\s+/g, '') ? 'filled-aggregate' : 'aggregate-failed';
}

const otpBoxes = Array.from(document.querySelectorAll('input')).filter((node) => {
    if (!isVisible(node) || node.disabled || node.readOnly) return false;
    const maxLength = Number(node.maxLength || 0);
    const ac = String(node.autocomplete || '').toLowerCase();
    return maxLength === 1 || ac === 'one-time-code';
});

if (otpBoxes.length >= code.length) {
    for (let i = 0; i < code.length; i += 1) {
        const ch = code[i] || '';
        const box = otpBoxes[i];
        box.focus();
        box.click();
        setInputValue(box, ch);
        box.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: ch }));
        box.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: ch }));
    }
    const merged = otpBoxes.slice(0, code.length).map((x) => String(x.value || '').trim()).join('');
    return merged.length ? 'filled-boxes' : 'boxes-failed';
}

return 'not-ready';
            """,
            clean_code,
        )
        except Exception as _fc_exc:
            em = str(_fc_exc)
            if (
                ("NoneType" in em and "run_js" in em)
                or "页面被刷新" in em
                or "PageDisconnected" in em
                or "与页面的连接已断开" in em
            ):
                if log_callback:
                    log_callback(f"[!] fill_code page disconnected: {_fc_exc}")
                try:
                    refresh_active_page()
                except Exception:
                    pass
                sleep_with_cancel(0.8, cancel_callback)
                continue
            raise

        if filled == "not-ready":
            sleep_with_cancel(0.5, cancel_callback)
            continue
        if "failed" in str(filled):
            if log_callback:
                log_callback(f"[Debug] 验证码填写失败: {filled}")
            sleep_with_cancel(0.5, cancel_callback)
            continue

        clicked = page.run_js(
            r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

const buttons = Array.from(document.querySelectorAll('button[type=\"submit\"], button')).filter((node) => {
    return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});

const btn = buttons.find((node) => {
    const t = (node.innerText || node.textContent || '').replace(/\\s+/g, '').toLowerCase();
    return (
        t.includes('确认邮箱') ||
        t.includes('继续') ||
        t.includes('下一步') ||
        t.includes('confirm') ||
        t.includes('continue') ||
        t.includes('next')
    );
});

if (!btn) return 'no-button';
btn.focus();
btn.click();
return 'clicked';
            """
        )

        if clicked == "clicked" or clicked == "no-button":
            if log_callback:
                log_callback(f"[*] 已填写验证码并提交: {code}")
            sleep_with_cancel(1.5, cancel_callback)
            return code

        sleep_with_cancel(0.5, cancel_callback)

    raise Exception("验证码已获取，但自动填写/提交失败")


def getTurnstileToken(log_callback=None, cancel_callback=None):
    """Solve page Turnstile; 18r42c fail-fast when widget iframe never appears."""
    page = _get_page()
    if page is None:
        raise Exception('浏览器 page 未就绪 (getTurnstileToken)')

    try:
        page.run_js(
            "try { if (window.turnstile && typeof turnstile.reset === 'function') turnstile.reset(); } catch(e) {}"
        )
    except Exception:
        pass

    # 18r42c: cap attempts; early-exit if no iframe/widget for many tries (SOCKS5/chromewebdata burn)
    max_attempts = 36
    no_widget_streak = 0
    # 18r29i: more attempts under slow SOCKS5 / CF widget lag
    for attempt in range(0, max_attempts):
        raise_if_cancelled(cancel_callback)
        has_iframe = False
        try:
            token = page.run_js(
                """
try {
  const byInput = String((document.querySelector('input[name="cf-turnstile-response"]') || {}).value || '').trim();
  if (byInput) return byInput;
  if (window.turnstile && typeof turnstile.getResponse === 'function') {
    return String(turnstile.getResponse() || '').trim();
  }
  return '';
} catch(e) { return ''; }
                """
            )
            token = str(token or "").strip()
            if len(token) >= 80:
                if log_callback:
                    log_callback(f"[*] Turnstile 已通过，token长度={len(token)}")
                return token

            challenge_input = page.ele("@name=cf-turnstile-response")
            if challenge_input:
                wrapper = challenge_input.parent()
                iframe = None
                try:
                    iframe = wrapper.shadow_root.ele("tag:iframe")
                except Exception:
                    iframe = None
                if iframe:
                    has_iframe = True
                    try:
                        iframe.run_js(
                            """
window.dtp = 1;
function getRandomInt(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
let sx = getRandomInt(800, 1200);
let sy = getRandomInt(400, 700);
Object.defineProperty(MouseEvent.prototype, 'screenX', { value: sx });
Object.defineProperty(MouseEvent.prototype, 'screenY', { value: sy });
                            """
                        )
                    except Exception:
                        pass
                    try:
                        body_sr = iframe.ele("tag:body").shadow_root
                        btn = body_sr.ele("tag:input")
                        if btn:
                            btn.click()
                    except Exception:
                        pass
            else:
                # 兜底：尝试触发页面上可见的 Turnstile 容器
                page.run_js(
                    """
const nodes = Array.from(document.querySelectorAll('div,span,iframe')).filter((n) => {
  const txt = (n.className || '') + ' ' + (n.id || '') + ' ' + (n.getAttribute?.('src') || '');
  return String(txt).toLowerCase().includes('turnstile');
});
if (nodes.length && typeof nodes[0].click === 'function') nodes[0].click();
                    """
                )
            # detect any challenges iframe on page (not only shadow)
            try:
                has_iframe = bool(
                    has_iframe
                    or page.run_js(
                        """
try {
  return !!(document.querySelector('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"], .cf-turnstile iframe, #cf-turnstile iframe'));
} catch (e) { return false; }
"""
                    )
                )
            except Exception:
                pass
        except Exception:
            pass

        if has_iframe:
            no_widget_streak = 0
        else:
            no_widget_streak += 1
            # 18r42c: widget never mounts (proxy/chrome-error) — fail fast instead of 36s+ burn
            if no_widget_streak >= 12:
                if log_callback:
                    try:
                        log_callback(
                            f"[Debug] Turnstile fail-fast: no widget iframe for {no_widget_streak} attempts"
                        )
                    except Exception:
                        pass
                raise Exception("Turnstile 获取 token 失败: widget not present (no iframe)")

        # 18r29i: periodic hard click / interact with turnstile widget
        if attempt % 5 == 4:
            try:
                page.run_js(
                    """
try {
  document.querySelectorAll('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]').forEach((f) => {
    try { f.click(); } catch(e) {}
  });
  document.querySelectorAll('[data-sitekey], .cf-turnstile, #cf-turnstile').forEach((n) => {
    try { n.click(); } catch(e) {}
    try { n.dispatchEvent(new MouseEvent('click', {bubbles:true})); } catch(e) {}
  });
} catch(e) {}
                    """
                )
            except Exception:
                pass
            if log_callback and attempt % 10 == 4:
                try:
                    log_callback(f"[Debug] Turnstile hard-click pass attempt={attempt+1}/{max_attempts}")
                except Exception:
                    pass
        sleep_with_cancel(1, cancel_callback)

    raise Exception("Turnstile 获取 token 失败")


def build_profile():
    given_name_pool = [
        "Neo", "Ethan", "Liam", "Noah", "Lucas", "Mason", "Ryan", "Leo",
        "Owen", "Aiden", "Elio", "Aron", "Ivan", "Nolan", "Evan", "Kai",
        "Caleb", "Adam", "Ezra", "Miles", "Logan", "Carter", "Hunter", "Jason",
        "Brian", "Dylan", "Alex", "Colin", "Blake", "Gavin", "Henry", "Julian",
        "Kevin", "Louis", "Marcus", "Nathan", "Oscar", "Peter", "Quinn", "Robin",
        "Simon", "Tristan", "Victor", "Wesley", "Xavier", "Yuri", "Zane", "Felix",
        "Aaron", "Damian",
    ]
    family_name_pool = [
        "Lin", "Wang", "Zhao", "Liu", "Chen", "Zhang", "Xu", "Sun",
        "Guo", "He", "Yang", "Wu", "Zhou", "Tang", "Qin", "Shi",
        "Fang", "Peng", "Cao", "Deng", "Fan", "Fu", "Gao", "Han",
        "Hu", "Jiang", "Kong", "Lu", "Ma", "Nie", "Pan", "Qiao",
        "Ren", "Shao", "Tian", "Xie", "Yan", "Yao", "Yu", "Zeng",
        "Bai", "Duan", "Hou", "Jin", "Kang", "Luo", "Mao", "Song",
        "Wei", "Xiong",
    ]
    given_name = random.choice(given_name_pool)
    family_name = random.choice(family_name_pool)
    password = "N" + secrets.token_hex(4) + "!a7#" + secrets.token_urlsafe(6)
    return given_name, family_name, password


def fill_profile_and_submit(timeout=210, log_callback=None, cancel_callback=None):
    given_name, family_name, password = build_profile()
    deadline = time.time() + timeout
    form_filled_once = False
    wait_cf_since = None
    last_cf_retry_at = 0.0
    cf_retry_fails = 0
    cf_proxy_rotated = False

    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        page = _get_page()
        if page is None:
            try:
                page = refresh_active_page()
            except Exception:
                page = None
        if page is None:
            sleep_with_cancel(0.5, cancel_callback)
            continue

        if not form_filled_once:
            try:
                filled = page.run_js(
                """
const givenName = arguments[0];
const familyName = arguments[1];
const password = arguments[2];

function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

function pickInput(selector) {
    return Array.from(document.querySelectorAll(selector)).find((node) => {
        return isVisible(node) && !node.disabled && !node.readOnly;
    }) || null;
}

function setInputValue(input, value) {
    if (!input) return false;
    input.focus();
    input.click();
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    const tracker = input._valueTracker;
    if (tracker) tracker.setValue('');
    if (nativeSetter) nativeSetter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, data: value, inputType: 'insertText' }));
    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.blur();
    return String(input.value || '').trim() === String(value || '').trim();
}

const givenInput = pickInput('input[data-testid="givenName"], input[name="givenName"], input[autocomplete="given-name"], input[aria-label*="名"]');
const familyInput = pickInput('input[data-testid="familyName"], input[name="familyName"], input[autocomplete="family-name"], input[aria-label*="姓"]');
const passwordInput = pickInput('input[data-testid="password"], input[name="password"], input[type="password"], input[autocomplete="new-password"]');

if (!givenInput || !familyInput || !passwordInput) return 'not-ready';

const ok1 = setInputValue(givenInput, givenName);
const ok2 = setInputValue(familyInput, familyName);
const ok3 = setInputValue(passwordInput, password);

if (!ok1 || !ok2 || !ok3) return 'fill-failed';

const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]')).filter((node) => {
    return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});
const submitBtn = buttons.find((node) => {
    const t = (node.innerText || node.textContent || '').replace(/\\s+/g, '').toLowerCase();
    return t.includes('完成注册') || t.includes('创建账户') || t.includes('signup') || t.includes('createaccount');
});

// 必须等待 Cloudflare 校验通过后再提交
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
const cfPresent = !!cfInput
  || !!document.querySelector('iframe[src*="turnstile"], div.cf-turnstile, [data-sitekey], script[src*="turnstile"]');
if (cfPresent) {
    const token = String((cfInput && cfInput.value) || '').trim();
    const solvedByToken = token.length >= 80;
    if (!solvedByToken) return 'wait-cloudflare:' + token.length;
}

if (submitBtn) {
    return 'ready-to-submit';
}
return 'filled-no-submit';
            """,
                given_name,
                family_name,
                password,
            )
            except Exception as _fp_exc:
                em = str(_fp_exc)
                if (
                    ("NoneType" in em and "run_js" in em)
                    or "页面被刷新" in em
                    or "PageDisconnected" in em
                    or "与页面的连接已断开" in em
                ):
                    if log_callback:
                        log_callback(f"[!] fill_profile page disconnected: {_fp_exc}")
                    try:
                        refresh_active_page()
                    except Exception:
                        pass
                    sleep_with_cancel(0.8, cancel_callback)
                    continue
                raise

            if isinstance(filled, str) and filled.startswith("wait-cloudflare"):
                form_filled_once = True
                if log_callback:
                    token_len = filled.split(":", 1)[1] if ":" in filled else "0"
                    log_callback(f"[*] 资料已填写，等待 Cloudflare 人机验证通过... 当前token长度={token_len}")
                if token_len == "0":
                    pause_seconds = random.uniform(1, 3)
                    if log_callback:
                        log_callback(f"[*] Cloudflare token 为空，暂停 {pause_seconds:.1f}s 后继续检测")
                    sleep_with_cancel(pause_seconds, cancel_callback)
                now = time.time()
                if wait_cf_since is None:
                    wait_cf_since = now
                # 卡住后自动二次复用 Turnstile 组件
                if now - wait_cf_since >= 12 and now - last_cf_retry_at >= 8:
                    if log_callback:
                        log_callback("[*] Cloudflare 验证卡住，开始二次复用 Turnstile...")
                    try:
                        token = getTurnstileToken(log_callback=log_callback, cancel_callback=cancel_callback)
                        if token:
                            synced = page.run_js(
                                """
const token = String(arguments[0] || '').trim();
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!cfInput || !token) return false;
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) nativeSetter.call(cfInput, token);
else cfInput.value = token;
cfInput.dispatchEvent(new Event('input', { bubbles: true }));
cfInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(cfInput.value || '').trim().length;
                                """,
                                token,
                            )
                            if log_callback:
                                log_callback(f"[*] Turnstile 二次复用完成，回填长度={synced}")
                        # 18r24: late CF token must still get a submit window
                        try:
                            deadline = max(deadline, time.time() + 75)
                        except Exception:
                            pass
                        if log_callback:
                            try:
                                log_callback("[*] profile submit window extended +75s after late Turnstile")
                            except Exception:
                                pass
                    except Exception as cf_exc:
                        if log_callback:
                            log_callback(f"[Debug] Turnstile 二次复用失败: {cf_exc}")
                    last_cf_retry_at = now
                sleep_with_cancel(0.8, cancel_callback)
                continue

            if filled in ("ready-to-submit", "filled-no-submit"):
                form_filled_once = True
            elif filled == "fill-failed" and log_callback:
                log_callback("[Debug] 资料输入失败，重试中...")
                sleep_with_cancel(0.5, cancel_callback)
                continue
            elif filled == "not-ready":
                sleep_with_cancel(0.5, cancel_callback)
                continue

        submit_state = page.run_js(
            r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}

const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
const cfPresent = !!cfInput
  || !!document.querySelector('iframe[src*="turnstile"], div.cf-turnstile, [data-sitekey], script[src*="turnstile"]');
if (cfPresent) {
    const token = String((cfInput && cfInput.value) || '').trim();
    const solvedByToken = token.length >= 80;
    if (!solvedByToken) return 'wait-cloudflare:' + token.length;
}

function buttonText(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('value'),
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]')).filter((node) => {
    return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});
const submitBtn = buttons.find((node) => {
    const t = buttonText(node).replace(/\s+/g, '').toLowerCase();
    return t.includes('完成注册') || t.includes('创建账户') || t.includes('signup') || t.includes('createaccount');
});
if (!submitBtn) {
    const visibleTexts = buttons.map(buttonText).filter(Boolean).slice(0, 8).join(' | ');
    return 'no-submit-button:' + visibleTexts;
}
submitBtn.focus();
submitBtn.click();
return 'submitted';
            """
        )

        if isinstance(submit_state, str) and submit_state.startswith("wait-cloudflare"):
            if log_callback:
                token_len = submit_state.split(":", 1)[1] if ":" in submit_state else "0"
                log_callback(f"[*] 等待 Cloudflare 人机验证通过后再提交... 当前token长度={token_len}")
            now = time.time()
            if wait_cf_since is None:
                wait_cf_since = now
            if now - wait_cf_since >= 12 and now - last_cf_retry_at >= 8:
                if log_callback:
                    log_callback("[*] 提交前仍卡住，自动再次复用 Turnstile...")
                try:
                    token = getTurnstileToken(log_callback=log_callback, cancel_callback=cancel_callback)
                    if token:
                        synced = page.run_js(
                            """
const token = String(arguments[0] || '').trim();
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!cfInput || !token) return false;
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) nativeSetter.call(cfInput, token);
else cfInput.value = token;
cfInput.dispatchEvent(new Event('input', { bubbles: true }));
cfInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(cfInput.value || '').trim().length;
                            """,
                            token,
                        )
                        if log_callback:
                            log_callback(f"[*] Turnstile 二次复用完成，回填长度={synced}")
                        cf_retry_fails = 0
                        # 18r24: late CF token must still get a submit window
                        try:
                            deadline = max(deadline, time.time() + 75)
                        except Exception:
                            pass
                        if log_callback:
                            try:
                                log_callback("[*] profile submit window extended +75s after late Turnstile")
                            except Exception:
                                pass
                except Exception as cf_exc:
                    cf_retry_fails += 1
                    if log_callback:
                        log_callback(f"[Debug] Turnstile 二次复用失败({cf_retry_fails}): {cf_exc}")
                    # 18r29i: under proxy, one soft IP rotate + stay on page if possible
                    if (
                        cf_retry_fails >= 2
                        and not cf_proxy_rotated
                        and _tls_browser_state().browser_started_with_proxy
                        and get_configured_proxy()
                    ):
                        cf_proxy_rotated = True
                        if log_callback:
                            log_callback("[Debug] Turnstile 连续失败，尝试更换代理 IP 并重置 Turnstile widget")
                        try:
                            # do not full restart browser mid-profile (loses form);
                            # soft reset widget only + hope next widget load uses new IP via bridge
                            page.run_js(
                                "try { if (window.turnstile && turnstile.reset) turnstile.reset(); } catch(e) {}"
                            )
                        except Exception:
                            pass
                        try:
                            # rotate local auth bridge IP by refreshing socks selection if available
                            if "rotate_proxy_bridge" in globals() or "refresh_cliproxy" in globals():
                                pass
                            refresh_cliproxy = globals().get("refresh_cliproxy")
                            if callable(refresh_cliproxy):
                                refresh_cliproxy(log_callback=log_callback)
                        except Exception as pe:
                            if log_callback:
                                log_callback(f"[Debug] proxy soft rotate skip: {pe}")
                last_cf_retry_at = now
            sleep_with_cancel(0.8, cancel_callback)
            continue

        if submit_state == "submitted":
            if log_callback:
                log_callback(f"[*] 已填写注册资料并提交: {given_name} {family_name}")
            return {"given_name": given_name, "family_name": family_name, "password": password}
        wait_cf_since = None
        if isinstance(submit_state, str) and submit_state.startswith("no-submit-button") and log_callback:
            visible_buttons = submit_state.split(":", 1)[1] if ":" in submit_state else ""
            suffix = f" 可见按钮: {visible_buttons}" if visible_buttons else ""
            log_callback(f"[Debug] 未找到提交按钮，继续等待页面稳定...{suffix}")

        sleep_with_cancel(0.5, cancel_callback)

    raise Exception("最终注册页资料填写失败")



def _iter_page_cookie_items(page):
    """Yield (name, value) from DrissionPage cookie list/dict/objects."""
    if page is None:
        return
    try:
        cookies = page.cookies(all_domains=True, all_info=True) or []
    except Exception:
        try:
            cookies = page.cookies() or []
        except Exception:
            cookies = []
    for item in cookies:
        if isinstance(item, dict):
            name = str(item.get("name", "") or "").strip()
            value = str(item.get("value", "") or "").strip()
        else:
            name = str(getattr(item, "name", "") or "").strip()
            value = str(getattr(item, "value", "") or "").strip()
        if name:
            yield name, value


def _collect_sso_cookie_values(page):
    """Return set of current sso / sso-rw cookie values on page."""
    out = set()
    for name, value in _iter_page_cookie_items(page):
        if name in ("sso", "sso-rw") and value:
            out.add(value)
            try:
                nv = _normalize_sso_token(value)
                if nv:
                    out.add(nv)
            except Exception:
                pass
    return out


def _clear_xai_session_cookies(page=None, log_callback=None):
    """Drop xAI auth cookies so the next signup cannot inherit previous SSO."""
    p = page
    if p is None:
        try:
            p = _get_page()
        except Exception:
            p = None
    if p is None:
        return 0
    cleared = 0
    try:
        p.run_js(
            r"""
(function(){
  const names = ['sso','sso-rw','sso_token','last-logged-in-with','logged_in','__Host-sso'];
  const domains = ['.x.ai','x.ai','.accounts.x.ai','accounts.x.ai','.grok.com','grok.com', location.hostname];
  const paths = ['/','/sign-up','/sign-in'];
  for (const n of names) {
    document.cookie = n + '=; Max-Age=0; path=/';
    for (const d of domains) {
      for (const path of paths) {
        document.cookie = n + '=; Max-Age=0; path=' + path + '; domain=' + d;
      }
    }
  }
  try { localStorage.clear(); sessionStorage.clear(); } catch(e) {}
  return true;
})()
"""
        )
        cleared += 1
    except Exception:
        pass
    try:
        setter = getattr(p, "set", None)
        cookies_api = getattr(setter, "cookies", None) if setter is not None else None
        if cookies_api is not None:
            clear_fn = getattr(cookies_api, "clear", None)
            if callable(clear_fn):
                clear_fn()
                cleared += 1
            else:
                rem = getattr(cookies_api, "remove", None) or getattr(cookies_api, "delete", None)
                if callable(rem):
                    for name, _value in list(_iter_page_cookie_items(p)):
                        if name in ("sso", "sso-rw", "sso_token", "last-logged-in-with", "logged_in"):
                            try:
                                rem(name)
                                cleared += 1
                            except Exception:
                                try:
                                    rem(name=name)
                                    cleared += 1
                                except Exception:
                                    pass
    except Exception:
        pass
    if log_callback:
        try:
            left = len(_collect_sso_cookie_values(p))
            log_callback(f"[*] 已清理 xAI session cookies (ops={cleared}, sso_left={left})")
        except Exception:
            pass
    return cleared


def wait_for_sso_cookie(timeout=120, log_callback=None, cancel_callback=None):
    deadline = time.time() + timeout
    last_seen_names = set()
    last_submit_retry = 0.0
    last_cf_retry_at = 0.0
    last_signin_nudge_at = 0.0
    signin_nudge_count = 0
    first_pure_signin_at = None
    final_no_submit_state = ""
    final_no_submit_since = None
    final_no_submit_timeout = 25
    # 18r44a/c: ignore SSO cookies already present + already-claimed session_ids
    baseline_sso = set()
    baseline_sids = set()
    try:
        baseline_sso = set(_collect_sso_cookie_values(_get_page()))
        for _bv in list(baseline_sso):
            _bs = _extract_sso_session_id(_bv)
            if _bs:
                baseline_sids.add(_bs)
    except Exception:
        baseline_sso = set()
        baseline_sids = set()
    try:
        with _SSO_SESSION_CLAIM_LOCK:
            baseline_sids |= set(_SSO_SESSION_CLAIMS.keys())
    except Exception:
        pass
    if (baseline_sso or baseline_sids) and log_callback:
        try:
            log_callback(
                f"[*] wait_for_sso: ignore baseline sso cookies n={len(baseline_sso)} "
                f"sids={len(baseline_sids)} (prevent same-worker account collision)"
            )
        except Exception:
            pass

    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        try:
            try:
                refresh_active_page()
            except Exception:
                pass
            page = _get_page()
            if page is None:
                sleep_with_cancel(1, cancel_callback)
                continue

            # 仍停留在“完成注册”页时，若 Cloudflare 已通过，周期性重试点击提交
            now = time.time()
            if now - last_submit_retry >= 2.5:
                retried = page.run_js(
                    r"""
function isVisible(node) {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}
const titleHit = !!Array.from(document.querySelectorAll('h1,h2,div,span')).find((el) => {
    const t = (el.textContent || '').replace(/\s+/g, '');
    const lower = t.toLowerCase();
    return t.includes('完成注册') || lower.includes('completeyoursignup') || lower.includes('completesignup');
});
if (!titleHit) return 'not-final-page';

const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
const cfPresent = !!cfInput
  || !!document.querySelector('iframe[src*="turnstile"], div.cf-turnstile, [data-sitekey], script[src*="turnstile"]');
if (cfPresent) {
    const token = String((cfInput && cfInput.value) || '').trim();
    const solved = token.length >= 80;
    if (!solved) return 'final-page-wait-cf:' + token.length;
}

function buttonText(node) {
    return [
        node.innerText,
        node.textContent,
        node.getAttribute('value'),
        node.getAttribute('aria-label'),
        node.getAttribute('title'),
    ].filter(Boolean).join(' ').replace(/\\s+/g, ' ').trim();
}
const buttons = Array.from(document.querySelectorAll('button[type="submit"], button, [role="button"], input[type="submit"]')).filter((node) => {
    return isVisible(node) && !node.disabled && node.getAttribute('aria-disabled') !== 'true';
});
const submitBtn = buttons.find((node) => {
    const t = buttonText(node).replace(/\s+/g, '').toLowerCase();
    return t.includes('完成注册') || t.includes('创建账户') || t.includes('signup') || t.includes('createaccount');
});
if (!submitBtn) {
    const visibleTexts = buttons.map(buttonText).filter(Boolean).slice(0, 8).join(' | ');
    return 'final-page-no-submit:' + visibleTexts;
}
submitBtn.focus();
submitBtn.click();
return 'final-page-clicked-submit';
                    """
                )
                last_submit_retry = now
                if log_callback and (retried == "final-page-clicked-submit" or (isinstance(retried, str) and retried.startswith("final-page-no-submit"))):
                    log_callback(f"[Debug] 最终页状态: {retried}")
                if isinstance(retried, str) and retried.startswith("final-page-no-submit"):
                    if retried != final_no_submit_state:
                        final_no_submit_state = retried
                        final_no_submit_since = now
                    elif final_no_submit_since and now - final_no_submit_since >= final_no_submit_timeout:
                        raise AccountRetryNeeded(
                            f"最终注册页状态 {final_no_submit_timeout}s 未变化且未找到提交按钮，重试当前账号: {retried}"
                        )
                else:
                    final_no_submit_state = ""
                    final_no_submit_since = None
                if log_callback and isinstance(retried, str) and retried.startswith("final-page-wait-cf"):
                    token_len = retried.split(":", 1)[1] if ":" in retried else "0"
                    log_callback(f"[Debug] 最终页状态: final-page-wait-cf, token长度={token_len}")
                    if now - last_cf_retry_at >= 10:
                        if log_callback:
                            log_callback("[*] 最终页 Cloudflare 卡住，自动二次复用 Turnstile...")
                        try:
                            token = getTurnstileToken(log_callback=log_callback, cancel_callback=cancel_callback)
                            if token:
                                synced = page.run_js(
                                    """
const token = String(arguments[0] || '').trim();
const cfInput = document.querySelector('input[name="cf-turnstile-response"]');
if (!cfInput || !token) return false;
const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (nativeSetter) nativeSetter.call(cfInput, token);
else cfInput.value = token;
cfInput.dispatchEvent(new Event('input', { bubbles: true }));
cfInput.dispatchEvent(new Event('change', { bubbles: true }));
return String(cfInput.value || '').trim().length;
                                    """,
                                    token,
                                )
                                if log_callback:
                                    log_callback(f"[*] 最终页 Turnstile 二次复用完成，回填长度={synced}")
                        except Exception as cf_exc:
                            if log_callback:
                                log_callback(f"[Debug] 最终页 Turnstile 二次复用失败: {cf_exc}")
                        last_cf_retry_at = now

            cookies = page.cookies(all_domains=True, all_info=True) or []
            for item in cookies:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    value = str(item.get("value", "")).strip()
                else:
                    name = str(getattr(item, "name", "")).strip()
                    value = str(getattr(item, "value", "")).strip()

                if name:
                    last_seen_names.add(name)

                if name == "sso" and value:
                    norm = value
                    try:
                        norm = _normalize_sso_token(value) or value
                    except Exception:
                        norm = value
                    if value in baseline_sso or norm in baseline_sso or (_extract_sso_session_id(value) in baseline_sids if baseline_sids else False):
                        # stale cookie from previous account on this browser
                        continue
                    if log_callback:
                        try:
                            sid = ""
                            try:
                                import base64 as _b64
                                import json as _json
                                pl = (norm or value).split(".")[1]
                                pad = "=" * ((4 - len(pl) % 4) % 4)
                                sid = str(
                                    _json.loads(_b64.urlsafe_b64decode(pl + pad)).get("session_id") or ""
                                )[:13]
                            except Exception:
                                sid = ""
                            log_callback(f"[*] 已获取到 sso cookie (new session sid={sid}...)")
                        except Exception:
                            log_callback("[*] 已获取到 sso cookie")
                    return value

            # 18r26: SSO nudge only after pure signing-in; never leave active signup form
            now2 = time.time()
            if now2 - last_signin_nudge_at >= 10.0 and signin_nudge_count < 4:
                try:
                    probe = page.run_js(
                        r"""
const body = (document.body && document.body.innerText || '').replace(/\s+/g, '');
const url = String(location.href || '');
const hit = body.includes('您正在登录') || body.includes('正在登录')
  || /signing\s*in/i.test(body) || /youare(being)?signedin/i.test(body)
  || body.includes('登录中');
const hasLast = document.cookie.includes('last-logged-in-with');
const stillSignupForm = /sign-up/i.test(url) && (
  body.includes('完成注册') || body.includes('创建账户') || body.includes('名') && body.includes('姓') && body.includes('密码')
  || /completeyoursignup|createaccount|firstname|lastname/i.test(body)
);
const pureSigningIn = !!hit && !stillSignupForm;
return JSON.stringify({
  hit: !!hit,
  hasLast: !!hasLast,
  stillSignupForm: !!stillSignupForm,
  pureSigningIn: !!pureSigningIn,
  url: url.slice(0, 180),
  bodyHead: body.slice(0, 100)
});
"""
                    )
                    info = {}
                    try:
                        import json as _json
                        info = _json.loads(probe) if isinstance(probe, str) else {}
                    except Exception:
                        info = {}
                    if info.get("stillSignupForm"):
                        # 18r29j: form still visible after profile submit → re-click complete-signup
                        if now2 - last_signin_nudge_at >= 8.0:
                            if log_callback:
                                log_callback(
                                    f"[*] SSO hold on signup form -> reclick 完成注册 "
                                    f"url={info.get('url')} hit={info.get('hit')} body={info.get('bodyHead')}"
                                )
                            try:
                                clicked = page.run_js(
                                    r"""
function isVisible(node) {
  if (!node) return false;
  const style = window.getComputedStyle(node);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function textOf(node) {
  return [node.innerText, node.textContent, node.getAttribute('aria-label'), node.getAttribute('value')]
    .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
}
function score(node) {
  const t = textOf(node).replace(/\s+/g, '');
  const l = t.toLowerCase();
  if (t.includes('完成注册')) return 100;
  if (l.includes('createaccount') || l.includes('create account')) return 95;
  if (t.includes('创建账户') || t.includes('创建帐户')) return 90;
  if (t === '注册' || l === 'sign up' || l === 'signup') return 70;
  if (t.includes('继续') || l.includes('continue') || l.includes('submit')) return 50;
  return 0;
}
const nodes = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], a'))
  .filter(n => isVisible(n) && !n.disabled && n.getAttribute('aria-disabled') !== 'true')
  .map(n => ({n, s: score(n), t: textOf(n)}))
  .filter(x => x.s > 0)
  .sort((a,b) => b.s - a.s);
if (!nodes.length) return false;
// ensure CF field has something if present
try {
  const cf = document.querySelector('input[name="cf-turnstile-response"]');
  if (cf && String(cf.value||'').trim().length < 20 && window.turnstile && turnstile.getResponse) {
    const tok = String(turnstile.getResponse()||'').trim();
    if (tok) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      if (setter) setter.call(cf, tok); else cf.value = tok;
      cf.dispatchEvent(new Event('input', {bubbles:true}));
      cf.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }
} catch(e) {}
nodes[0].n.click();
return nodes[0].t || true;
                                    """
                                )
                                if log_callback:
                                    log_callback(f"[*] signup-form reclick result={clicked}")
                            except Exception as re_exc:
                                if log_callback:
                                    log_callback(f"[Debug] signup-form reclick fail: {re_exc}")
                            last_signin_nudge_at = now2
                    elif info.get("pureSigningIn") or info.get("hasLast") or ("last-logged-in-with" in last_seen_names):
                        # first pure-signing-in: dwell >= 18s before navigating away
                        dwell_ok = True
                        if signin_nudge_count == 0 and info.get("pureSigningIn") and not info.get("hasLast"):
                            if first_pure_signin_at is None:
                                first_pure_signin_at = now2
                            stayed = now2 - float(first_pure_signin_at)
                            if stayed < 18.0:
                                dwell_ok = False
                                if log_callback:
                                    log_callback(
                                        f"[*] SSO pure signing-in dwell {stayed:.1f}s/18s "
                                        f"url={info.get('url')}"
                                    )
                                last_signin_nudge_at = now2
                        if dwell_ok:
                            signin_nudge_count += 1
                            last_signin_nudge_at = now2
                            if log_callback:
                                log_callback(
                                    f"[*] SSO nudge {signin_nudge_count}/4 pure-signing-in "
                                    f"url={info.get('url')} hasLast={info.get('hasLast')} body={info.get('bodyHead')}"
                                )
                            for dest in (
                                "https://grok.com/",
                                "https://accounts.x.ai/",
                                "https://grok.com/chat",
                            ):
                                try:
                                    if log_callback:
                                        log_callback(f"[*] SSO nudge goto {dest}")
                                    page.get(dest)
                                    sleep_with_cancel(2.0, cancel_callback)
                                    refresh_active_page()
                                    cookies2 = page.cookies(all_domains=True, all_info=True) or []
                                    for item2 in cookies2:
                                        if isinstance(item2, dict):
                                            n2 = str(item2.get("name", "")).strip()
                                            v2 = str(item2.get("value", "")).strip()
                                        else:
                                            n2 = str(getattr(item2, "name", "")).strip()
                                            v2 = str(getattr(item2, "value", "")).strip()
                                        if n2:
                                            last_seen_names.add(n2)
                                        if n2 == "sso" and v2:
                                            if log_callback:
                                                log_callback(f"[*] 已获取到 sso cookie (nudge {dest})")
                                            return v2
                                except Exception as nav_exc:
                                    if log_callback:
                                        log_callback(f"[Debug] SSO nudge nav fail {dest}: {nav_exc}")
                except Exception as nudge_exc:
                    if log_callback:
                        log_callback(f"[Debug] SSO nudge probe fail: {nudge_exc}")

            # Do NOT AccountRetryNeeded-loop when page is pure signing-in (registration may already be done)
            if isinstance(final_no_submit_state, str) and (
                "您正在登录" in final_no_submit_state
                or "正在登录" in final_no_submit_state
                or "signing" in final_no_submit_state.lower()
            ):
                final_no_submit_since = None  # suppress retry-as-fail for this state
        except PageDisconnectedError:
            refresh_active_page()
        except AccountRetryNeeded:
            raise
        except Exception:
            pass

        sleep_with_cancel(1, cancel_callback)

    # Prefer pending_sso path signal when account likely created
    likely = "last-logged-in-with" in last_seen_names or signin_nudge_count > 0
    raise Exception(
        f"等待超时：未获取到 sso cookie。likely_registered={int(likely)} "
        f"nudges={signin_nudge_count} 已看到 cookies: {sorted(last_seen_names)}"
    )


class GrokRegisterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Grok 注册机")
        self.root.geometry("1120x900")
        self.root.minsize(960, 700)
        self.is_running = False
        self.batch_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.pending_sso_count = 0
        self.results = []
        self.stop_requested = False
        self.ui_queue = queue.Queue()
        self.accounts_output_file = ""
        self.setup_ui()

    def setup_ui(self):
        load_config()
        main_frame = tk.Frame(self.root, bg=UI_BG, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(3, weight=1)

        config_frame = tk.LabelFrame(
            main_frame,
            text="配置",
            bg=UI_PANEL_BG,
            fg=UI_FG,
            padx=10,
            pady=10,
            relief=tk.GROOVE,
            borderwidth=1,
        )
        config_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))
        config_frame.grid_columnconfigure(1, weight=1, minsize=260)
        config_frame.grid_columnconfigure(3, weight=1, minsize=260)

        def add_label(row, column, text):
            tk_label(config_frame, text=text, bg=UI_PANEL_BG).grid(
                row=row,
                column=column,
                sticky=tk.W,
                padx=(0, 6),
                pady=3,
            )

        def add_field(widget, row, column, columnspan=1, sticky=tk.EW):
            widget.grid(
                row=row,
                column=column,
                columnspan=columnspan,
                sticky=sticky,
                padx=(0, 14),
                pady=3,
            )

        add_label(0, 0, "邮箱服务商:")
        self.email_provider_var = tk.StringVar(value=config.get("email_provider", "duckmail"))
        self.email_provider_combo = tk_option_menu(config_frame, self.email_provider_var, ["duckmail", "yyds", "cloudflare", "outlook", "aol", "tempmail_io", "linshiyouxiang", "boomlify", "tempmail_org", "mailtm", "tempmail_lol", "tempmail_plus"], width=16)
        add_field(self.email_provider_combo, 0, 1, sticky=tk.W)

        add_label(0, 2, "注册数量:")
        self.count_var = tk.StringVar(value=str(config.get("register_count", 1)))
        self.count_spinbox = tk.Spinbox(
            config_frame,
            from_=1,
            to=2500,
            width=8,
            textvariable=self.count_var,
            bg=UI_ENTRY_BG,
            fg=UI_FG,
            insertbackground=UI_FG,
            buttonbackground=UI_BUTTON_BG,
            disabledbackground="#2f2f2f",
            disabledforeground=UI_MUTED_FG,
            relief=tk.SOLID,
        )
        add_field(self.count_spinbox, 0, 3, sticky=tk.W)

        add_label(1, 0, "注册选项:")
        self.nsfw_var = tk.BooleanVar(value=config.get("enable_nsfw", True))
        self.nsfw_check = tk_checkbutton(config_frame, text="注册后开启 NSFW", variable=self.nsfw_var)
        add_field(self.nsfw_check, 1, 1, sticky=tk.W)

        add_label(1, 2, "代理（可选）:")
        self.proxy_var = tk.StringVar(value=config.get("proxy", ""))
        self.proxy_entry = tk_entry(config_frame, textvariable=self.proxy_var, width=34)
        add_field(self.proxy_entry, 1, 3)

        add_label(2, 0, "DuckMail API Key:")
        self.api_key_var = tk.StringVar(value=config.get("duckmail_api_key", ""))
        self.api_key_entry = tk_entry(config_frame, textvariable=self.api_key_var, width=34)
        add_field(self.api_key_entry, 2, 1)

        add_label(2, 2, "Cloudflare 鉴权模式:")
        self.cloudflare_auth_mode_var = tk.StringVar(value=config.get("cloudflare_auth_mode", "none"))
        self.cloudflare_auth_mode_combo = tk_option_menu(
            config_frame, self.cloudflare_auth_mode_var, ["query-key", "bearer", "x-api-key", "x-admin-auth", "none"], width=12
        )
        add_field(self.cloudflare_auth_mode_combo, 2, 3, sticky=tk.W)

        add_label(3, 0, "Cloudflare API Base:")
        self.cloudflare_api_base_var = tk.StringVar(value=config.get("cloudflare_api_base", ""))
        self.cloudflare_api_base_entry = tk_entry(config_frame, textvariable=self.cloudflare_api_base_var, width=72)
        add_field(self.cloudflare_api_base_entry, 3, 1, columnspan=3)

        add_label(4, 0, "Cloudflare API Key:")
        self.cloudflare_api_key_var = tk.StringVar(value=config.get("cloudflare_api_key", ""))
        self.cloudflare_api_key_entry = tk_entry(config_frame, textvariable=self.cloudflare_api_key_var, width=34)
        add_field(self.cloudflare_api_key_entry, 4, 1)

        add_label(4, 2, "CF 路径:")
        self.cloudflare_paths_var = tk.StringVar(
            value=",".join(
                [
                    config.get("cloudflare_path_domains", "/api/domains"),
                    config.get("cloudflare_path_accounts", "/api/new_address"),
                    config.get("cloudflare_path_token", "/api/token"),
                    config.get("cloudflare_path_messages", "/api/mails"),
                ]
            )
        )
        self.cloudflare_paths_entry = tk_entry(config_frame, textvariable=self.cloudflare_paths_var, width=34)
        add_field(self.cloudflare_paths_entry, 4, 3)

        add_label(5, 0, "号池本地入池:")
        self.grok2api_local_auto_var = tk.BooleanVar(value=bool(config.get("grok2api_auto_add_local", True)))
        self.grok2api_local_auto_check = tk_checkbutton(config_frame, variable=self.grok2api_local_auto_var)
        add_field(self.grok2api_local_auto_check, 5, 1, sticky=tk.W)

        add_label(5, 2, "号池名称:")
        self.grok2api_pool_name_var = tk.StringVar(value=str(config.get("grok2api_pool_name", "ssoBasic")))
        self.grok2api_pool_name_combo = tk_option_menu(
            config_frame, self.grok2api_pool_name_var, ["ssoBasic", "ssoSuper"], width=12
        )
        add_field(self.grok2api_pool_name_combo, 5, 3, sticky=tk.W)

        add_label(6, 0, "本地 token.json:")
        self.grok2api_local_file_var = tk.StringVar(value=str(config.get("grok2api_local_token_file", "")))
        self.grok2api_local_file_entry = tk_entry(config_frame, textvariable=self.grok2api_local_file_var, width=72)
        add_field(self.grok2api_local_file_entry, 6, 1, columnspan=3)

        add_label(7, 0, "号池远端入池:")
        self.grok2api_remote_auto_var = tk.BooleanVar(value=bool(config.get("grok2api_auto_add_remote", False)))
        self.grok2api_remote_auto_check = tk_checkbutton(config_frame, variable=self.grok2api_remote_auto_var)
        add_field(self.grok2api_remote_auto_check, 7, 1, sticky=tk.W)

        add_label(8, 0, "号池远端 Base:")
        self.grok2api_remote_base_var = tk.StringVar(value=str(config.get("grok2api_remote_base", "")))
        self.grok2api_remote_base_entry = tk_entry(config_frame, textvariable=self.grok2api_remote_base_var, width=72)
        add_field(self.grok2api_remote_base_entry, 8, 1, columnspan=3)

        add_label(9, 0, "号池远端 app_key:")
        self.grok2api_remote_key_var = tk.StringVar(value=str(config.get("grok2api_remote_app_key", "")))
        self.grok2api_remote_key_entry = tk_entry(config_frame, textvariable=self.grok2api_remote_key_var, width=72)
        add_field(self.grok2api_remote_key_entry, 9, 1, columnspan=3)

        btn_frame = tk.Frame(main_frame, bg=UI_BG)
        btn_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 6))
        self.start_btn = tk_button(btn_frame, text="开始注册", command=self.start_registration)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk_button(btn_frame, text="停止", command=self.stop_registration, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.clear_btn = tk_button(btn_frame, text="清空日志", command=self.clear_log)
        self.clear_btn.pack(side=tk.LEFT, padx=5)

        status_frame = tk.Frame(main_frame, bg=UI_BG)
        status_frame.grid(row=2, column=0, sticky=tk.EW, pady=(0, 6))
        self.status_var = tk.StringVar(value="就绪")
        tk_label(status_frame, text="状态: ").pack(side=tk.LEFT)
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, bg=UI_BG, fg="green")
        self.status_label.pack(side=tk.LEFT)
        self.stats_var = tk.StringVar(value="成功: 0 | 失败: 0")
        tk.Label(status_frame, textvariable=self.stats_var, bg=UI_BG, fg=UI_FG).pack(side=tk.RIGHT)
        log_frame = tk.LabelFrame(
            main_frame,
            text="日志",
            bg=UI_PANEL_BG,
            fg=UI_FG,
            padx=5,
            pady=5,
            relief=tk.GROOVE,
            borderwidth=1,
        )
        log_frame.grid(row=3, column=0, sticky=tk.NSEW)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=18,
            width=60,
            bg="#111111",
            fg="#f5f5f5",
            insertbackground="#f5f5f5",
            selectbackground="#345a8a",
            selectforeground="#ffffff",
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#555555",
        )
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        self.log("[*] GUI 已就绪，配置已加载")
        self.log(f"[*] 当前邮箱服务商: {self.email_provider_var.get()} | 注册数量: {self.count_var.get()}")

    def log(self, message):
        timestamp = now_beijing("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        print(line, flush=True)
        self.log_text.insert(tk.END, f"{line}\n")
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def update_stats(self):
        self.stats_var.set(f"成功: {self.success_count} | 失败: {self.fail_count}")

    def _set_running_ui(self, running):
        self.is_running = running
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.status_var.set("运行中..." if running else "就绪")
        self.status_label.config(foreground="blue" if running else "green")

    def should_stop(self):
        return self.stop_requested or not self.is_running

    def start_registration(self):
        if self.is_running:
            self.log("[!] 当前已有任务在运行")
            return

        config["email_provider"] = self.email_provider_var.get().strip() or "duckmail"
        config["enable_nsfw"] = bool(self.nsfw_var.get())
        config["proxy"] = self.proxy_var.get().strip()
        config["duckmail_api_key"] = self.api_key_var.get().strip()
        config["cloudflare_api_base"] = self.cloudflare_api_base_var.get().strip()
        config["cloudflare_api_key"] = self.cloudflare_api_key_var.get().strip()
        config["cloudflare_auth_mode"] = self.cloudflare_auth_mode_var.get().strip() or "none"
        config["grok2api_auto_add_local"] = bool(self.grok2api_local_auto_var.get())
        config["grok2api_local_token_file"] = self.grok2api_local_file_var.get().strip()
        config["grok2api_pool_name"] = self.grok2api_pool_name_var.get().strip() or "ssoBasic"
        config["grok2api_auto_add_remote"] = bool(self.grok2api_remote_auto_var.get())
        config["grok2api_remote_base"] = self.grok2api_remote_base_var.get().strip()
        config["grok2api_remote_app_key"] = self.grok2api_remote_key_var.get().strip()
        raw_paths = [x.strip() for x in self.cloudflare_paths_var.get().split(",") if x.strip()]
        if len(raw_paths) >= 4:
            config["cloudflare_path_domains"] = raw_paths[0] if raw_paths[0].startswith("/") else ("/" + raw_paths[0])
            config["cloudflare_path_accounts"] = raw_paths[1] if raw_paths[1].startswith("/") else ("/" + raw_paths[1])
            config["cloudflare_path_token"] = raw_paths[2] if raw_paths[2].startswith("/") else ("/" + raw_paths[2])
            config["cloudflare_path_messages"] = raw_paths[3] if raw_paths[3].startswith("/") else ("/" + raw_paths[3])
        save_config()
        if config["email_provider"] == "cloudflare" and not config["cloudflare_api_base"]:
            self.log("[!] Cloudflare 模式需要先填写 Cloudflare API Base")
            return
        if str(config.get("email_provider") or "").strip().lower() in ("outlook", "microsoft", "hotmail", "ms_outlook"):
            has_text = bool(str(config.get("outlook_accounts") or "").strip())
            acc_file = str(config.get("outlook_accounts_file") or "outlook_accounts.txt").strip()
            if acc_file and not os.path.isabs(acc_file):
                acc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), acc_file)
            else:
                acc_path = acc_file
            has_file = bool(acc_path and os.path.isfile(acc_path) and os.path.getsize(acc_path) > 0)
            if not has_text and not has_file:
                self.log("[!] Outlook 模式需要配置 outlook_accounts 或 outlook_accounts.txt（email----password----totp）")

        if str(config.get("email_provider") or "").strip().lower() in ("aol", "aol_mail", "aol.com", "aim", "verizon_aol"):
            has_text = bool(str(config.get("aol_accounts") or "").strip())
            acc_file = str(config.get("aol_accounts_file") or "aol_accounts.txt").strip()
            path_ok = False
            try:
                from pathlib import Path as _P
                p = _P(acc_file) if _P(acc_file).is_absolute() else (_P(__file__).resolve().parent / acc_file)
                path_ok = p.is_file() and p.stat().st_size > 0
            except Exception:
                path_ok = False
            if not has_text and not path_ok:
                self.log("[!] AOL 模式需要配置 aol_accounts 或 aol_accounts.txt（email----password 或应用专用密码）")
                return

                return
        try:
            count = int(self.count_var.get())
        except Exception:
            self.log("[!] 注册数量无效")
            return
        config["register_count"] = count
        save_config()
        self.stop_requested = False
        self.success_count = 0
        self.fail_count = 0
        self.pending_sso_count = 0
        self.results = []
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.accounts_output_file = os.path.join(
            os.path.dirname(__file__), f"accounts_{now}.txt"
        )
        self.update_stats()
        self._set_running_ui(True)
        self.log(f"[*] 配置已保存，开始执行。目标数量: {count}")
        self.log(f"[*] 成功账号将实时保存到: {self.accounts_output_file}")
        threading.Thread(
            target=self.run_registration,
            args=(count,),
            daemon=True,
        ).start()

    def stop_registration(self):
        self.stop_requested = True
        self.log("[!] 用户停止注册")

    def run_registration(self, count):
        try:
            start_browser(log_callback=self.log)
            self.log("[*] 浏览器已启动")
            i = 0
            retry_count_for_slot = 0
            max_slot_retry = 3
            while i < count:
                if self.should_stop():
                    break
                self.log(f"--- 开始第 {i + 1}/{count} 个账号 ---")
                try:
                    email = ""
                    dev_token = ""
                    code = ""
                    mail_ok = False
                    max_mail_retry = 3
                    for mail_try in range(1, max_mail_retry + 1):
                        self.log(f"[*] 1. 打开注册页 (尝试 {mail_try}/{max_mail_retry})")
                        open_signup_page(
                            log_callback=self.log, cancel_callback=self.should_stop
                        )
                        self.log("[*] 2. 创建邮箱并提交")
                        try:
                            email, dev_token = fill_email_and_submit(
                                log_callback=self.log, cancel_callback=self.should_stop
                            )
                        except Exception as fill_exc:
                            # 18r35c serial: rate-limit on fill_email -> burn+retry other mailbox
                            fmsg = str(fill_exc)
                            if any(
                                k in fmsg
                                for k in ("create_email_rate_limited", "RATE_LIMITED", "验证码过多")
                            ):
                                _em = str(email or "")
                                try:
                                    import re as _re_rl
                                    _m = _re_rl.search(r"email=([^\s]+)", fmsg)
                                    if _m:
                                        _em = _m.group(1).strip()
                                except Exception:
                                    pass
                                if _em:
                                    try:
                                        from hybrid_register import handle_create_email_rate_limited
                                        handle_create_email_rate_limited(
                                            _em,
                                            "",
                                            log=self.log,
                                            source="browser_serial_fill_email",
                                            evidence=fmsg[:300],
                                            mail_token=str(dev_token or ""),
                                        )
                                    except Exception as _e:
                                        self.log(f"[!] serial rate-limit cleanup: {_e}")
                                self.log(
                                    f"[!] CreateEmail rate-limit -> switch mailbox "
                                    f"try={mail_try}/{max_mail_retry} email={_em}"
                                )
                                if mail_try < max_mail_retry:
                                    restart_browser(log_callback=self.log)
                                    sleep_with_cancel(1.5, self.should_stop)
                                    continue
                            raise
                        self.log(f"[*] 邮箱: {email}")
                        self.log(f"[Debug] 邮箱credential(jwt): {dev_token}")
                        try:
                            with open(
                                os.path.join(os.path.dirname(__file__), "mail_credentials.txt"),
                                "a",
                                encoding="utf-8",
                            ) as f:
                                f.write(f"{email}\t{dev_token}\n")
                        except Exception:
                            pass
                        self.log("[*] 3. 拉取验证码")
                        try:
                            code = fill_code_and_submit(
                                email,
                                dev_token,
                                log_callback=self.log,
                                cancel_callback=self.should_stop,
                            )
                            mail_ok = True
                            break
                        except Exception as mail_exc:
                            msg = str(mail_exc)
                            _mail_fail = any(
                                k in msg
                                for k in (
                                    "early_no_new_mail",
                                    "create_email_rate_limited",
                                    "验证码过多",
                                    "RATE_LIMITED",
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
                                    _pw = ""
                                    try:
                                        _g, _f, _pw = build_profile()
                                    except Exception:
                                        _pw = "N" + __import__("uuid").uuid4().hex[:8] + "!a7#TmpPw9x"
                                    burn_mailbox_to_pending(
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

                    if not mail_ok:
                        raise Exception("pending_sso:browser_code_fail email=multiple 验证码阶段失败，已达到最大重试次数")
                    self.log(f"[*] 验证码: {code}")
                    self.log("[*] 4. 填写资料")
                    profile = fill_profile_and_submit(
                        log_callback=self.log, cancel_callback=self.should_stop
                    )
                    self.log(f"[*] 资料已填: {profile.get('given_name')} {profile.get('family_name')}")
                    self.log("[*] 5. 等待 sso cookie")
                    try:
                        sso = wait_for_sso_cookie(
                            log_callback=self.log, cancel_callback=self.should_stop
                        )
                    except Exception as sso_exc:
                        msg = str(sso_exc)
                        if "未获取到 sso cookie" in msg or "sso cookie" in msg.lower():
                            # 18r23b: profile already submitted — queue pending_sso instead of hard-lose account
                            try:
                                from hybrid_register import burn_mailbox_to_pending
                                burn_mailbox_to_pending(
                                    email,
                                    str(profile.get("password") or ""),
                                    reason="browser_sso_timeout_likely_registered",
                                    log=self.log,
                                )
                                self.log(
                                    f"[!] browser no SSO after profile submit -> pending_sso "
                                    f"email={email} detail={msg}"
                                )
                            except Exception as pend_exc:
                                self.log(f"[!] pending_sso save fail email={email}: {pend_exc}")
                            raise Exception(f"pending_sso:browser_sso_timeout email={email} {msg}")
                        raise
                    ok_claim, sid, owner = claim_sso_session_or_reject(
                        sso, email=email, log_callback=self.log
                    )
                    if not ok_claim:
                        try:
                            from hybrid_register import burn_mailbox_to_pending
                            burn_mailbox_to_pending(
                                email,
                                str(profile.get("password") or ""),
                                reason="sso_session_collision",
                                log=self.log,
                            )
                        except Exception as pend_exc:
                            self.log(f"[!] collision pending save fail: {pend_exc}")
                        try:
                            _clear_xai_session_cookies(log_callback=self.log)
                            restart_browser(log_callback=self.log)
                        except Exception:
                            pass
                        raise Exception(
                            f"pending_sso:sso_session_collision email={email} "
                            f"sid={(sid or '')[:13]} owner={owner}"
                        )
                    self.results.append({"email": email, "sso": sso, "profile": profile})
                    try:
                        line = f"{email}----{profile.get('password','')}----{sso}\n"
                        with open(self.accounts_output_file, "a", encoding="utf-8") as f:
                            f.write(line)
                    except Exception as file_exc:
                        self.log(f"[Debug] 保存账号文件失败: {file_exc}")
                    # NSFW / g2a / CPA：默认后台，不阻塞下一号（功能仍执行）
                    schedule_post_registration(
                        email,
                        str(profile.get("password") or ""),
                        sso,
                        page=page,
                        log_callback=self.log,
                    )
                    self.success_count += 1
                    retry_count_for_slot = 0
                    i += 1
                    self.log(f"[+] 注册成功: {email}")
                    # 18r23: browser path must also burn mailbox out of pool (same as hybrid)
                    try:
                        from hybrid_register import mark_outlook_registered
                        mark_outlook_registered(email, self.log)
                    except Exception as _reg_exc:
                        try:
                            self.log(f"[!] browser mark_outlook_registered fail email={email}: {_reg_exc}")
                        except Exception:
                            pass
                    if (
                        self.success_count > 0
                        and self.success_count % MEMORY_CLEANUP_INTERVAL == 0
                        and i < count
                    ):
                        cleanup_runtime_memory(
                            log_callback=self.log,
                            reason=f"已成功 {self.success_count} 个账号，执行定期清理",
                        )
                except RegistrationCancelled:
                    self.log("[!] 注册被用户停止")
                    break
                except AccountRetryNeeded as exc:
                    retry_count_for_slot += 1
                    if retry_count_for_slot <= max_slot_retry:
                        self.log(
                            f"[!] 当前账号流程卡住，重试第 {retry_count_for_slot}/{max_slot_retry} 次: {exc}"
                        )
                    else:
                        self.fail_count += 1
                        self.log(
                            f"[-] 当前账号已达到最大重试次数，跳过: {exc}"
                        )
                        retry_count_for_slot = 0
                        i += 1
                except Exception as exc:
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
                finally:
                    self.update_stats()
                    if self.should_stop():
                        break
                    if browser is None:
                        start_browser(log_callback=self.log)
                    else:
                        restart_browser(log_callback=self.log)
                    sleep_with_cancel(1, self.should_stop)
        except Exception as exc:
            self.log(f"[!] 任务异常: {exc}")
        finally:
            # 等后台 g2a/CPA/NSFW 尽量跑完再关浏览器进程环境
            wait_post_success_queue(timeout=None, log_callback=self.log)
            stop_browser()
            self._set_running_ui(False)
            self.log("[*] 任务结束")


class CliStopController:
    def __init__(self, log_callback=None):
        self.stop_requested = False
        self._log = log_callback

    def should_stop(self):
        return self.stop_requested

    def stop(self, force_cleanup=True):
        self.stop_requested = True
        if force_cleanup:
            try:
                force_stop_registration(
                    log_callback=self._log,
                    reason="CliStopController.stop",
                )
            except Exception:
                try:
                    stop_browser(log_callback=self._log)
                except Exception:
                    pass


def cli_log(message):
    timestamp = now_beijing("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def run_registration_job(count, log_callback=None, controller=None, workers=None):
    """Non-interactive registration loop for CLI and Web.

    Returns dict: success, fail, accounts_file, stopped.
    workers: 18r30 multi-thread count; 18r30b: open_signup PageDisconnected auto-retry (default config workers/thread_count; 1=serial).
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

    success_count = 0
    fail_count = 0
    pending_sso_count = 0
    retry_count_for_slot = 0
    max_slot_retry = 3
    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_{now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] 任务启动，目标数量: {count}")
    log(f"[*] 注册模式: browser（全浏览器）")
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")
    mode = str(config.get("proxy_mode", "direct") or "direct")
    try:
        resolved_proxy = apply_resolved_proxy_to_config(log_callback=log, fetch_live=True)
    except Exception as proxy_exc:
        log(f"[!] 获取/解析代理失败: {proxy_exc}")
        raise
    if resolved_proxy:
        # mask password in log
        safe = resolved_proxy
        try:
            parsed = urllib.parse.urlparse(resolved_proxy)
            if parsed.password:
                safe = resolved_proxy.replace(":" + parsed.password + "@", ":****@")
        except Exception:
            pass
        log(f"[*] 代理模式: {mode} | {safe}")
        if mode in ("whitelist", "group", "proxy_group"):
            log(
                f"[*] 代理组: 国家={config.get('proxy_country','')} "
                f"分隔符={config.get('proxy_delimiter','-')!r} "
                f"时长={config.get('proxy_duration','120')}分钟"
            )
        if mode in ("cliproxy_white", "cliproxy", "white_api", "api"):
            log(
                f"[*] Cliproxy 白名单: region={config.get('proxy_country','US')} "
                f"time={config.get('proxy_duration','10')}m"
            )
    else:
        log(f"[*] 代理模式: {mode or 'direct'}（直连）")
    try:
        start_browser(log_callback=log)
        log("[*] 浏览器已启动")
        i = 0
        while i < count:
            if controller.should_stop():
                break
            log(f"--- 开始第 {i + 1}/{count} 个账号 ---")
            try:
                email = ""
                dev_token = ""
                code = ""
                mail_ok = False
                max_mail_retry = 3
                for mail_try in range(1, max_mail_retry + 1):
                    log(f"[*] 1. 打开注册页 (尝试 {mail_try}/{max_mail_retry})")
                    open_signup_page(
                        log_callback=log, cancel_callback=controller.should_stop
                    )
                    log("[*] 2. 创建邮箱并提交")
                    email, dev_token = fill_email_and_submit(
                        log_callback=log, cancel_callback=controller.should_stop
                    )
                    log(f"[*] 邮箱: {email}")
                    log(f"[Debug] 邮箱credential(jwt): {dev_token}")
                    try:
                        with open(
                            os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                "mail_credentials.txt",
                            ),
                            "a",
                            encoding="utf-8",
                        ) as f:
                            f.write(f"{email}\t{dev_token}\n")
                    except Exception:
                        pass
                    log("[*] 3. 拉取验证码")
                    try:
                        code = fill_code_and_submit(
                            email,
                            dev_token,
                            log_callback=log,
                            cancel_callback=controller.should_stop,
                        )
                        mail_ok = True
                        break
                    except Exception as mail_exc:
                        msg = str(mail_exc)
                        _mail_fail = any(
                            k in msg
                            for k in (
                                "early_no_new_mail",
                                    "create_email_rate_limited",
                                    "验证码过多",
                                    "RATE_LIMITED",
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
                                _pw = ""
                                try:
                                    _g, _f, _pw = build_profile()
                                except Exception:
                                    _pw = "N" + __import__("uuid").uuid4().hex[:8] + "!a7#TmpPw9x"
                                burn_mailbox_to_pending(
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

                if not mail_ok:
                    raise Exception("验证码阶段失败，已达到最大重试次数")
                log(f"[*] 验证码: {code}")
                log("[*] 4. 填写资料")
                profile = fill_profile_and_submit(
                    log_callback=log, cancel_callback=controller.should_stop
                )
                log(f"[*] 资料已填: {profile.get('given_name')} {profile.get('family_name')}")
                log("[*] 5. 等待 sso cookie")
                try:
                    sso = wait_for_sso_cookie(
                        log_callback=log, cancel_callback=controller.should_stop
                    )
                except Exception as sso_exc:
                    msg = str(sso_exc)
                    if "未获取到 sso cookie" in msg or "sso cookie" in msg.lower():
                        try:
                            from hybrid_register import burn_mailbox_to_pending
                            burn_mailbox_to_pending(
                                email,
                                str(profile.get("password") or ""),
                                reason="browser_sso_timeout_likely_registered",
                                log=log,
                            )
                            log(f"[!] browser/cli no SSO after profile submit -> pending_sso email={email} detail={msg}")
                        except Exception as pend_exc:
                            log(f"[!] pending_sso save fail email={email}: {pend_exc}")
                        raise Exception(f"pending_sso:browser_sso_timeout email={email} {msg}")
                    raise
                try:
                    line = f"{email}----{profile.get('password','')}----{sso}\n"
                    with open(accounts_output_file, "a", encoding="utf-8") as f:
                        f.write(line)
                except Exception as file_exc:
                    log(f"[Debug] 保存账号文件失败: {file_exc}")
                # NSFW / g2a / CPA：默认后台补写，功能保留、不挡下一号
                page = _get_page()
                schedule_post_registration(
                    email,
                    str(profile.get("password") or ""),
                    sso,
                    page=page,
                    log_callback=log,
                )
                success_count += 1
                retry_count_for_slot = 0
                i += 1
                log(f"[+] 注册成功: {email}")
                try:
                    from hybrid_register import mark_outlook_registered
                    mark_outlook_registered(email, log)
                except Exception as _reg_exc:
                    try:
                        log(f"[!] browser/cli mark_outlook_registered fail email={email}: {_reg_exc}")
                    except Exception:
                        pass

                log(f"[*] 当前统计: 成功 {success_count} | 失败 {fail_count}")
                if success_count > 0 and success_count % MEMORY_CLEANUP_INTERVAL == 0 and i < count:
                    cleanup_runtime_memory(
                        log_callback=log,
                        reason=f"已成功 {success_count} 个账号，执行定期清理",
                    )
            except RegistrationCancelled:
                log("[!] 注册被停止")
                break
            except AccountRetryNeeded as exc:
                retry_count_for_slot += 1
                if retry_count_for_slot <= max_slot_retry:
                    log(
                        f"[!] 当前账号流程卡住，重试第 {retry_count_for_slot}/{max_slot_retry} 次: {exc}"
                    )
                else:
                    fail_count += 1
                    retry_count_for_slot = 0
                    i += 1
                    log(f"[-] 当前账号已达到最大重试次数，跳过: {exc}")
            except Exception as exc:
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
            finally:
                if controller.should_stop():
                    break
                if _get_browser() is None:
                    start_browser(log_callback=log)
                else:
                    restart_browser(log_callback=log)
                sleep_with_cancel(1, controller.should_stop)
    except KeyboardInterrupt:
        controller.stop()
        log("[!] 收到 Ctrl+C，正在停止并清理")
    except Exception as exc:
        log(f"[!] 任务异常: {exc}")
    finally:
        # 浏览器关掉前先尽量完成后台入池/CPA/NSFW（不依赖 page）
        wait_post_success_queue(timeout=None, log_callback=log)
        try:
            if controller.should_stop():
                force_stop_registration(log_callback=log, reason="browser_job_stopped")
            else:
                cleanup_runtime_memory(log_callback=log, reason="任务结束")
        except Exception as fin_exc:
            log(f"[!] job finally cleanup: {fin_exc}")
            try:
                force_kill_registration_browsers(log_callback=log)
            except Exception:
                pass
        log(f"[*] 任务结束。成功 {success_count} | 失败 {fail_count} | pending_sso {pending_sso_count}")
    return {
        "success": success_count,
        "fail": fail_count,
        "pending_sso": pending_sso_count,
        "accounts_file": accounts_output_file,
        "stopped": bool(controller.should_stop()),
    }



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
        try:
            from worker_coord import start_continuous_preflight
            start_continuous_preflight(config, log=log, top=int(config.get("mail_top_per_folder") or 5))
        except Exception as cpf_exc:
            log(f"[!] continuous email preflight start: {cpf_exc}")

    accounts_output_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"accounts_{now_beijing('%Y%m%d_%H%M%S')}.txt",
    )
    log(f"[*] 成功账号将实时保存到: {accounts_output_file}")
    coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max(8, int(count) * 3), claim_mode="attempt")
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
            try:
                _clear_xai_session_cookies(log_callback=wlog)
            except Exception as _clr_exc:
                try:
                    wlog(f"[Debug] pre-signup cookie clear: {_clr_exc}")
                except Exception:
                    pass
            open_signup_page(log_callback=wlog, cancel_callback=controller.should_stop)
            wlog("[*] 2. 创建邮箱并提交")
            try:
                email, dev_token = fill_email_and_submit(
                    log_callback=wlog, cancel_callback=controller.should_stop
                )
            except Exception as fill_exc:
                # 18r35c: rate-limit raised from fill_email (outside fill_code try)
                fmsg = str(fill_exc)
                _rl = any(
                    k in fmsg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                        "too many verification",
                        "too many codes",
                    )
                )
                if _rl:
                    _em = str(email or "")
                    try:
                        import re as _re_rl
                        _m = _re_rl.search(r"email=([^\s]+)", fmsg)
                        if _m:
                            _em = _m.group(1).strip()
                    except Exception:
                        pass
                    if _em:
                        try:
                            from hybrid_register import handle_create_email_rate_limited
                            handle_create_email_rate_limited(
                                _em,
                                "",
                                log=wlog,
                                source="browser_mt_fill_email",
                                evidence=fmsg[:300],
                                mail_token=str(dev_token or ""),
                            )
                        except Exception as _rl_exc:
                            try:
                                from hybrid_register import remove_mailbox_from_pool
                                remove_mailbox_from_pool(
                                    _em, reason="create_email_rate_limited", log=wlog
                                )
                            except Exception:
                                wlog(f"[!] rate-limit cleanup fail: {_rl_exc}")
                    wlog(
                        f"[!] CreateEmail rate-limit -> switch mailbox "
                        f"try={mail_try}/{max_mail_retry} email={_em}"
                    )
                    if mail_try >= max_mail_retry:
                        raise Exception(
                            f"create_email_rate_limited exhausted email={_em} {fmsg}"
                        )
                    try:
                        restart_browser(log_callback=wlog)
                    except Exception:
                        pass
                    try:
                        sleep_with_cancel(1.5, controller.should_stop)
                    except Exception:
                        time.sleep(1.5)
                    continue
                raise
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
                _rl2 = any(
                    k in msg
                    for k in (
                        "create_email_rate_limited",
                        "RATE_LIMITED",
                        "验证码过多",
                    )
                )
                _mail_fail = _rl2 or any(
                    k in msg
                    for k in (
                        "early_no_new_mail",
                        "create_email_rate_limited",
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
                if _rl2 and email:
                    try:
                        from hybrid_register import handle_create_email_rate_limited
                        handle_create_email_rate_limited(
                            email,
                            "",
                            log=wlog,
                            source="browser_mt_fill_code",
                            evidence=msg[:300],
                            mail_token=str(dev_token or ""),
                        )
                    except Exception as _rl_exc2:
                        wlog(f"[!] rate-limit burn(code) fail: {_rl_exc2}")
                wlog(f"[!] 验证码阶段失败 try={mail_try}: {mail_exc}")
                # 18r41: non-mail errors raise immediately; mail-stage fails retry then
                # fall through to burn+pending_sso (do NOT bare-raise original early_no_new
                # on last try — that was counted as hard fail with pending_sso=0).
                if not _mail_fail:
                    raise
                if mail_try >= max_mail_retry:
                    break
                try:
                    restart_browser(log_callback=wlog)
                except Exception:
                    pass
        if not mail_ok:
            # 18r41: burn last mailbox + raise pending_sso: so MT worker records pending not fail
            _reason = "browser_mt_code_fail"
            try:
                _last = str(locals().get("msg") or "")
            except Exception:
                _last = ""
            if "early_no_new_mail" in _last:
                _reason = "early_no_new_mail"
            elif any(k in _last for k in ("create_email_rate_limited", "RATE_LIMITED", "验证码过多")):
                _reason = "create_email_rate_limited"
            elif any(k in _last for k in ("验证码超时", "code_timeout", "未收到验证码")):
                _reason = "browser_code_timeout"
            if email:
                try:
                    from hybrid_register import burn_mailbox_to_pending
                    _pw = ""
                    try:
                        _g, _f, _pw = build_profile()
                    except Exception:
                        _pw = "N" + __import__("uuid").uuid4().hex[:8] + "!a7#TmpPw9x"
                    burn_mailbox_to_pending(
                        email,
                        _pw,
                        reason=_reason,
                        log=wlog,
                        mail_token=str(dev_token or ""),
                    )
                    wlog(
                        f"[!] browser/mt mail fail -> pending_sso+del pool "
                        f"email={email} reason={_reason} detail={_last[:200]}"
                    )
                except Exception as pend_exc:
                    wlog(f"[!] browser/mt burn pending fail email={email}: {pend_exc}")
            raise Exception(
                f"pending_sso:browser_code_fail email={email or 'multiple'} "
                f"reason={_reason} 验证码阶段失败 detail={_last[:160]}"
            )
        wlog(f"[*] 验证码: {code}")
        wlog("[*] 4. 填写资料")
        # 18r30c: same serial path — fill_profile -> wait SSO -> disk -> schedule_post
        profile = fill_profile_and_submit(
            log_callback=wlog, cancel_callback=controller.should_stop
        )
        wlog(
            f"[*] 资料已填: {profile.get('given_name')} {profile.get('family_name')}"
        )
        wlog("[*] 5. 等待 sso cookie")
        try:
            sso = wait_for_sso_cookie(
                log_callback=wlog, cancel_callback=controller.should_stop
            )
        except Exception as sso_exc:
            msg = str(sso_exc)
            if "未获取到 sso cookie" in msg or "sso cookie" in msg.lower():
                try:
                    from hybrid_register import burn_mailbox_to_pending
                    burn_mailbox_to_pending(
                        email,
                        str(profile.get("password") or ""),
                        reason="browser_sso_timeout_likely_registered",
                        log=wlog,
                    )
                    wlog(
                        f"[!] browser/mt no SSO after profile submit -> pending_sso "
                        f"email={email} detail={msg}"
                    )
                except Exception as pend_exc:
                    wlog(f"[!] pending_sso save fail email={email}: {pend_exc}")
                raise Exception(
                    f"pending_sso:browser_sso_timeout email={email} {msg}"
                )
            raise
        # 18r44c: hard reject reused session_id before disk/import
        ok_claim, sid, owner = claim_sso_session_or_reject(
            sso, email=email, log_callback=wlog
        )
        if not ok_claim:
            try:
                from hybrid_register import burn_mailbox_to_pending
                burn_mailbox_to_pending(
                    email,
                    str(profile.get("password") or ""),
                    reason="sso_session_collision",
                    log=wlog,
                    mail_token="",
                )
            except Exception as pend_exc:
                wlog(f"[!] collision pending save fail: {pend_exc}")
            try:
                _clear_xai_session_cookies(log_callback=wlog)
            except Exception:
                pass
            try:
                restart_browser(log_callback=wlog)
            except Exception as rb_exc:
                wlog(f"[!] collision restart_browser: {rb_exc}")
            raise Exception(
                f"pending_sso:sso_session_collision email={email} "
                f"sid={(sid or '')[:13]} owner={owner}"
            )
        try:
            line = f"{email}----{profile.get('password','')}----{sso}\n"
            with open(accounts_output_file, "a", encoding="utf-8") as f:
                f.write(line)
            wlog(f"[+] browser/mt saved account line email={email}")
        except Exception as file_exc:
            wlog(f"[Debug] 保存账号文件失败: {file_exc}")
        page = _get_page()
        schedule_post_registration(
            email,
            str(profile.get("password") or ""),
            sso,
            page=page,
            log_callback=wlog,
        )
        try:
            from hybrid_register import mark_outlook_registered
            mark_outlook_registered(email, wlog)
        except Exception as _reg_exc:
            try:
                wlog(
                    f"[!] browser/mt mark_outlook_registered fail email={email}: {_reg_exc}"
                )
            except Exception:
                pass
        wlog(f"[+] 注册成功: {email}")
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
                    # 18r44c: hard isolate next account in same worker
                    try:
                        _clear_xai_session_cookies(log_callback=wlog)
                    except Exception:
                        pass
                    try:
                        restart_browser(log_callback=wlog)
                        wlog("[*] post-success browser restart for SSO isolation")
                    except Exception as rb_exc:
                        wlog(f"[!] post-success restart_browser: {rb_exc}")
                except RegistrationCancelled:
                    wlog("[!] 注册被停止")
                    break
                except Exception as exc:
                    emsg = str(exc)
                    if (
                        emsg.startswith("pending_sso:")
                        or "pending_sso:" in emsg
                        or "mailbox burned to pending_sso" in emsg
                        or "pending_sso" in emsg
                    ):
                        coord.record_pending()
                        wlog(f"[*] pending_sso counted (not fail): {exc}")
                    else:
                        coord.record_fail()
                        wlog(f"[-] 注册失败: {exc}")
                finally:
                    coord.log_stats()
                    try:
                        if controller.should_stop():
                            break
                        # 18r35: only hard-restart when browser/page is dead.
                        # Always-restart caused infinite open/close under workers=10.
                        b = _get_browser()
                        p = _get_page()
                        need_restart = b is None or p is None
                        if not need_restart:
                            try:
                                _ = p.url
                            except Exception:
                                need_restart = True
                        if need_restart:
                            if b is None:
                                start_browser(log_callback=wlog)
                            else:
                                restart_browser(log_callback=wlog)
                        else:
                            try:
                                open_signup_page(log_callback=wlog, cancel_callback=controller.should_stop)
                            except Exception as os_exc:
                                wlog(f"[!] soft open_signup failed, hard restart: {os_exc}")
                                restart_browser(log_callback=wlog)
                    except Exception as rb:
                        wlog(f"[!] restart browser: {rb}")
                    sleep_with_cancel(0.6, controller.should_stop)
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
        wait_post_success_queue(timeout=None, log_callback=log)
    except Exception:
        pass
    try:
        if controller.should_stop():
            try:
                from worker_coord import stop_continuous_preflight
                stop_continuous_preflight(log=log)
            except Exception:
                pass
            force_stop_registration(log_callback=log, reason="browser_mt_job_stopped")
        else:
            try:
                from worker_coord import stop_continuous_preflight
                stop_continuous_preflight(log=log)
            except Exception:
                pass
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


def run_registration_cli(count):
    return run_registration_job(count, log_callback=cli_log, controller=CliStopController())


def main_cli():
    load_config()
    count = int(config.get("register_count", 1) or 1)
    cli_log("[*] CLI 已加载配置")
    cli_log(f"[*] 当前邮箱服务商: {config.get('email_provider', 'duckmail')} | 注册数量: {count}")
    cli_log("[*] 输入 start 后开始；按 Ctrl+C 可强制停止")
    try:
        command = input("> ").strip().lower()
    except KeyboardInterrupt:
        cli_log("[!] 已取消")
        return
    if command != "start":
        cli_log("[!] 未输入 start，已退出")
        return
    run_registration_cli(count)


def main():
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() in ("start", "cli", "--cli"):
        main_cli()
        return
    if not HAS_TK:
        print("[!] 当前环境无 Tkinter，请使用 CLI: python grok_register_ttk.py cli")
        sys.exit(1)
    root = tk.Tk()
    setup_light_theme(root)
    app = GrokRegisterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
