from pathlib import Path
lines = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace").splitlines()
for s in [6405, 6520, 6720, 6780]:
    print("====", s, "====")
    for i in range(max(0, s - 1), min(len(lines), s + 90)):
        print(f"{i+1}:{lines[i][:200]}")
# multi-thread browser path
import re
text="\n".join(lines)
for m in re.finditer(r"def (run_.*browser|worker_|_browser_worker|register_one_browser|mt_.*reg)", text):
    print("FN", m.group(1), "at", text[:m.start()].count("\n")+1)
for pat in ["create_email_rate_limited", "max_mail_retry", "burn_mailbox"]:
    print(pat, [i+1 for i,l in enumerate(lines) if pat in l][:30])
