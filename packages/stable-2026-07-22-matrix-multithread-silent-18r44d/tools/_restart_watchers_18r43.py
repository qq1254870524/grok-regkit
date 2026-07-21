import subprocess, sys, time
from pathlib import Path
root = Path(r"C:\Users\zhang\grok-regkit")
tools = root / "tools"
runs = root / "matrix_runs"
pyw = Path(sys.executable).with_name("pythonw.exe")
if not pyw.exists():
    pyw = Path(r"C:\Python312\pythonw.exe")
pairs = [
    ("_pulse_18r43.py", "_pulse_18r43.pid"),
    ("_watch_18r43_live.py", "_watch_18r43_live.pid"),
    ("_agent_keep_18r43.py", "_agent_keep_18r43.pid"),
]
for script_name, pid_name in pairs:
    script = tools / script_name
    pidfile = runs / pid_name
    if not script.exists():
        print("missing", script)
        continue
    if pidfile.exists():
        old = pidfile.read_text(encoding="utf-8", errors="ignore").strip()
        if old.isdigit():
            try:
                import ctypes
                SYNCHRONIZE = 0x00100000
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(old))
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    print("skip", script_name, "alive", old)
                    continue
            except Exception:
                pass
    creationflags = 0x08000000  # CREATE_NO_WINDOW
    p = subprocess.Popen(
        [str(pyw), "-B", str(script)],
        cwd=str(root),
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pidfile.write_text(str(p.pid), encoding="ascii")
    print("started", script_name, "pid", p.pid)
print("done")
