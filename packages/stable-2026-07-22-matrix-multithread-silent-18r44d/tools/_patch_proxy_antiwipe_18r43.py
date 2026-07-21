from pathlib import Path

p = Path(r"C:\Users\zhang\grok-regkit\web\server.py")
text = p.read_text(encoding="utf-8")

old = '''def _sync_proxy_list_file(text: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    """Write proxy pool text to list file and keep config.proxy_list in sync."""
    c = cfg if isinstance(cfg, dict) else engine.config
    cleaned_lines = []
    for line in str(text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n"):
        s = line.strip()
        if not s:
            continue
        cleaned_lines.append(s)
    body = ("\\n".join(cleaned_lines) + "\\n") if cleaned_lines else ""
    name = str(c.get("proxy_list_file") or "socks5_proxies.txt").strip() or "socks5_proxies.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except Exception as exc:
        _append_log(f"[!] 写入代理池文件失败: {exc}")
    c["proxy_list"] = body.rstrip("\\n")
    if not os.path.isabs(name):
        c["proxy_list_file"] = name
    try:
        if hasattr(engine, "_PROXY_POOL_CACHE"):
            engine._PROXY_POOL_CACHE = {"mtime": None, "path": None, "items": []}
        if hasattr(engine, "load_proxy_list"):
            engine.load_proxy_list(c, force_reload=True)
    except Exception:
        pass
    return body
'''

new = '''def _sync_proxy_list_file(
    text: str,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    allow_clear: bool = False,
) -> str:
    """Write proxy pool text to list file and keep config.proxy_list in sync.

    Empty text never wipes an existing non-empty pool unless allow_clear=True.
    Prevents put_config / mode-only updates from deleting socks5_proxies.txt.
    """
    c = cfg if isinstance(cfg, dict) else engine.config
    cleaned_lines = []
    for line in str(text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cleaned_lines.append(s)
    body = ("\\n".join(cleaned_lines) + "\\n") if cleaned_lines else ""
    name = str(c.get("proxy_list_file") or "socks5_proxies.txt").strip() or "socks5_proxies.txt"
    path = Path(name) if os.path.isabs(name) else (ROOT / name)
    if not cleaned_lines and not allow_clear:
        existing = ""
        try:
            if path.is_file():
                existing = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            existing = ""
        exist_lines = [
            ln.strip()
            for ln in existing.replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n")
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if exist_lines:
            _append_log(
                f"[!] 拒绝用空 proxy_list 覆盖代理池文件（保留 {len(exist_lines)} 条）: {path.name}"
            )
            c["proxy_list"] = "\\n".join(exist_lines)
            if not os.path.isabs(name):
                c["proxy_list_file"] = name
            try:
                if hasattr(engine, "_PROXY_POOL_CACHE"):
                    engine._PROXY_POOL_CACHE = {"mtime": None, "path": None, "items": []}
                if hasattr(engine, "load_proxy_list"):
                    engine.load_proxy_list(c, force_reload=True)
            except Exception:
                pass
            return c["proxy_list"] + ("\\n" if c["proxy_list"] else "")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except Exception as exc:
        _append_log(f"[!] 写入代理池文件失败: {exc}")
    c["proxy_list"] = body.rstrip("\\n")
    if not os.path.isabs(name):
        c["proxy_list_file"] = name
    try:
        if hasattr(engine, "_PROXY_POOL_CACHE"):
            engine._PROXY_POOL_CACHE = {"mtime": None, "path": None, "items": []}
        if hasattr(engine, "load_proxy_list"):
            engine.load_proxy_list(c, force_reload=True)
    except Exception:
        pass
    return body
'''

if old not in text:
    raise SystemExit("OLD_BLOCK_NOT_FOUND")
text = text.replace(old, new, 1)

old2 = '''    # Web panel SOCKS5 pool: save textarea -> config + socks5_proxies.txt
    if "proxy_list" in updates or str(engine.config.get("proxy_mode") or "").strip().lower() in (
        "socks5_list",
        "socks5_pool",
        "proxy_list",
        "list",
        "socks5",
    ):
        _sync_proxy_list_file(str(engine.config.get("proxy_list") or ""), engine.config)
'''

new2 = '''    # Web panel SOCKS5 pool: only rewrite file when proxy_list is in the payload.
    # Setting proxy_mode alone must not wipe socks5_proxies.txt with an empty list.
    _proxy_mode = str(engine.config.get("proxy_mode") or "").strip().lower()
    if "proxy_list" in updates:
        raw_pl = str(engine.config.get("proxy_list") or "")
        allow_clear = (not raw_pl.strip()) and bool(updates.get("_clear_proxy_list"))
        _sync_proxy_list_file(raw_pl, engine.config, allow_clear=allow_clear)
    elif _proxy_mode in ("socks5_list", "socks5_pool", "proxy_list", "list", "socks5"):
        if not str(engine.config.get("proxy_list") or "").strip():
            try:
                hydrated = _proxy_list_raw_text(engine.config)
                n = len([x for x in hydrated.splitlines() if x.strip()])
                if n:
                    engine.config["proxy_list"] = hydrated.rstrip("\\n")
                    _append_log(f"[+] proxy_list 已从文件回填 {n} 条")
            except Exception as exc:
                _append_log(f"[!] proxy_list 文件回填失败: {exc}")
'''

if old2 not in text:
    raise SystemExit("OLD2_NOT_FOUND")
text = text.replace(old2, new2, 1)
p.write_text(text, encoding="utf-8")
print("patched_ok")

# re-ensure pool on disk/config
import json
root = Path(r"C:\Users\zhang\grok-regkit")
body = (root / "socks5_proxies.txt").read_text(encoding="utf-8", errors="ignore")
lines = [ln for ln in body.splitlines() if ln.strip()]
cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
cfg["proxy_list"] = body.rstrip("\n")
cfg["proxy_list_file"] = "socks5_proxies.txt"
cfg["proxy_mode"] = "socks5_list"
(root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("proxy_lines", len(lines), "bytes", (root / "socks5_proxies.txt").stat().st_size)
