from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\tools\_silence_safe_drission.py")
t = p.read_text(encoding="utf-8")
# replace any match filter with like *DrissionPage*
import re
t2 = re.sub(r'-match\s+\'[^\']*DrissionPage[^\']*\'', r"-like '*DrissionPage*'", t)
p.write_text(t2, encoding="utf-8")
print("changed", t!=t2)
for line in t2.splitlines():
    if "Drission" in line or "script_pids" in line or "-like" in line:
        print(line)