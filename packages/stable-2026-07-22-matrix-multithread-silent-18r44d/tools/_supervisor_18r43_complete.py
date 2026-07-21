# -*- coding: utf-8 -*-
from __future__ import annotations
import json, time, subprocess, sys, traceback, os
from pathlib import Path
from datetime import datetime
import urllib.request
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
LOG = OUT / "_CODEX_18r43_SUPERVISOR.log"
ERR = OUT / "_CODEX_18r43_SUPERVISOR.err"
PIDF = OUT / "_matrix_18r43.pid"
PKG = ROOT / "packages" / "stable-2026-07-21-matrix-multithread-silent-18r43.zip"
STATE = OUT / "_CODEX_18r43_SUPERVISOR_STATE.json"
SELF_PID = OUT / "_supervisor_18r43.pid"
START_PS1 = ROOT / "tools" / "start_matrix18r43_hidden.ps1"

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

def api_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)}

def matrix_proc_alive() -> bool:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'matrix_18r43_silent_stable_mt' }).Count"],
            text=True, encoding="utf-8", errors="ignore", timeout=15,
        )
        return int((out or "0").strip().splitlines()[-1] or 0) > 0
    except Exception:
        return False

def matrix_alive() -> bool:
    try:
        if not PIDF.exists():
            return matrix_proc_alive()
        pid = int(PIDF.read_text(encoding="utf-8").strip().split()[0])
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)
        if h:
            k.CloseHandle(h)
            return True
        return matrix_proc_alive()
    except Exception as e:
        log("matrix_alive err: %s" % e)
        return matrix_proc_alive()

def find_summary():
    files = sorted(OUT.glob("matrix_18r43_*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def restart_matrix():
    if not START_PS1.is_file():
        log("restart_matrix missing start ps1")
        return False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_PS1)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        log("restart_matrix rc=%s out=%s" % (r.returncode, (r.stdout or "")[-300:]))
        return r.returncode == 0
    except Exception as e:
        log("restart_matrix fail: %s" % e)
        return False

def main():
    try:
        SELF_PID.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    log("supervisor start pid=%s (18r43e auto-resume matrix)" % os.getpid())
    dead_ticks = 0
    while True:
        try:
            st = api_status()
            alive = matrix_alive()
            board = OUT / "_CODEX_MATRIX_18r43_BOARD.md"
            progress = ""
            if board.exists():
                for line in board.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("progress="):
                        progress = line.strip()
            summary = find_summary()
            if not alive:
                dead_ticks += 1
            else:
                dead_ticks = 0
            if (not alive) and (not summary) and (not PKG.exists()) and dead_ticks >= 2:
                log("ALERT matrix dead ticks=%s; restarting with resume-capable script" % dead_ticks)
                if restart_matrix():
                    dead_ticks = 0
                    time.sleep(5)
                else:
                    log("matrix restart failed")
            log(
                "matrix_alive=%s job_running=%s ok=%s fail=%s pend=%s await=%s %s summary=%s dead_ticks=%s"
                % (alive, st.get("running"), st.get("success"), st.get("fail"), st.get("pending_sso"),
                   st.get("awaiting_pool"), progress, bool(summary), dead_ticks)
            )
            if summary and (not st.get("running")) and (not PKG.exists()):
                log("matrix complete summary=%s; packaging..." % summary.name)
                try:
                    r = subprocess.run(
                        [sys.executable, "-B", str(ROOT / "tools" / "package_18r43_silent.py")],
                        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                    )
                    log("package rc=%s out=%s err=%s" % (r.returncode, (r.stdout or "")[-500:], (r.stderr or "")[-300:]))
                except Exception as e:
                    log("package fail: %s" % e)
                STATE.write_text(json.dumps({"done": True, "summary": str(summary), "ts": time.time()}, indent=2), encoding="utf-8")
                log("supervisor exit after package attempt")
                return
            if summary and PKG.exists():
                log("already packaged; exit")
                return
        except Exception:
            try:
                ERR.write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
            log("loop error: %s" % traceback.format_exc().splitlines()[-1])
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            ERR.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        raise
