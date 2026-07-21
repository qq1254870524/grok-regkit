from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\hybrid_register.py")
lines = p.read_text(encoding="utf-8").splitlines()
fixed = 0
for i, l in enumerate(lines):
    if "keep browser_sent=0 dual_send_lock=0 allow protocol-rescue" in l:
        lines[i] = '                        f"-- keep browser_sent=0 dual_send_lock=0 allow protocol-rescue path"'
        fixed += 1
        print("fixed", i + 1)
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("count", fixed)