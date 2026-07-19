# -*- coding: utf-8 -*-
"""After matrix_18r21 finishes: restart 8092 only, rerun weak cells with 18r24 code, build package flag."""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
MATRIX_PID = 154288
OUT_LOG = ROOT / "matrix_runs" / "_post_matrix_r24_actions.log"
DONE = ROOT / "matrix_runs" / "_matrix_r24_pipeline.flag"
OLD_DONE = ROOT / "matrix_runs" / "_matrix_done.flag"

def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with OUT_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def pid_alive(pid: int) -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        return str(pid) in (r.stdout or "")
    except Exception:
        return False

def api(method: str, path: str, body=None, timeout=20):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:8092{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw

def wait_idle(timeout=90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            code, st = api("GET", "/api/status", timeout=8)
            if code == 200 and not st.get("running"):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False

def restart_8092():
    log("restart 8092 only (keep 8010/8080/8317/8318)")
    # stop job first
    try:
        api("POST", "/api/stop", {})
    except Exception as e:
        log(f"stop api ignore: {e}")
    time.sleep(2)
    # kill only 8092 listeners
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15)
        pids = set()
        for line in (r.stdout or "").splitlines():
            if "LISTENING" in line and ":8092" in line:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            if pid.isdigit():
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, timeout=10)
                log(f"killed 8092 pid={pid}")
    except Exception as e:
        log(f"kill 8092 err: {e}")
    time.sleep(2)
    # start hidden
    ps1 = ROOT / "tools" / "start_web8092_hidden.ps1"
    if ps1.exists():
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # fallback
        subprocess.Popen(
            [sys.executable, "-B", "web/server.py"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    # wait health
    for i in range(40):
        try:
            code, st = api("GET", "/api/status", timeout=5)
            if code == 200:
                log(f"8092 up after restart i={i} running={st.get('running')}")
                return True
        except Exception:
            time.sleep(1)
    log("8092 failed to come up")
    return False

def main():
    log("post_matrix_r24 pipeline waiting for matrix pid 154288...")
    while pid_alive(MATRIX_PID):
        time.sleep(15)
    log("matrix pid ended")
    time.sleep(5)
    # also wait post_matrix_r23 if still running
    log("ensure idle then restart 8092 for 18r24 code")
    wait_idle(30)
    if not restart_8092():
        DONE.write_text("fail_restart\n", encoding="utf-8")
        return 1

    # launch supplemental matrix 2 rounds for weak cells only via existing runner flags if any
    # Use matrix_cross_run with env or a focused script
    supp = ROOT / "tools" / "matrix_rerun_weak_18r24.py"
    if not supp.exists():
        log("missing matrix_rerun_weak_18r24.py")
        DONE.write_text("missing_rerun_script\n", encoding="utf-8")
        return 2
    log("start weak-cell rerun 18r24")
    proc = subprocess.Popen(
        [sys.executable, "-B", str(supp)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log(f"weak rerun pid={proc.pid}")
    proc.wait()
    log(f"weak rerun exit={proc.returncode}")
    DONE.write_text(
        json.dumps({"finished": datetime.now().isoformat(), "rerun_rc": proc.returncode}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OLD_DONE.write_text("matrix+r24 pipeline done\n", encoding="utf-8")
    log("pipeline done")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
