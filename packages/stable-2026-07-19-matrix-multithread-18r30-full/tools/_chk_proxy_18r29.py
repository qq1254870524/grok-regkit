from pathlib import Path
import re
# search proxy quality / socks5_list handling
files=['hybrid_register.py','grok_register_ttk.py','web/server.py']
# also find modules
for p in Path('.').rglob('*.py'):
    if 'venv' in str(p) or '.git' in str(p) or 'matrix_runs' in str(p) or 'backup' in str(p):
        continue
    try:
        t=p.read_text(encoding='utf-8',errors='ignore')
    except: continue
    if 'proxy_require_residential' in t or 'socks5_list' in t or 'proxy_quality' in t or 'proxy_list' in t:
        if p.name.startswith('_'): continue
        print('FILE', p)
        for i,l in enumerate(t.splitlines(),1):
            if any(k in l for k in ['proxy_require_residential','socks5_list','proxy_quality_check','proxy_list_file','reject_datacenter','pick_proxy','rotate_proxy','proxy_mode']):
                if 'def ' in l or 'if ' in l or 'proxy_' in l or 'socks' in l:
                    print(f'  {i}:{l[:140]}')
