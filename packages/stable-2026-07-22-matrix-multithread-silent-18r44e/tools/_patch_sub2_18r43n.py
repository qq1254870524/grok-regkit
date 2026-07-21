from pathlib import Path
p = Path('sub2api_client.py')
t = p.read_text(encoding='utf-8')
if 'def _resolve_runtime_config' not in t:
    t = t.replace(
        'def _client_cache_key(config: Dict[str, Any]) -> str:',
        'def _resolve_runtime_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:\n'
        '    """18r43n: never run Sub2 import with empty config (admin email missing)."""\n'
        '    cfg: Dict[str, Any] = dict(config or {})\n'
        '    if str(cfg.get("sub2api_admin_email") or "").strip() and str(cfg.get("sub2api_admin_password") or ""):\n'
        '        return cfg\n'
        '    try:\n'
        '        import grok_register_ttk as _engine\n'
        '        try:\n'
        '            _engine.load_config()\n'
        '        except Exception:\n'
        '            pass\n'
        '        eng = getattr(_engine, "config", None)\n'
        '        if isinstance(eng, dict):\n'
        '            merged = {**eng, **{k: v for k, v in cfg.items() if v not in (None, "")}}\n'
        '            if str(merged.get("sub2api_admin_email") or "").strip():\n'
        '                return merged\n'
        '            cfg = merged\n'
        '    except Exception:\n'
        '        pass\n'
        '    for path in (Path(__file__).resolve().parent / "config.json", _project_root() / "config.json"):\n'
        '        try:\n'
        '            if path.is_file():\n'
        '                disk = json.loads(path.read_text(encoding="utf-8"))\n'
        '                if isinstance(disk, dict):\n'
        '                    merged = {**disk, **{k: v for k, v in cfg.items() if v not in (None, "")}}\n'
        '                    if str(merged.get("sub2api_admin_email") or "").strip():\n'
        '                        return merged\n'
        '                    cfg = merged\n'
        '        except Exception:\n'
        '            continue\n'
        '    return cfg\n'
        '\n'
        '\n'
        'def _client_cache_key(config: Dict[str, Any]) -> str:',
        1,
    )
t = t.replace(
    '    """Retry failed Sub2 imports recorded in sub2api_import_pending.jsonl."""\n    cfg = config or {}\n',
    '    """Retry failed Sub2 imports recorded in sub2api_import_pending.jsonl."""\n    cfg = _resolve_runtime_config(config)\n',
    1,
)
t = t.replace(
    '    """Import G2A emails missing from Sub2API using CPA files first, else SSO token."""\n    cfg = config or {}\n',
    '    """Import G2A emails missing from Sub2API using CPA files first, else SSO token."""\n    cfg = _resolve_runtime_config(config)\n',
    1,
)
old = (
    'def get_client(\n'
    '    config: Dict[str, Any],\n'
    '    log_callback: Optional[Callable[[str], None]] = None,\n'
    '    *,\n'
    '    force_new: bool = False,\n'
    ') -> Sub2APIClient:\n'
    '    key = _client_cache_key(config)\n'
)
new = (
    'def get_client(\n'
    '    config: Dict[str, Any],\n'
    '    log_callback: Optional[Callable[[str], None]] = None,\n'
    '    *,\n'
    '    force_new: bool = False,\n'
    ') -> Sub2APIClient:\n'
    '    config = _resolve_runtime_config(config)\n'
    '    key = _client_cache_key(config)\n'
)
if old not in t:
    raise SystemExit('get_client block missing')
t = t.replace(old, new, 1)
if '18r43n:' not in t[:250]:
    t = '# 18r43n: _resolve_runtime_config auto-load admin creds when config empty\n' + t
p.write_text(t, encoding='utf-8')
import ast
ast.parse(t)
print('patched OK')
