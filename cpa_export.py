"""Register-machine hook: mint CPA xai auth after successful registration.

OIDC package lives at ./cpa_xai (bundled with this project).
Optional override: config pi_reverse_tools / env API_REVERSE_TOOLS
points at a directory that *contains* the cpa_xai package.

Changelog:
- 2026-07-17 fuse-v1 (grokRegister-cpa fusion):
  * Prefer Authorization Code + PKCE mint with referrer=grok-build when SSO
    is available (cpa_prefer_authcode, default True) via sso_to_auth_json.
  * After successful write, optional remote upload to CLIProxyAPI Management
    API (cpa_remote_url + cpa_management_key, gate cpa_remote_upload).
  * cpa_auto_add accepted as alias of cpa_export_enabled (upstream name).
  * Log access_token referrer claim so free grok-4.5 path is diagnosable.
  * Keep existing device/protocol mint as fallback.
"""


from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

_REG_DIR = Path(__file__).resolve().parent
_DEFAULT_OUT = _REG_DIR / "cpa_auths"
_DEFAULT_CPA = Path("")  # empty = do not assume a machine-local CPA path


def _ensure_cpa_xai_on_path(tools_dir: str | Path | None = None) -> Path:
    """Put the parent of `cpa_xai` on sys.path. Default: this project root."""
    if tools_dir:
        tools = Path(tools_dir).expanduser().resolve()
    else:
        env = (os.environ.get("API_REVERSE_TOOLS") or "").strip()
        tools = Path(env).expanduser().resolve() if env else _REG_DIR
    # If user pointed at .../cpa_xai itself, use its parent
    if tools.name == "cpa_xai" and (tools / "__init__.py").is_file():
        tools = tools.parent
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return tools


def export_cookies_from_page(page: Any) -> list[dict]:
    """Best-effort export of cookies from a DrissionPage tab/browser."""
    if page is None:
        return []
    cookies = None
    for getter in (
        lambda: page.cookies(all_domains=True, all_info=True),
        lambda: page.cookies(all_domains=True),
        lambda: page.cookies(),
    ):
        try:
            cookies = getter()
            if cookies:
                break
        except TypeError:
            continue
        except Exception:
            continue
    if not cookies:
        try:
            browser = getattr(page, "browser", None)
            if browser is not None:
                cookies = browser.cookies()
        except Exception:
            cookies = None
    if isinstance(cookies, list):
        return [c for c in cookies if isinstance(c, dict)]
    return []




def _cpa_export_enabled(cfg: dict) -> bool:
    """True if CPA export should run.

    Upstream grokRegister-cpa uses cpa_auto_add; this project historically
    used cpa_export_enabled. Either may enable; either explicitly False disables.
    """
    if "cpa_export_enabled" in cfg and cfg.get("cpa_export_enabled") is False:
        return False
    if "cpa_auto_add" in cfg and cfg.get("cpa_auto_add") is False:
        return False
    if cfg.get("cpa_export_enabled", None) is True or cfg.get("cpa_auto_add", None) is True:
        return True
    # default on when neither key set to False
    return bool(cfg.get("cpa_export_enabled", True))


def _jwt_payload(token: str) -> dict:
    import base64
    import json
    parts = (token or "").split(".")
    if len(parts) < 2:
        return {}
    pad = "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}


def access_token_referrer(access_token: str) -> str | None:
    pl = _jwt_payload(access_token)
    ref = pl.get("referrer")
    return None if ref is None else str(ref)


