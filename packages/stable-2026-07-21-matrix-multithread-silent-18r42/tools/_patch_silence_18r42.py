# -*- coding: utf-8 -*-
from pathlib import Path
import re

p = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
text = p.read_text(encoding="utf-8")

# Locate function block by markers
start = text.find("def _browser_silent_enabled(cfg=None):")
end = text.find("\ndef create_browser_options(", start)
if start < 0 or end < 0:
    raise SystemExit(f"markers missing start={start} end={end}")

new_block = r'''def _browser_silent_enabled(cfg=None):
    """18r42: silent headed mode (Windows). Env GROK_BROWSER_SILENT overrides."""
    env = (os.environ.get("GROK_BROWSER_SILENT") or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        c = cfg if isinstance(cfg, dict) else (config if isinstance(config, dict) else {})
    except Exception:
        c = {}
    if "browser_silent" in c:
        return bool(c.get("browser_silent"))
    # default silent on Windows multi-thread to avoid focus theft
    return sys.platform == "win32"


_SILENCE_KEEPER_LOCK = threading.Lock()
_SILENCE_KEEPER_STOP = None
_SILENCE_KEEPER_THREAD = None
_SILENCE_SCRIPT_PIDS = set()  # only these PIDs may be minimized


def _browser_root_pid(browser):
    try:
        proc = getattr(browser, "process", None) or getattr(browser, "browser_process", None)
        if proc is not None and getattr(proc, "pid", None):
            return int(proc.pid)
    except Exception:
        pass
    return None


def _process_tree_pids(root_pid):
    """Return root + descendants (Windows Toolhelp)."""
    out = set()
    try:
        root_pid = int(root_pid)
    except Exception:
        return out
    out.add(root_pid)
    if sys.platform != "win32":
        return out
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == -1:
            return out
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        children = {}
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                pid = int(pe.th32ProcessID)
                ppid = int(pe.th32ParentProcessID)
                children.setdefault(ppid, []).append(pid)
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(snap)
        stack = [root_pid]
        while stack:
            cur = stack.pop()
            for ch in children.get(cur, []):
                if ch not in out:
                    out.add(ch)
                    stack.append(ch)
    except Exception:
        pass
    return out


def _collect_script_chrome_pids(browser=None):
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
                "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | "
                "Where-Object { $_.CommandLine -match 'DrissionPage\\\\userData|DrissionPage/userData' } | "
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


def _silence_browser_windows(browser=None, log_callback=None, only_pids=None):
    """Minimize SCRIPT Chrome only — never touch the user's normal browser.

    Headed silent mode (not headless) so CF/Turnstile still works.
    Without a PID whitelist this is a no-op (safe for user Chrome).
    """
    if sys.platform != "win32":
        return 0
    if not _browser_silent_enabled():
        return 0

    # Do NOT call DrissionPage mini() — it can activate/focus windows.

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_SHOWMINNOACTIVE = 7
        HWND_BOTTOM = 1
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010

        if only_pids is not None:
            pids = set(int(x) for x in only_pids)
        else:
            pids = _collect_script_chrome_pids(browser)
            with _SILENCE_KEEPER_LOCK:
                if pids:
                    _SILENCE_SCRIPT_PIDS.clear()
                    _SILENCE_SCRIPT_PIDS.update(pids)
                elif _SILENCE_SCRIPT_PIDS:
                    pids = set(_SILENCE_SCRIPT_PIDS)

        if not pids:
            # Safety: without PID whitelist, do nothing (avoids minimizing user Chrome)
            return 0

        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible = user32.IsWindowVisible
        GetClassNameW = user32.GetClassNameW
        ShowWindow = user32.ShowWindow
        SetWindowPos = user32.SetWindowPos
        IsIconic = user32.IsIconic

        targets = []

        def _cb(hwnd, _lparam):
            try:
                if not IsWindowVisible(hwnd):
                    return True
                pid = wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) not in pids:
                    return True  # leave user browser alone
                cls = ctypes.create_unicode_buffer(256)
                GetClassNameW(hwnd, cls, 256)
                cname = cls.value or ""
                if cname not in ("Chrome_WidgetWin_1", "Chrome_WidgetWin_0"):
                    return True
                targets.append(int(hwnd))
            except Exception:
                pass
            return True

        EnumWindows(EnumWindowsProc(_cb), 0)
        n = 0
        for hwnd in targets:
            try:
                ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
                SetWindowPos(
                    hwnd,
                    HWND_BOTTOM,
                    -32000,
                    0,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOACTIVATE,
                )
                if not IsIconic(hwnd):
                    ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
                n += 1
            except Exception:
                pass
        if log_callback and n and os.environ.get("GROK_SILENCE_VERBOSE"):
            log_callback(f"[*] 静默浏览器: 已最小化 {n} 个脚本窗口(不动用户Chrome)")
        return n
    except Exception as exc:
        if log_callback:
            log_callback(f"[Debug] 静默浏览器最小化失败: {exc}")
        return 0


def start_browser_silence_keeper(interval=1.2, log_callback=None):
    """Background re-minimize script Chrome only (page nav restores windows)."""
    global _SILENCE_KEEPER_STOP, _SILENCE_KEEPER_THREAD
    if sys.platform != "win32" or not _browser_silent_enabled():
        return False
    with _SILENCE_KEEPER_LOCK:
        if _SILENCE_KEEPER_THREAD is not None and _SILENCE_KEEPER_THREAD.is_alive():
            return True
        _SILENCE_KEEPER_STOP = threading.Event()
        stop_ev = _SILENCE_KEEPER_STOP

        def _loop():
            while not stop_ev.is_set():
                try:
                    _silence_browser_windows(browser=None, log_callback=None)
                except Exception:
                    pass
                stop_ev.wait(max(0.6, float(interval or 1.2)))

        t = threading.Thread(target=_loop, name="browser-silence-keeper", daemon=True)
        _SILENCE_KEEPER_THREAD = t
        t.start()
    if log_callback:
        log_callback("[*] 浏览器静默守护已启动: 仅最小化脚本Chrome, 不影响用户浏览器")
    return True


def stop_browser_silence_keeper(log_callback=None):
    global _SILENCE_KEEPER_STOP, _SILENCE_KEEPER_THREAD
    with _SILENCE_KEEPER_LOCK:
        if _SILENCE_KEEPER_STOP is not None:
            _SILENCE_KEEPER_STOP.set()
        _SILENCE_KEEPER_STOP = None
        _SILENCE_KEEPER_THREAD = None
        _SILENCE_SCRIPT_PIDS.clear()
    if log_callback:
        log_callback("[*] 浏览器静默守护已停止")


'''

