# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(r"C:\Users\zhang\grok-regkit\sub2api_client.py")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
# find function start
fn = None
for i, l in enumerate(lines):
    if l.startswith("def backfill_missing_sub2api_from_cpa_and_sso"):
        fn = i
        break
if fn is None:
    raise SystemExit("fn not found")
# find "# map email -> sso" and "client = get_client" after fn
map_i = client_i = None
for i in range(fn, min(fn + 200, len(lines))):
    if "# map email -> sso" in lines[i] and map_i is None:
        map_i = i
    if lines[i].startswith("    client = get_client(cfg, log_callback=log)"):
        client_i = i
        break
print("fn", fn + 1, "map", (map_i + 1 if map_i is not None else None), "client", (client_i + 1 if client_i is not None else None))
if map_i is None or client_i is None:
    raise SystemExit("markers missing")
# also include tok_path assignment just before map - typically a few lines before map
tok_i = None
for i in range(map_i, fn, -1):
    if "tok_path = _project_root()" in lines[i]:
        tok_i = i
        break
print("tok_i", tok_i + 1 if tok_i is not None else None)
if tok_i is None:
    tok_i = map_i
# print old block summary
print("OLD first:", lines[tok_i][:80])
print("OLD last before client:", lines[client_i - 1][:80])

insert = '''    tok_path = _project_root() / "token.json"
    raw = json.loads(tok_path.read_text(encoding="utf-8")) if tok_path.is_file() else {}
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    entries = raw.get(pool) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        entries = []

    # map email -> sso (token.json + accounts*.txt session SSO) 18r43n
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
            m = re.search(r"[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}", blob)
            if m:
                em = m.group(0).lower()
        if not sso:
            for k, v in ent.items():
                if isinstance(v, str) and len(v) > 40 and ("eyJ" in v or len(v) > 80):
                    sso = v
                    break
        if em and "@" in em and sso:
            email_sso[em] = sso

    # 18r43n: harvest session SSO from accounts*.txt (not only token.json)
    try:
        from grok_register_ttk import _is_importable_session_sso as _is_sess
    except Exception:
        _is_sess = None  # type: ignore
    for apath in sorted(_project_root().glob("accounts*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            for ln in apath.read_text(encoding="utf-8", errors="ignore").splitlines():
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
                    if _is_sess is not None:
                        try:
                            ok = bool(_is_sess(cand))
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
new_lines = lines[:tok_i] + [insert if insert.endswith("\n") else insert + "\n"] + lines[client_i:]
# fix insert to keepends style - insert is multi-line string without keepends list
# rebuild properly
block_lines = [ln + "\n" for ln in insert.splitlines()]
# preserve final blank if needed
new_lines = lines[:tok_i] + block_lines + lines[client_i:]
path.write_text("".join(new_lines), encoding="utf-8")
import py_compile
py_compile.compile(str(path), doraise=True)
print("compile_ok patched lines", tok_i + 1, "to", client_i)
# show snippet
text = path.read_text(encoding="utf-8")
i = text.find("def backfill_missing_sub2api_from_cpa_and_sso")
print(text[i:i+1800][:1800])
