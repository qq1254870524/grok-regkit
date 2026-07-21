from pathlib import Path
p = Path("tools/_agent_longmon_18r43.py")
t = p.read_text(encoding="utf-8")
t2 = t.replace("PIDS = [74480, 162152, 18728, 173000, 185528, 165072]", "PIDS = [85044, 162152, 18728, 173000, 185528, 165072]")
t2 = t2.replace('procs.get("74480")', 'procs.get("85044")')
# dynamic matrix pid from file
if "def matrix_pid" not in t2:
    t2 = t2.replace(
        "PIDS = [85044, 162152, 18728, 173000, 185528, 165072]",
        """def matrix_pid():
    try:
        return int((ROOT / "matrix_runs" / "_matrix_18r43.pid").read_text(encoding="utf-8").strip())
    except Exception:
        return 85044
PIDS_BASE = [162152, 18728, 173000, 185528, 165072]"""
    )
    t2 = t2.replace(
        "procs = {str(pid): alive(pid) for pid in PIDS}",
        "pids = [matrix_pid()] + list(PIDS_BASE)\n    procs = {str(pid): alive(pid) for pid in pids}"
    )
    t2 = t2.replace(
        'procs.get("85044"), procs.get("162152"), procs.get("18728")',
        'procs.get(str(matrix_pid())), procs.get("162152"), procs.get("18728")'
    )
p.write_text(t2, encoding="utf-8")
print("longmon updated")
