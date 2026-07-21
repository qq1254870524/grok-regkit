# -*- coding: utf-8 -*-
import ctypes, time, re
from ctypes import wintypes
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\zhang\grok-regkit")
LOG = ROOT / "matrix_runs" / "_CODEX_SILENCE_18r42.log"
LOG.parent.mkdir(exist_ok=True)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
SW_SHOWMINNOACTIVE = 7
SW_MINIMIZE = 6
HWND_BOTTOM = 1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
IsWindowVisible = user32.IsWindowVisible
GetClassNameW = user32.GetClassNameW
GetWindowTextW = user32.GetWindowTextW
ShowWindow = user32.ShowWindow
SetWindowPos = user32.SetWindowPos
GetWindowLongW = user32.GetWindowLongW
SetWindowLongW = user32.SetWindowLongW
IsIconic = user32.IsIconic

TITLE_RE = re.compile(r"(Grok|x\.ai|accounts\.x\.ai|Cloudflare|Just a moment|Turnstile|挑战|人机验证)", re.I)

def silence_once():
    targets = []
    def cb(hwnd, _lp):
        try:
            if not IsWindowVisible(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, cls, 256)
            title = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, title, 512)
            cname = cls.value or ""
            tname = title.value or ""
            if cname not in ("Chrome_WidgetWin_1", "Chrome_WidgetWin_0"):
                return True
            # Only script-related titles — never generic "新标签页"/user browsing
            if not tname or not TITLE_RE.search(tname):
                return True
            targets.append((int(hwnd), tname[:80]))
        except Exception:
            pass
        return True
    EnumWindows(EnumWindowsProc(cb), 0)
    n = 0
    for hwnd, _t in targets:
        try:
            # Keep minimized without activating; also shove off-screen
            ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            SetWindowPos(hwnd, HWND_BOTTOM, -32000, 0, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            try:
                ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
                SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
            except Exception:
                pass
            if not IsIconic(hwnd):
                ShowWindow(hwnd, SW_MINIMIZE)
            n += 1
        except Exception:
            pass
    return n, len(targets)

last_log = 0
while True:
    try:
        n, total = silence_once()
        now = time.time()
        if now - last_log > 30:
            last_log = now
            msg = f"{datetime.now().isoformat(timespec='seconds')} silenced={n} matched={total}\n"
            with LOG.open("a", encoding="utf-8") as f:
                f.write(msg)
    except Exception as exc:
        try:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} err={exc}\n")
        except Exception:
            pass
    time.sleep(1.2)
