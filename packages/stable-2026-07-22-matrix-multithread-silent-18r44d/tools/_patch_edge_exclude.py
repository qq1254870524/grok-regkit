from pathlib import Path
import re
p = Path(r'C:\Users\zhang\grok-regkit\grok_register_ttk.py')
t = p.read_text(encoding='utf-8')

# Fix _collect_script_chrome_pids body to only chrome.exe + DrissionPage, never edge
old = '''def _collect_script_chrome_pids(browser=None):
    """PIDs that belong to script Chromium only (never user Chrome)."""
    pids = set()
    browsers = []
    if browser is not None:
        browsers.append(browser)
    try:
        with _ACTIVE_BROWSERS_LOCK:
            browsers.extend([b for b in _ACTIVE_BROWSERS.values() if b is not None])
    except Exception:
        pass
    for b in browsers:
        rp = _browser_root_pid(b)
        if rp:
            pids |= _process_tree_pids(rp)
    # DrissionPage temp profile / remote debugging = script chrome only
    if sys.platform == "win32":
        try:
            import subprocess

            ps = (
                "Get-CimInstance Win32_Process -Filter \\"Name = 'chrome.exe'\\" | "
                "Where-Object { $_.CommandLine -like '*DrissionPage*' } | "
                "ForEach-Object { $_.ProcessId }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                timeout=8,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            for line in (out or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except Exception:
            pass
    return pids
'''

new = '''def _collect_script_chrome_pids(browser=None):
    """PIDs of script chrome.exe only. NEVER include Microsoft Edge/msedge."""
    pids = set()
    browsers = []
    if browser is not None:
        browsers.append(browser)
    try:
        with _ACTIVE_BROWSERS_LOCK:
            browsers.extend([b for b in _ACTIVE_BROWSERS.values() if b is not None])
    except Exception:
        pass
    for b in browsers:
        rp = _browser_root_pid(b)
        if rp:
            pids |= _process_tree_pids(rp)
    # Only Google Chrome automation profiles (DrissionPage). Never msedge.
    if sys.platform == "win32":
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if "msedge" in name:
                        continue
                    if name != "chrome.exe":
                        continue
                    cl = " ".join(proc.info.get("cmdline") or [])
                    if "DrissionPage" not in cl:
                        continue
                    pids.add(int(proc.info["pid"]))
                except Exception:
                    pass
        except Exception:
            pass
    return pids
'''

if old not in t:
    # try flexible: find function and replace until next def
    m = re.search(r'def _collect_script_chrome_pids\(browser=None\):.*?(?=\ndef )', t, re.S)
    if not m:
        raise SystemExit('collect not found')
    t = t[:m.start()] + new + '\n' + t[m.end():]
    print('replaced_via_regex')
else:
    t = t.replace(old, new, 1)
    print('replaced_exact')

# In silence loop, also skip if process name is msedge - add helper check after pid match
# Add note in _silence_browser_windows docstring already enough if pids never include edge

p.write_text(t, encoding='utf-8')
import ast
ast.parse(t)
print('engine_ok', 'msedge' in t and 'NEVER include Microsoft Edge' in t)