"""Build non-overwriting package+release for 18r23 when called."""
import os, sys, shutil, subprocess, zipfile, time
from pathlib import Path
from datetime import datetime

ROOT = Path(r'C:\Users\zhang\grok-regkit')
os.chdir(ROOT)
TAG = 'stable-2026-07-19-outlook-sso-nudge-18r23'
PKG = ROOT / 'packages' / TAG
if PKG.exists():
    shutil.rmtree(PKG)

files = [
    'hybrid_register.py', 'outlook_mail.py', 'grok_register_ttk.py', 'aol_mail.py',
    'tools/matrix_cross_run.py', 'docs/CPA_AUTH_JSON_FORMAT.md',
    'web/server.py', 'web/index.html', 'sso_to_auth_json.py',
    'browser/token_harvester.py', 'AGENT_COORD.md',
]
# optional
for opt in ['cpa_export.py', 'CHANGELOG.md', 'README.md']:
    if (ROOT/opt).exists():
        files.append(opt)

PKG.mkdir(parents=True, exist_ok=True)
copied=[]
for rel in files:
    src = ROOT/rel
    if not src.exists():
        print('skip missing', rel)
        continue
    dst = PKG/rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(rel)

changelog = f'''# {TAG}

Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
Restore-point package 18r23 (does NOT overwrite 18r20/18r21/18r22).

## Changes
### 18r21
- Outlook early_no_new_mail: Graph 75s no post-send mail -> early burn/switch
- seen_new_after_send init fix

### 18r22
- hybrid VerifyEmail SOCKS5/proxy timeout retry (up to 3, 45/60/75s)

### 18r23
- Outlook strict post-send code window (since_ts-20s); baseline skip pre-send xAI codes
- Outlook form action `#`/empty -> urlPost/page URL (fix MissingSchema identity/confirm)
- browser success path calls mark_outlook_registered (prevent mailbox reuse + old code)

### 18r23b
- wait_for_sso_cookie: signing-in page nudge navigate grok.com/accounts.x.ai to mint SSO
- browser SSO timeout after profile submit -> pending_sso burn (not silent lose)

## Main path unchanged
register -> immediate SSO -> pool; pending only fallback.

## Matrix note
See matrix_runs/matrix_18r21_* summary for cross-run results.
'''
(PKG/'CHANGELOG_18r23.md').write_text(changelog, encoding='utf-8')
(PKG/'RESTORE.md').write_text(
    f'''# Restore {TAG}

1. Stop only grok-regkit web 8092 (do not kill 8010/8080/8317/8318).
2. Copy files from this package over `C:\\Users\\zhang\\grok-regkit` (or checkout tag).
3. Start: `python -B web/server.py`
4. Keep Sub2API/g2a/CLIProxy/cpa_gateway running.

Files included:
''' + '\n'.join(f'- {c}' for c in copied) + '\n',
    encoding='utf-8',
)

zip_path = ROOT/'packages'/f'{TAG}.zip'
if zip_path.exists():
    zip_path.unlink()
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in PKG.rglob('*'):
        if f.is_file():
            z.write(f, f.relative_to(PKG.parent).as_posix())
print('package dir', PKG)
print('zip', zip_path, zip_path.stat().st_size)
print('files', len(copied))
