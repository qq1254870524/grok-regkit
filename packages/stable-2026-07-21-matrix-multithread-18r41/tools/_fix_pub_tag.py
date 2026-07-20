from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\tools\_auto_publish_18r29.py")
t = p.read_text(encoding="utf-8")
t2 = t.replace('run(["git", "tag", "-f", TAG], check=False)  # only if new - refuse if want never force? use without -f first\n', "")
t2 = t2.replace("# actually never force overwrite tag\n", "")
if t2 != t:
    p.write_text(t2, encoding="utf-8")
    print("patched ok")
else:
    print("no change")
    if "-f" in t and "tag" in t:
        for i,line in enumerate(t.splitlines(),1):
            if "tag" in line and "-f" in line:
                print(i, line)
