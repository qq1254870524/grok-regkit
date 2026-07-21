from pathlib import Path
lines = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace").splitlines()
for s in [6927, 6980, 7040, 7100, 7160]:
    print("====", s, "====")
    for i in range(max(0, s - 1), min(len(lines), s + 70)):
        print(f"{i+1}:{lines[i][:200]}")
