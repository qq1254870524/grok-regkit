from pathlib import Path
import re
t = Path("tools/matrix_cross_run.py").read_text(encoding="utf-8")
print("--- CELLS names ---")
for m in re.finditer(r'"name":\s*"([^"]+)"', t):
    print(m.group(1))
print("--- key consts ---")
for line in t.splitlines():
    s=line.strip()
    if s.startswith("ROUNDS") or s.startswith("PENDING") or s.startswith("JOB_TIMEOUT") or s.startswith("OUT"):
        print(s[:140])
print("--- proxy files ---")
for p in Path('.').glob('*proxy*'):
    print(p, p.stat().st_size if p.is_file() else 'dir')
for p in [Path('socks5_proxies.txt'), Path('proxies.txt'), Path('data/socks5.txt')]:
    if p.exists():
        lines=[x.strip() for x in p.read_text(encoding='utf-8', errors='ignore').splitlines() if x.strip() and not x.strip().startswith('#')]
        print(p, 'lines', len(lines), 'sample', lines[:2])
print('--- outlook markers ---')
om=Path('outlook_mail.py').read_text(encoding='utf-8', errors='ignore')
for key in ['identity_confirm_blocked','errcode=1078','permanent']:
    print(key, om.count(key))
