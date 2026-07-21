# -*- coding: utf-8 -*-
import sys
sys.dont_write_bytecode = True
import time, os
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'matrix_runs'
LOG = OUT / '_CODEX_18r43_EXT_SILENCE.log'
PIDF = OUT / '_ext_silence_18r43.pid'

def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    line = time.strftime('%Y-%m-%dT%H:%M:%S') + ' ' + str(msg)
    try:
        with LOG.open('a', encoding='utf-8') as f:
            f.write(line + chr(10))
    except Exception:
        pass

def once():
    import ctypes
    from ctypes import wintypes
    import psutil
    pids = set()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or '').lower()
            if name != 'chrome.exe':
                continue
            cl = ' '.join(proc.info.get('cmdline') or [])
            if 'DrissionPage' not in cl:
                continue
            pids.add(int(proc.info['pid']))
        except Exception:
            pass
    if not pids:
        return 0
    user32 = ctypes.windll.user32
    SW_SHOWMINNOACTIVE = 7
    HWND_BOTTOM = 1
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    IsWindowVisible = user32.IsWindowVisible
    GetClassNameW = user32.GetClassNameW
    ShowWindow = user32.ShowWindow
    SetWindowPos = user32.SetWindowPos
    IsIconic = user32.IsIconic
    n = 0
    def cb(hwnd, _lparam):
        nonlocal n
        try:
            if not IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) not in pids:
                return True
            cls = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, cls, 256)
            if cls.value not in ('Chrome_WidgetWin_1', 'Chrome_WidgetWin_0'):
                return True
            if IsIconic(hwnd):
                return True
            ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            SetWindowPos(hwnd, HWND_BOTTOM, -32000, 0, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            n += 1
        except Exception:
            pass
        return True
    EnumWindows(EnumWindowsProc(cb), 0)
    return n

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PIDF.write_text(str(os.getpid()), encoding='utf-8')
    log('start external silence keeper')
    ticks = 0
    while True:
        try:
            n = once()
            ticks += 1
            if n or ticks % 30 == 0:
                log('minimized_new=%s ticks=%s' % (n, ticks))
        except Exception as exc:
            log('err=%s' % exc)
        time.sleep(1.0)

if __name__ == '__main__':
    main()