text = text[:start] + new_block + text[end + 1 :]  # end points at \ndef...

needle = """            try:
                _silence_browser_windows(b, log_callback=log_callback)
            except Exception:
                pass
            if log_callback and sys.platform == \"win32\" and _browser_silent_enabled():
                log_callback(\"[*] 浏览器静默模式: headed+最小化/屏外 (不抢焦点, CF可用)\")
"""
repl = """            try:
                start_browser_silence_keeper(interval=1.0, log_callback=None)
                _silence_browser_windows(b, log_callback=log_callback)
            except Exception:
                pass
            if log_callback and sys.platform == \"win32\" and _browser_silent_enabled():
                log_callback(\"[*] 浏览器静默模式: headed+屏外+PID白名单守护 (只压脚本Chrome, CF可用)\")
"""
if needle not in text:
    raise SystemExit("START_HOOK_NOT_FOUND")
text = text.replace(needle, repl, 1)

fs = """def force_stop_registration(log_callback=None, reason=\"user_stop\"):
    \"\"\"Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA.\"\"\"
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    _lg(f\"[!] force_stop_registration: {reason}\")
"""
fs2 = """def force_stop_registration(log_callback=None, reason=\"user_stop\"):
    \"\"\"Immediate stop: kill all worker browsers. Does NOT stop G2A/Sub2API/CLIProxy/CPA.\"\"\"
    _lg = log_callback if callable(log_callback) else (lambda m: None)
    _lg(f\"[!] force_stop_registration: {reason}\")
    try:
        stop_browser_silence_keeper(log_callback=_lg)
    except Exception:
        pass
"""
if fs not in text:
    raise SystemExit("FORCE_STOP_NOT_FOUND")
text = text.replace(fs, fs2, 1)

p.write_text(text, encoding="utf-8")
# syntax check
import ast
ast.parse(text)
print("OK", p.stat().st_size)
print("has_keeper", "start_browser_silence_keeper" in text)
print("has_safe", "leave user browser alone" in text)
