from pathlib import Path
lines = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace").splitlines()
for s in [7000, 7020, 7040, 7060, 7080]:
    print("====", s, "====")
    for i in range(max(0, s - 1), min(len(lines), s + 40)):
        print(f"{i+1}:{lines[i][:200]}")
# hybrid handle body
h = Path("hybrid_register.py").read_text(encoding="utf-8", errors="replace").splitlines()
print("==== hybrid handle_create_email_rate_limited ====")
for i in range(1001, 1085):
    print(f"{i+1}:{h[i][:200]}")
