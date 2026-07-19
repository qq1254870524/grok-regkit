from pathlib import Path
import ast
p = Path("pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")
start = t.find("forced_mail_token = str(item.get(\"mail_token\")")
print("start", start)
print(t[start:start+1800])
print("---AST---")
try:
    ast.parse(t)
    print("OK")
except SyntaxError as e:
    print(e)
    lines=t.splitlines()
    for i in range(e.lineno-5, e.lineno+8):
        if 0<i<=len(lines):
            print(f"{i}: {lines[i-1]}")
