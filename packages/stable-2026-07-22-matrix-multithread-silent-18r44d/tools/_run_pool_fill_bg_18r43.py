# -*- coding: utf-8 -*-
import sys, traceback, json, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r'C:/Users/zhang/grok-regkit')
sys.path.insert(0, str(ROOT))
LOG = ROOT / 'tools' / '_pool_fill_bg_18r43.log'

def log(m):
    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    with LOG.open('a', encoding='utf-8') as f:
        f.write(ts + ' ' + str(m) + chr(10))

def main():
    log('BEGIN pool fill v2')
    import grok_register_ttk as engine
    engine.load_config()
    cfg = dict(engine.config)
    log('admin_len=' + str(len(str(cfg.get('sub2api_admin_email') or ''))) + ' key_len=' + str(len(str(cfg.get('grok2api_remote_app_key') or ''))))
    import sub2api_client as s2
    try:
        r = s2.process_sub2api_pending_file(config=cfg, log_callback=log, limit=200)
        log('pending_file ' + repr(r))
    except Exception as e:
        log('pending_file err ' + str(e))
        traceback.print_exc()
    try:
        r = s2.backfill_missing_sub2api_from_cpa_and_sso(config=cfg, log_callback=log, limit=500)
        log('sub2_backfill ' + repr(r))
    except Exception as e:
        log('sub2_backfill err ' + str(e))
        traceback.print_exc()
    try:
        import runpy
        runpy.run_path(str(ROOT / 'tools' / '_g2a_remote_sync_only.py'), run_name='__main__')
        log('g2a_sync done')
    except Exception as e:
        log('g2a_sync err ' + str(e))
    try:
        integ = json.loads(urllib.request.urlopen('http://127.0.0.1:8092/api/integration', timeout=15).read().decode())
        s2c = integ.get('sub2api') or {}
        g2 = integ.get('g2a') or integ.get('grok2api') or {}
        log('FINAL sub2=' + str(s2c.get('account_count') or s2c.get('count')) + ' g2a=' + str(g2.get('account_count') or g2.get('count')))
    except Exception as e:
        log('final err ' + str(e))
    log('END')

if __name__ == '__main__':
    main()
