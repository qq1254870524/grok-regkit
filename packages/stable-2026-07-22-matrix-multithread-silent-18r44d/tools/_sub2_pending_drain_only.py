# -*- coding: utf-8 -*-
import json, sys, time
from pathlib import Path
ROOT = Path(r'C:\Users\zhang\grok-regkit')
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
LOG = ROOT / 'matrix_runs' / '_SUB2_PENDING_DRAIN_18r43.log'
def log(m):
    line = time.strftime('%Y-%m-%dT%H:%M:%S ') + str(m)
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')
cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
cfg = dict(cfg)
cfg['sub2api_verify_after_add'] = False
cfg['sub2api_require_verify_success'] = False
from sub2api_client import process_sub2api_pending_file, log_pool_counts
log('=== SUB2 PENDING DRAIN ===')
log_pool_counts(config=cfg, log_callback=log)
pend = process_sub2api_pending_file(config=cfg, log_callback=log, limit=0)
log('PEND ' + json.dumps({k:v for k,v in pend.items() if k!='errors'}, ensure_ascii=False))
log_pool_counts(config=cfg, log_callback=log)
log('DONE')
