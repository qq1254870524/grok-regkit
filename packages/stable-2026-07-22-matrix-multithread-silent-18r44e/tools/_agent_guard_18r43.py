# -*- coding: utf-8 -*-
"""18r43 guard v2: reliable process detect, no duplicate watchers, never kill web job."""
from __future__ import annotations
import json, os, subprocess, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
LOG = OUT / "_CODEX_18r43_AGENT_GUARD.log"
STATUS = OUT / "_CODEX_18r43_AGENT_STATUS.md"
LOCK = OUT / "_agent_guard_18r43.pid"
PKG = ROOT / "packages" / "stable-2026-07-21-matrix-multithread-silent-18r43.zip"
START_PS1 = ROOT / "tools" / "start_matrix18r43_hidden.ps1"
PY = r"C:\Python312\python.exe"
PYW = r"C:\Python312\pythonw.exe"

# (marker substring in command line, relative script, use_pyw)
WATCHERS = [
    ("_supervisor_18r43_complete.py", "tools/_supervisor_18r43_complete.py", True),
    ("_finish_18r43_release.py", "tools/_finish_18r43_release.py", True),
    ("_pulse_18r43.py", "tools/_pulse_18r43.py", True),
    ("_agent_keep_18r43.py", "tools/_agent_keep_18r43.py", True),
    ("_watch_18r43_live.py", "tools/_watch_18r43_live.py", False),
    ("_health_18r43.py", "tools/_health_18r43.py", False),
    ("_longpoll_18r43.py", "tools/_longpoll_18r43.py", True),
    ("_silence_safe_drission.py", "tools/_silence_safe_drission.py", False),
]

_CMD_CACHE = {"ts": 0.0, "text": ""}


def log(msg: str) -> None:
    line = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + " " + msg
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def all_cmdlines() -> str:
    now = time.time()
    if now - _CMD_CACHE["ts"] < 15 and _CMD_CACHE["text"]:
        return _CMD_CACHE["text"]
    text = ""
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }",
            ],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
        text = out or ""
    except Exception as e:
        log("cmdline scan fail: %s" % e)
        text = ""
    _CMD_CACHE["ts"] = now
    _CMD_CACHE["text"] = text
    return text


def has_proc(marker: str) -> bool:
    return marker.lower() in all_cmdlines().lower()


def api():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)}


def start_py(rel: str, use_pyw: bool) -> None:
    exe = PYW if use_pyw else PY
    script = str(ROOT / rel)
    try:
        subprocess.Popen(
            [exe, "-B", script],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        log("started %s" % rel)
        _CMD_CACHE["ts"] = 0  # force refresh
    except Exception as e:
        log("start fail %s: %s" % (rel, e))


def ensure_watchers() -> None:
    for marker, rel, pyw in WATCHERS:
        if not has_proc(marker):
            log("missing %s -> start" % marker)
            start_py(rel, pyw)
            time.sleep(1)


def ensure_matrix() -> None:
    if has_proc("matrix_18r43_silent_stable_mt.py"):
        return
    if PKG.exists():
        return
    summaries = list(OUT.glob("matrix_18r43_*_summary.json"))
    st = api()
    if summaries and not st.get("running"):
        return
    log("matrix missing -> restart via start ps1")
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(START_PS1),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        _CMD_CACHE["ts"] = 0
    except Exception as e:
        log("matrix restart fail: %s" % e)


def write_status(st: dict, last_change: float) -> None:
    ok = st.get("success")
    stall = int((time.time() - last_change) / 60) if last_change else 0
    rem = max(0, 1000 - int(ok or 0))
    eta = int(rem / max(2.5, 1)) if rem else 0
    alert = "STALL_ALERT ok frozen %sm" % stall if (stall >= 25 and st.get("running")) else ""
    body = (
        "# 18r43 agent status\n"
        "updated=%s\n"
        "ok=%s fail=%s pend=%s await=%s run=%s phase=%s\n"
        "jobs=%s/%s stall_min=%s rem~%s eta_min~%s\n"
        "guard=v2 keep_alive matrix+watchers\n"
        "package_pending=stable-2026-07-21-matrix-multithread-silent-18r43\n"
        "%s\n"
    ) % (
        datetime.now().isoformat(timespec="seconds"),
        ok,
        st.get("fail"),
        st.get("pending_sso"),
        st.get("awaiting_pool"),
        st.get("running"),
        st.get("phase"),
        st.get("jobs_started"),
        st.get("jobs_finished"),
        stall,
        rem,
        eta,
        alert,
    )
    try:
        STATUS.write_text(body, encoding="utf-8")
    except Exception:
        pass


def already_running() -> bool:
    try:
        if not LOCK.is_file():
            return False
        pid = int(LOCK.read_text(encoding="utf-8").strip().split()[0])
        if pid == os.getpid():
            return False
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def main():
    if already_running():
        log("another guard alive; exit")
        return
    try:
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    log("guard v2 start pid=%s" % os.getpid())
    last_ok = None
    last_change = time.time()
    while True:
        try:
            ensure_watchers()
            ensure_matrix()
            st = api()
            ok = st.get("success")
            if ok is not None and ok != last_ok:
                last_ok = ok
                last_change = time.time()
            write_status(st, last_change)
            log(
                "ok=%s fail=%s pend=%s await=%s run=%s phase=%s zip=%s"
                % (
                    ok,
                    st.get("fail"),
                    st.get("pending_sso"),
                    st.get("awaiting_pool"),
                    st.get("running"),
                    st.get("phase"),
                    PKG.exists(),
                )
            )
            if PKG.exists() and list(OUT.glob("matrix_18r43_*_summary.json")) and not st.get("running"):
                log("COMPLETE package ready; exit")
                return
        except Exception as e:
            log("loop err: %s" % e)
        time.sleep(60)


if __name__ == "__main__":
    main()
