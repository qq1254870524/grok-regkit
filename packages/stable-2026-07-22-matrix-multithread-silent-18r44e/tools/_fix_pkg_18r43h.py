from pathlib import Path
import ast
import re
p = Path(r"C:\Users\zhang\grok-regkit\tools\package_18r43_silent.py")
t = p.read_text(encoding="utf-8")
pat = re.compile(
    r'"- 18r43g: register count is SUCCESS target \(pending/fail no longer end job early\)\s*\n\s*- 18r43h:[^"]*"',
    re.M,
)
if pat.search(t):
    rep = (
        '"- 18r43g: register count is SUCCESS target (pending/fail no longer end job early)",\n'
        '        "- 18r43h: post_success task_done guard + auto-replace dead drain workers (awaiting_pool)"'
    )
    t = pat.sub(rep, t, count=1)
    print("replaced_broken_block")
elif "- 18r43h:" not in t:
    needle = '"- 18r43g: register count is SUCCESS target (pending/fail no longer end job early)",'
    if needle not in t:
        raise SystemExit("needle missing")
    t = t.replace(
        needle,
        needle + "\n        \"- 18r43h: post_success task_done guard + auto-replace dead drain workers (awaiting_pool)\",",
        1,
    )
    print("inserted_18r43h")
else:
    print("already_present")
ast.parse(t)
p.write_text(t, encoding="utf-8")
print("pkg_compile_ok")