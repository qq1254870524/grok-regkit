from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\tools\matrix_18r43_silent_stable_mt.py")
t = p.read_text(encoding="utf-8")
old = 'attach_first = bool(live.get("running") and start_idx == 0)'
new = 'attach_first = bool(live.get("running"))  # 18r43j: attach mid-cell even if start_idx>0'
if old not in t:
    raise SystemExit("anchor missing")
t = t.replace(old, new, 1)
if t.startswith("# 18r43i:"):
    t = "# 18r43j: resume attach mid-cell even when start_idx>0\n" + t
p.write_text(t, encoding="utf-8")
print("ok", p.stat().st_size)