def upload_cpa_auth_remote(
    base_url: str,
    management_key: str,
    record: dict,
    *,
    timeout: int = 30,
    log: Callable[[str], None] | None = None,
) -> str:
    """POST auth JSON to CLIProxyAPI Management API.

    Endpoint: POST {base}/v0/management/auth-files?name=xai-<email>.json
    Header: Authorization: Bearer <plaintext management key>
    Body: raw JSON auth record

    Returns uploaded file name.
    """
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    from cpa_xai.schema import credential_file_name

    base = str(base_url or "").strip().rstrip("/")
    key = str(management_key or "").strip()
    if not base:
        raise ValueError("cpa_remote_url 为空")
    if not key:
        raise ValueError("cpa_management_key 为空")
    # strip accidental /v1 suffix
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")

    name = credential_file_name(
        str(record.get("email") or ""),
        str(record.get("sub") or ""),
    )
    q = urllib.parse.urlencode({"name": name})
    url = f"{base}/v0/management/auth-files?{q}"
    body = json.dumps(record, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "grok-regkit-cpa-fuse/1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            _ = resp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = (e.read() or b"").decode("utf-8", errors="replace").strip()
        except Exception:
            detail = str(e.reason or e)
        if len(detail) > 300:
            detail = detail[:300] + "..."
        raise RuntimeError(f"远程上传失败 HTTP {e.code}: {detail or e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"远程上传失败: {e}") from e

    if log:
        log(f"[cpa] remote upload ok name={name} -> {base}")
    return name


def _maybe_remote_upload(cfg: dict, auth_path: Path, log: Callable[[str], None]) -> dict:
    """Upload written auth file if remote CPA is configured."""
    import json

    remote_url = str(cfg.get("cpa_remote_url") or "").strip()
    remote_key = str(cfg.get("cpa_management_key") or "").strip()
    # default: upload only when both set AND cpa_remote_upload is true
    # (or cpa_remote_upload omitted but both set → still require explicit true to avoid
    #  bcrypt-hashed secret-key mistakes on local CPA)
    upload_flag = cfg.get("cpa_remote_upload", False)
    if isinstance(upload_flag, str):
        upload_flag = upload_flag.strip().lower() in {"1", "true", "yes", "on"}
    if not upload_flag:
        return {"skipped": True, "reason": "cpa_remote_upload off"}
    if not remote_url or not remote_key:
        return {"skipped": True, "reason": "remote url/key empty"}
    try:
        record = json.loads(Path(auth_path).read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"read auth: {e}"}
    if not isinstance(record, dict):
        return {"ok": False, "error": "auth file not object"}
    try:
        name = upload_cpa_auth_remote(
            remote_url,
            remote_key,
            record,
            timeout=int(cfg.get("cpa_remote_timeout_sec", 30) or 30),
            log=log,
        )
        return {"ok": True, "name": name, "url": remote_url.rstrip("/")}
    except Exception as e:
        log(f"[cpa] remote upload failed: {e}")
        return {"ok": False, "error": str(e)}


def _mint_via_authcode(
    *,
    email: str,
    sso: str,
    out_dir: Path,
    proxy: str,
    log: Callable[[str], None],
) -> dict:
    """Authorization Code + PKCE mint (referrer=grok-build). Upstream fusion."""
    try:
        from sso_to_auth_json import (
            sso_to_token,
            token_to_cpa_record,
            write_cpa_auth,
        )
    except Exception as e:
        return {"ok": False, "error": f"import sso_to_auth_json: {e}"}

    def _ulog(msg: str) -> None:
        # upstream uses emoji; keep prefix consistent
        log(msg if msg.startswith("[cpa]") or msg.startswith("  ") else f"  {msg}")

    token = sso_to_token(sso, proxy=proxy or "", log=_ulog)
    if not token or not token.get("access_token"):
        return {"ok": False, "error": "authcode mint returned no token"}
    ref = access_token_referrer(str(token.get("access_token") or ""))
    log(f"[cpa] authcode access_token referrer={ref!r}")
    record = token_to_cpa_record(token, email=email, sso=sso)
    # ensure free path base_url
    if not str(record.get("base_url") or "").startswith("https://cli-chat-proxy.grok.com"):
        record["base_url"] = "https://cli-chat-proxy.grok.com/v1"
    path = write_cpa_auth(out_dir, record)
    return {
        "ok": True,
        "path": str(path),
        "mint_method": "authcode_pkce",
        "referrer": ref,
        "record": record,
    }


def export_cpa_xai_for_account(
    email: str,
    password: str,
    *,
    page: Any | None = None,
    cookies: Any | None = None,
    sso: str | None = None,
    config: dict | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict:
    """Mint OIDC + write xai-<email>.json under register cpa_auths (and optional CPA auth-dir)."""
    cfg = config or {}
    log = log_callback or (lambda m: print(m, flush=True))

    if not _cpa_export_enabled(cfg):
        log("[cpa] export disabled")
        return {"ok": False, "skipped": True, "reason": "disabled"}

    tools_dir = cfg.get("api_reverse_tools") or cfg.get("cpa_xai_parent") or None
    _ensure_cpa_xai_on_path(tools_dir)

    try:
        from cpa_xai import mint_and_export  # type: ignore
    except Exception as e:  # noqa: BLE001
        log(f"[cpa] import cpa_xai failed: {e}")
        return {"ok": False, "error": f"import: {e}"}

    out_dir = Path(cfg.get("cpa_auth_dir") or _DEFAULT_OUT).expanduser()
    if not out_dir.is_absolute():
        out_dir = (_REG_DIR / out_dir).resolve()

    hotload_raw = (cfg.get("cpa_hotload_dir") or "").strip()
    cpa_dir = Path(hotload_raw).expanduser() if hotload_raw else None
    if cpa_dir and not cpa_dir.is_absolute():
        cpa_dir = (_REG_DIR / cpa_dir).resolve()

    # Priority: cpa_proxy > proxy > env. Config must beat shell https_proxy.
    proxy = (cfg.get("cpa_proxy") or cfg.get("proxy") or "").strip()
    if not proxy:
        proxy = (
            os.environ.get("https_proxy")
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("http_proxy")
            or ""
        ).strip()
    # Default headed: headless is frequently Cloudflare-blocked on accounts.x.ai
    headless = bool(cfg.get("cpa_headless", False))
    probe = bool(cfg.get("cpa_probe_after_write", True))
    probe_chat = bool(cfg.get("cpa_probe_chat", False))
    timeout = float(cfg.get("cpa_mint_timeout_sec", 240))
    base_url = cfg.get("cpa_base_url") or "https://cli-chat-proxy.grok.com/v1"
    force_standalone = bool(cfg.get("cpa_force_standalone", True))
    cookie_inject = bool(cfg.get("cpa_mint_cookie_inject", True))
    reuse_browser = bool(cfg.get("cpa_mint_browser_reuse", True))
    recycle_every = int(cfg.get("cpa_mint_browser_recycle_every", 15) or 0)
    # Protocol (pure HTTP SSO device flow) first; browser only on failure.
    prefer_protocol = bool(cfg.get("cpa_prefer_protocol", True))
    protocol_only = bool(cfg.get("cpa_protocol_only", False))
    protocol_poll_timeout = float(cfg.get("cpa_protocol_poll_timeout_sec", 90) or 90)

    # cookies: explicit arg > page export > none
    use_cookies = cookies
    if use_cookies is None and cookie_inject and page is not None:
        use_cookies = export_cookies_from_page(page)
    if not cookie_inject:
        use_cookies = None
    else:
        # Always attach SSO cookie clones — register cookies alone often miss accounts.x.ai host
        sso_val = (sso or "").strip()
        if not sso_val and isinstance(use_cookies, list):
            for c in use_cookies:
                if isinstance(c, dict) and c.get("name") in ("sso", "sso-rw") and c.get("value"):
                    sso_val = str(c.get("value"))
                    break
        if sso_val:
            base = list(use_cookies) if isinstance(use_cookies, list) else []
            for name in ("sso", "sso-rw"):
                for dom in (".x.ai", "accounts.x.ai", ".accounts.x.ai", "auth.x.ai", "grok.com", ".grok.com"):
                    base.append({
                        "name": name,
                        "value": sso_val,
                        "domain": dom,
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                    })
            use_cookies = base

    sso_val = (sso or "").strip()
    if not sso_val and isinstance(use_cookies, list):
        for c in use_cookies:
            if isinstance(c, dict) and c.get("name") in ("sso", "sso-rw") and c.get("value"):
                sso_val = str(c.get("value"))
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    log(
        f"[cpa] mint OIDC for {email} -> {out_dir} proxy={proxy or '(none)'} "
        f"cookies={len(use_cookies) if isinstance(use_cookies, list) else (1 if use_cookies else 0)} "
        f"reuse={reuse_browser} protocol={prefer_protocol}"
        f"{' only' if protocol_only else ''} sso={'yes' if sso_val else 'no'}"
    )

    def _log(msg: str) -> None:
        log(f"[cpa] {msg}")

    prefer_authcode = bool(cfg.get("cpa_prefer_authcode", True))
    result: dict = {}
    if prefer_authcode and sso_val:
        log("[cpa] try authcode mint (referrer=grok-build, fused from grokRegister-cpa)")
        ac = _mint_via_authcode(
            email=email,
            sso=sso_val,
            out_dir=out_dir,
            proxy=proxy or "",
            log=log,
        )
        if ac.get("ok") and ac.get("path"):
            result = ac
        else:
            log(f"[cpa] authcode mint failed, fallback device/protocol: {ac.get('error')}")

    if not result.get("ok"):
        result = mint_and_export(
        email=email,
        password=password,
        auth_dir=out_dir,
        page=None if force_standalone else page,
        proxy=proxy or None,
        headless=headless,
        base_url=base_url,
        probe=probe,
        probe_chat=probe_chat,
        browser_timeout_sec=timeout,
        force_standalone=force_standalone,
        cookies=use_cookies,
        sso=sso_val or None,
        reuse_browser=reuse_browser,
        recycle_every=recycle_every,
        prefer_protocol=prefer_protocol,
        protocol_only=protocol_only,
        protocol_poll_timeout_sec=protocol_poll_timeout,
        log=_log,
    )
    if result.get("mint_method"):
        log(f"[cpa] mint_method={result.get('mint_method')}")

    # By default, a failed post-write probe is only a warning: the CPA auth file
    # has already been minted and written. Set cpa_probe_required=true to make
    # missing /models grok-4.5 fail the export.
    if (
        not result.get("ok")
        and result.get("path")
        and str(result.get("error") or "").startswith("token ok but grok-4.5 not listed")
        and not cfg.get("cpa_probe_required", False)
    ):
        result["ok"] = True
        result["probe_warning"] = result.pop("error", "probe failed")
        log(f"[cpa] probe warning ignored (file already written): {result.get('probe_warning')}")

    if result.get("ok") and result.get("path") and cfg.get("cpa_copy_to_hotload", False) and cpa_dir:
        try:
            cpa_dir.mkdir(parents=True, exist_ok=True)
            src = Path(result["path"])
            dst = cpa_dir / src.name
            shutil.copy2(src, dst)
            os.chmod(dst, 0o600)
            result["cpa_path"] = str(dst)
            log(f"[cpa] hotload copy -> {dst}")
        except Exception as e:  # noqa: BLE001
            log(f"[cpa] hotload copy failed: {e}")
            result["cpa_copy_error"] = str(e)

    # referrer diagnostics + optional remote Management API upload (grokRegister-cpa)
    if result.get("ok") and result.get("path"):
        try:
            import json as _json
            rec = _json.loads(Path(result["path"]).read_text(encoding="utf-8"))
            ref = access_token_referrer(str(rec.get("access_token") or ""))
            result["referrer"] = ref
            if ref not in ("grok-build", "cli-proxy-api"):
                log(
                    f"[cpa] WARN access_token referrer={ref!r}; "
                    f"free grok-4.5 may fail — prefer authcode mint / sso_to_auth_json"
                )
            else:
                log(f"[cpa] access_token referrer={ref!r} ok")
        except Exception as e:  # noqa: BLE001
            log(f"[cpa] referrer check skipped: {e}")
        remote = _maybe_remote_upload(cfg, Path(result["path"]), log)
        result["remote_upload"] = remote
        if remote.get("ok"):
            log(f"[cpa] remote CPA name={remote.get('name')} url={remote.get('url')}")

    # failure log under register dir
    if not result.get("ok"):
        fail_path = out_dir / "cpa_auth_failed.txt"
        with open(fail_path, "a", encoding="utf-8") as f:
            f.write(f"{email}----{result.get('error') or 'unknown'}----{int(time.time())}\n")
        if cfg.get("cpa_mint_required", False):
            raise RuntimeError(f"CPA mint required but failed: {result.get('error')}")

    return result
