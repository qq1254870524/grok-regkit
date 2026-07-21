from pathlib import Path
import re

p = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
t = p.read_text(encoding="utf-8")

new_fn = r'''def force_kill_registration_browsers(log_callback=None):
    """Kill leftover SCRIPT Chrome only. NEVER touch msedge/Edge/WebView2 (user browser).

    18r42 Edge-safe: do NOT match bare userData — Microsoft Edge always has --user-data-dir.
    Only chrome.exe / chromedriver.exe with script markers (DrissionPage / project paths).
    """
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    killed = []
    if sys.platform != "win32":
        return killed
    try:
        import subprocess

        # Never include msedge. Never match bare userData (kills personal Edge).
        ps = r"""
$pat = 'DrissionPage|\.chrome-data|grok-regkit|auto_port|accounts\.x\.ai'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|chromedriver)\.exe$' -and
    $_.CommandLine -and ($_.CommandLine -match $pat)
  } |
  ForEach-Object {
    try {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
      $_.ProcessId
    } catch {}
  }
"""
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stderr=subprocess.STDOUT,
            timeout=20,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        for line in (out or "").splitlines():
            line = line.strip()
            if line.isdigit():
                killed.append(int(line))
        # second pass — only chrome under project .chrome-data (never msedge)
        try:
            ps2 = r"""
$root = 'C:\Users\zhang\grok-regkit\.chrome-data'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|chromedriver)\.exe$' -and
    $_.CommandLine -and (
      $_.CommandLine -like ('*' + $root + '*') -or
      ($_.CommandLine -match 'DrissionPage' -and $_.CommandLine -match 'run-\d+-\d+-[0-9a-f]{4}')
    )
  } |
  ForEach-Object {
    try {
      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
      $_.ProcessId
    } catch {}
  }
"""
            out2 = subprocess.check_output(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps2],
                stderr=subprocess.STDOUT,
                timeout=20,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            for line in (out2 or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid not in killed:
                        killed.append(pid)
        except Exception as _e2:
            _lg(f"[!] force_kill second pass: {_e2}")
        if killed:
            _lg(f"[*] 已强制结束残留脚本 Chrome 进程(Edge-safe): {killed}")
        else:
            _lg("[*] 无匹配的残留脚本 Chrome 进程(Edge 不受影响)")
    except Exception as exc:
        _lg(f"[!] 强制结束浏览器失败: {exc}")
    return killed


'''

# Replace from def force_kill... through the next def after the broken region
m = re.search(
    r"def force_kill_registration_browsers\(log_callback=None\):.*?(?=\ndef force_stop_registration\()",
    t,
    re.S,
)
if not m:
    # fallback: next def after force_kill
    m = re.search(
        r"def force_kill_registration_browsers\(log_callback=None\):.*?(?=\ndef )",
        t,
        re.S,
    )
if not m:
    raise SystemExit("force_kill block not found")
print("matched", m.start(), m.end(), "len", m.end()-m.start())
# show a bit of what follows
print("AFTER:", repr(t[m.end():m.end()+80]))
t2 = t[:m.start()] + new_fn + t[m.end():]
# compile check
compile(t2, str(p), "exec")
p.write_text(t2, encoding="utf-8")
body = t2.split("def force_kill_registration_browsers")[1].split("def force_stop_registration")[0]
assert "msedge" not in body or "NEVER touch msedge" in body
assert "userData" not in body or "do NOT match bare userData" in body
assert "$pat = 'DrissionPage" in body
assert "$_.Name -match '^(chrome|chromedriver)" in body
assert "msedge|chromedriver" not in body
print("OK size", p.stat().st_size)
