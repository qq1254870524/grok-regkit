from pathlib import Path
lines = Path("grok_register_ttk.py").read_text(encoding="utf-8", errors="replace").splitlines()
for i in range(5040, 5120):
    print(f"{i+1}:{lines[i]}")
print("--- gate def ---")
for i,l in enumerate(lines):
    if "CREATE_EMAIL" in l or "wait_create_email" in l or "18r35c" in l:
        print(f"{i+1}:{l[:160]}")
