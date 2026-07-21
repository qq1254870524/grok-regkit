from pathlib import Path
import re
text = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace")
# find multithread browser registration
for pat in ["workers", "ThreadPool", "browser_worker", "run_multi", "mt_register", "register_worker", "worker_id", "w{"]:
    idxs=[]
    for i,l in enumerate(text.splitlines()):
        if pat in l and ("def " in l or "worker" in l.lower() or "thread" in l.lower() or "多线程" in l):
            idxs.append(i+1)
    if idxs:
        print(pat, idxs[:20])
lines=text.splitlines()
for i,l in enumerate(lines):
    if "全浏览器多线程" in l or "browser multi" in l.lower() or "def run_browser" in l or "def start_registration" in l or "def _worker_register" in l:
        print(i+1, l[:160])
# search hybrid multi
h=Path("hybrid_register.py").read_text(encoding="utf-8",errors="replace").splitlines()
for i,l in enumerate(h):
    if "create_email_rate_limited" in l or "fill_email_and_submit" in l or "max_mail_retry" in l:
        if i>5000:
            print("H", i+1, l[:160])
