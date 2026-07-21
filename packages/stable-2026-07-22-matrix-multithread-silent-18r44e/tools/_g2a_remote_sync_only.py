# -*- coding: utf-8 -*-
import json, sys, time, traceback, urllib.request, urllib.parse
from pathlib import Path
ROOT = Path(r'C:\Users\zhang\grok-regkit')
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
LOG = ROOT / 'matrix_runs' / '_G2A_REMOTE_SYNC_18r43.log'

def log(m):
    line = time.strftime('%Y-%m-%dT%H:%M:%S ') + str(m)
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')

def main():
    LOG.write_text('', encoding='utf-8')
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    from grok_register_ttk import load_config, add_token_to_grok2api_remote_pool, _is_importable_session_sso
    load_config()
    pool = str(cfg.get('grok2api_pool_name') or 'ssoBasic')
    tok = json.loads((ROOT / 'token.json').read_text(encoding='utf-8'))
    items = tok.get(pool) or []
    base = str(cfg.get('grok2api_remote_base') or 'http://127.0.0.1:8010').rstrip('/')
    key = str(cfg.get('grok2api_remote_app_key') or '')
    if not key or len(key) < 12:
        log('BAD_APP_KEY_LEN=%s' % len(key)); return 2
    url = base + '/admin/api/tokens?' + urllib.parse.urlencode({'app_key': key})
    with urllib.request.urlopen(url, timeout=30) as resp:
        remote = json.loads(resp.read().decode())
    remote_tokens = remote.get('tokens') or []
    remote_vals = set()
    for t in remote_tokens:
        if not isinstance(t, dict):
            continue
        v = str(t.get('token') or t.get('sso') or t.get('value') or '').strip()
        if v:
            remote_vals.add(v)
    log('BEFORE remote=%s local=%s remote_token_vals=%s' % (len(remote_tokens), len(items), len(remote_vals)))
    added = skipped = failed = bad_shape = 0
    fail_reasons = {}
    for e in items:
        if not isinstance(e, dict):
            skipped += 1; continue
        email = str(e.get('note') or e.get('email') or '').strip()
        token = str(e.get('token') or e.get('sso') or e.get('value') or '').strip()
        if not token:
            skipped += 1; continue
        if token in remote_vals:
            skipped += 1; continue
        if not _is_importable_session_sso(token):
            bad_shape += 1; failed += 1
            fail_reasons['not_session_sso'] = fail_reasons.get('not_session_sso', 0) + 1
            continue
        try:
            ok = add_token_to_grok2api_remote_pool(token, email=email, log_callback=None)
            if ok:
                added += 1; remote_vals.add(token)
            else:
                failed += 1
                fail_reasons['add_false'] = fail_reasons.get('add_false', 0) + 1
        except Exception as ex:
            failed += 1
            name = type(ex).__name__
            fail_reasons[name] = fail_reasons.get(name, 0) + 1
            if sum(fail_reasons.values()) <= 15:
                log('fail email_len=%s token_len=%s err=%s: %s' % (len(email), len(token), name, ex))
        if added and added % 25 == 0:
            log('progress added=%s failed=%s skipped=%s bad_shape=%s' % (added, failed, skipped, bad_shape))
        time.sleep(0.03)
    with urllib.request.urlopen(url, timeout=30) as resp:
        remote2 = json.loads(resp.read().decode())
    final_n = len(remote2.get('tokens') or [])
    log('AFTER remote=%s added=%s failed=%s skipped=%s bad_shape=%s' % (final_n, added, failed, skipped, bad_shape))
    log('FAIL_REASONS ' + json.dumps(fail_reasons, ensure_ascii=False))
    log('DONE'); return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        log('FATAL ' + traceback.format_exc()); raise
