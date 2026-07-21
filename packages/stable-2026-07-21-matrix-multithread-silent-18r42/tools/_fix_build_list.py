from pathlib import Path
p = Path('tools/_build_pkg_18r24.py')
t = p.read_text(encoding='utf-8')
if 'pending_sso_recovery.py' not in t:
    t = t.replace('"aol_mail.py",', '"aol_mail.py",\n    "pending_sso_recovery.py",', 1)
    p.write_text(t, encoding='utf-8')
    print('added double-quote form')
else:
    print('present')
for ln in p.read_text(encoding='utf-8').splitlines():
    if 'aol_mail' in ln or 'pending_sso_recovery.py' in ln:
        print(ln)
