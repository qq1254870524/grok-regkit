from pathlib import Path
p = Path(r"C:/Users/zhang/grok-regkit/tools/_finish_18r43_release.py")
t = p.read_text(encoding="utf-8")
needle = '"tools/matrix_18r43_silent_stable_mt.py", "tools/package_18r43_silent.py",'
insert = (
    '"tools/matrix_18r43_silent_stable_mt.py", "tools/package_18r43_silent.py",\n'
    '        "tools/start_matrix18r43_hidden.ps1", "tools/_supervisor_18r43_complete.py", '
    '"tools/_agent_keep_18r43.py",'
)
if "start_matrix18r43_hidden" in t:
    print("already")
elif needle in t:
    p.write_text(t.replace(needle, insert), encoding="utf-8")
    print("patched")
else:
    print("needle missing")
