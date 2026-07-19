from pathlib import Path
import re
files=['hybrid_register.py','grok_register_ttk.py','web/server.py','browser/token_harvester.py']
for f in files:
    p=Path(f)
    if not p.exists():
        print('missing', f)
        continue
    t=p.read_text(encoding='utf-8', errors='replace')
    hits=[]
    for i,l in enumerate(t.splitlines(),1):
        if re.search(r"register_mode|mode == .browser|full.?browser|def register_one|job_kind", l):
            hits.append(f"{i}:{l.strip()[:160]}")
    if hits:
        print('FILE', f, 'hits', len(hits))
        for h in hits[:30]:
            print(h)
        print('---')
