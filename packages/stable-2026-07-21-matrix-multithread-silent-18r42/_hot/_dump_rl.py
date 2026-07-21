from pathlib import Path
lines = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace").splitlines()
for s in [4652, 5040, 5085, 6360, 6700]:
    print("====", s, "====")
    for i in range(max(0, s - 1), min(len(lines), s + 50)):
        print(f"{i+1}:{lines[i][:180]}")
print("==== hybrid handle ====")
h = Path("hybrid_register.py").read_text(encoding="utf-8", errors="replace").splitlines()
for s in [1002, 2440, 2620]:
    print("==== hybrid", s, "====")
    for i in range(max(0, s - 1), min(len(h), s + 60)):
        print(f"{i+1}:{h[i][:180]}")
