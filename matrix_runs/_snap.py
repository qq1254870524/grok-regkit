import json, urllib.request
from pathlib import Path
snap=json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/logs/snapshot?limit=800", timeout=20))
lines=snap.get("lines") or []
Path("matrix_runs/_snap_now.txt").write_text("\n".join(lines), encoding="utf-8")
# filter from 05:12
rec=[ln for ln in lines if "[05:12" in ln or "[05:13" in ln or "[05:14" in ln or "[05:15" in ln or "[05:16" in ln or "[05:17" in ln or "[05:18" in ln]
print("recent", len(rec))
for ln in rec:
    if any(k in ln for k in ["turnstile","force","mail_token","cache","re-register","error","密码","SSO","sso","hybrid","pre-rereg","cleared","already","bad_","auth","code","Verify","success","fail","reload"]):
        print(ln)
print("---LAST20---")
for ln in lines[-20:]:
    print(ln)
