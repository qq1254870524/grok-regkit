from pathlib import Path
# web server job path
lines=Path('web/server.py').read_text(encoding='utf-8').splitlines()
for i in range(560, 720):
    if i-1 < len(lines):
        print(f'{i}:{lines[i-1]}')
print('==== register mode dispatch ====')
lines2=Path('grok_register_ttk.py').read_text(encoding='utf-8').splitlines()
for i in range(5840, 5950):
    if i-1 < len(lines2):
        print(f'{i}:{lines2[i-1]}')
