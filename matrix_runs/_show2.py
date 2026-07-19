from pathlib import Path
t = Path("pending_sso_recovery.py").read_text(encoding="utf-8")
start = t.find("forced_mail_token = str(item.get(\"mail_token\")")
print(t[start:start+2500])
