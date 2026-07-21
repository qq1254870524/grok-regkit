# -*- coding: utf-8 -*-
# SAFE silence: only chrome.exe + DrissionPage. NEVER msedge/Edge/WebView2.
import ctypes, time
from ctypes import wintypes
from pathlib import Path
from datetime import datetime
try:
    import psutil
except Exception:
    psutil = None
ROOT = Path(r'C:\Users\zhang\grok-regkit')
LOG = ROOT / 'matrix_runs' / '_CODEX_SILENCE_SAFE.log'
LOG.parent.mkdir(exist_ok=True)
user32 = ctypes.windll.user32
SW_SHOWMINNOACTIVE = 7
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
IsWindowVisible = user32.IsWindowVisible
GetClassNameW = user32.GetClassNameW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
ShowWindow = user32.ShowWindow
SetWindowPos = user32.SetWindowPos

def script_chrome_pids():
    s = set()
    if psutil is None:
        return s
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (p.info.get('name') or '').lower()
            if 'msedge' in name:
                continue
            if name != 'chrome.exe':
                continue
            cl = ' '.join(p.info.get('cmdline') or [])
            if 'DrissionPage' not in cl:
                continue
            s.add(int(p.info['pid']))
        except Exception:
            pass
    return s

def silence(pids):
    if not pids:
        return 0
    targets = []
    def cb(hwnd, _lp):
        try:
            if not IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) not in pids:
                return True
            cls = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, cls, 256)
            if (cls.value or '') not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            targets.append(int(hwnd))
        except Exception:
            pass
        return True
    EnumWindows(EnumWindowsProc(cb), 0)
    n = 0
    for hwnd in targets:
        try:
            ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            SetWindowPos(hwnd, HWND_BOTTOM, -32000, 0, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            n += 1
        except Exception:
            pass
    return n

last = 0
while True:
    try:
        pids = script_chrome_pids()
        n = silence(pids)
        now = time.time()
        if now - last > 15:
            last = now
            with LOG.open('a', encoding='utf-8') as f:
                f.write('%s script_chrome_pids=%s silenced=%s edge_safe=1\n' % (
                    datetime.now().isoformat(timespec='seconds'), len(pids), n))
    except Exception as exc:
        try:
            with LOG.open('a', encoding='utf-8') as f:
                f.write('%s err=%s\n' % (datetime.now().isoformat(), exc))
        except Exception:
            pass
    time.sleep(1.2)
