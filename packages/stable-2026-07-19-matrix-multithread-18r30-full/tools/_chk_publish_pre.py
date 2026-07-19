from pathlib import Path
import subprocess, os
# companion repos
for p in [r'C:\Users\zhang\grok-regkit-services', r'C:\Users\zhang\sub2api-src', r'C:\Users\zhang\grok-regkit-services1\grok2api1']:
    pp=Path(p)
    print('==', p, 'exists', pp.exists())
    if (pp/'.git').exists():
        os.chdir(pp)
        print(subprocess.check_output(['git','status','-sb'], text=True, errors='replace')[:500])
        print(subprocess.check_output(['git','remote','-v'], text=True, errors='replace')[:300])
        print('tags', subprocess.check_output(['git','tag','--sort=-creatordate'], text=True, errors='replace').splitlines()[:5])
    elif pp.exists():
        print('no git', list(pp.iterdir())[:8])
os.chdir(r'C:\Users\zhang\grok-regkit')
# packages dir
pkg=Path('packages')
if pkg.exists():
    items=sorted(pkg.iterdir(), key=lambda x:x.stat().st_mtime, reverse=True)[:12]
    for i in items:
        print('PKG', i.name, i.stat().st_size)
else:
    print('no packages dir')
# gh auth
try:
    print(subprocess.check_output(['gh','auth','status'], text=True, errors='replace')[:800])
except Exception as e:
    print('gh', e)
