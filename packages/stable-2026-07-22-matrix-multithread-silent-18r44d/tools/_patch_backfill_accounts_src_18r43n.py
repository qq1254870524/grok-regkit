# -*- coding: utf-8 -*-
from pathlib import Path
import re

path = Path(r"C:\Users\zhang\grok-regkit\sub2api_client.py")
text = path.read_text(encoding="utf-8")
marker = "    tok_path = _project_root() / \"token.json\""
idx = text.find(marker)
if idx < 0:
    marker = "    tok_path = _project_root() / 'token.json'"
    idx = text.find(marker)
print("idx", idx)
if idx < 0:
    # find by unique comment
    idx = text.find("# map email -> sso")
    print("comment idx", idx)
    print(text[idx-200:idx+100])
    raise SystemExit(2)

# find end of email_sso building loop - after the for ent in entries loop, before client = get_client
start = idx
# find "client = get_client(cfg, log_callback=log)" after start within function
client_m = re.search(r"\n    client = get_client\(cfg, log_callback=log\)", text[start:])
if not client_m:
    raise SystemExit("client marker missing")
end = start + client_m.start()
old_block = text[start:end]
print("OLD_LEN", len(old_block))
print(old_block[:300])
print("---")

new_block = r'''    tok_path = _project_root() / "token.json"
    raw = json.loads(tok_path.read_text(encoding="utf-8")) if tok_path.is_file() else {}
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    entries = raw.get(pool) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        entries = []

    # map email -> sso (token.json + accounts*.txt session SSO)
    email_sso: Dict[str, str] = {}
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        # grok-regkit local token.json: {token, tags, note=email}
        em = str(
            ent.get("email")
            or ent.get("mail")
            or ent.get("account")
            or ent.get("note")
            or ""
        ).strip().lower()
        sso = str(ent.get("token") or ent.get("sso") or ent.get("value") or "").strip()
        if not em or "@" not in em:
            blob = json.dumps(ent, ensure_ascii=False)
            m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", blob)
            if m:
                em = m.group(0).lower()
        if not sso:
            for k, v in ent.items():
                if isinstance(v, str) and len(v) > 40 and ("eyJ" in v or len(v) > 80):
                    sso = v
                    break
        if em and "@" in em and sso:
            email_sso[em] = sso

    # 18r43n: also harvest session SSO from accounts*.txt so full pool fill is not limited to token.json
    try:
        from grok_register_ttk import _is_importable_session_sso
    except Exception:
        _is_importable_session_sso = None  # type: ignore
    root = _project_root()
    for path in sorted(root.glob("accounts*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = (ln or "").strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split("----")
                if len(parts) < 2:
                    continue
                em = parts[0].strip().lower()
                if "@" not in em:
                    continue
                tok = ""
                for part in reversed(parts):
                    cand = part.strip()
                    if not cand:
                        continue
                    ok = False
                    if _is_importable_session_sso is not None:
                        try:
                            ok = bool(_is_importable_session_sso(cand))
                        except Exception:
                            ok = False
                    else:
                        ok = cand.count(".") == 2 and 40 <= len(cand) <= 800
                    if ok:
                        tok = cand
                        break
                if tok:
                    email_sso[em] = tok
        except Exception:
            continue

'''
text2 = text[:start] + new_block + text[end:]
if text2 == text:
    raise SystemExit("no change")
# backup
bak = path.with_suffix(".py.bak_18r43n")
if not bak.exists():
    bak.write_text(text, encoding="utf-8")
path.write_text(text2, encoding="utf-8")
print("patched", path)
# syntax check
import py_compile
py_compile.compile(str(path), doraise=True)
print("compile_ok")
