# -*- coding: utf-8 -*-
import json, time, urllib.request, pathlib, subprocess, sys
sys.dont_write_bytecode = True
ROOT = pathlib.Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "_CODEX_18r43_LONGMON.md"
JSONL = ROOT / "matrix_runs" / "_CODEX_18r43_LONGMON.jsonl"
HB = ROOT / "matrix_runs" / "_CODEX_18r43_AGENT_HEARTBEAT.md"
def matrix_pid():
    try:
        return int((ROOT / "matrix_runs" / "_matrix_18r43.pid").read_text(encoding="utf-8").strip())
    except Exception:
        return 85044
PIDS_BASE = [23304, 18728, 173000, 185528, 165072]

def status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=4) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        return {"error": str(e), "running": False}

def alive(pid):
    try:
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, timeout=5, creationflags=0x08000000)
        return str(pid) in out
    except Exception:
        return False

def counts():
    try:
        out = subprocess.check_output(["tasklist"], text=True, timeout=8, creationflags=0x08000000)
        ch = out.lower().count("chrome.exe")
        ed = out.lower().count("msedge.exe")
        return ch, ed
    except Exception:
        return -1, -1

prev = None
stall = 0
while True:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    s = status()
    ok = s.get("success", s.get("ok"))
    fail = s.get("fail")
    pend = s.get("pending_sso", s.get("pend"))
    awaitp = s.get("awaiting_pool", s.get("pending_pool"))
    phase = s.get("phase")
    run = bool(s.get("running"))
    ch, ed = counts()
    pids = [matrix_pid()] + list(PIDS_BASE)
    procs = {str(pid): alive(pid) for pid in pids}
    if prev is not None and ok == prev and run:
        stall += 1
    else:
        stall = 0
    prev = ok
    row = {"ts": ts, "ok": ok, "fail": fail, "pend": pend, "await": awaitp, "phase": phase, "run": run, "chrome": ch, "edge": ed, "stall": stall, "procs": procs}
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    pkg = (ROOT / "packages" / "stable-2026-07-21-matrix-multithread-silent-18r43.zip").exists()
    ev = (s.get("last_event") or "")
    import re as _re
    ev = _re.sub(r"(?i)(?:socks5h?|https?)://\S+", "***proxy***", ev)
    ev = _re.sub(r"(?i)(?:access_token|refresh_token|mail_token)=\S+", "***token***", ev)
    ev = ev[:160]
    OUT.write_text("# 18r43 LONGMON\nupdated=%s\nok=%s fail=%s pend=%s await=%s phase=%s run=%s\nchrome=%s edge=%s stall=%s package=%s\nprocs=%s\nevent=%s\n" % (ts, ok, fail, pend, awaitp, phase, run, ch, ed, stall, pkg, procs, ev), encoding="utf-8")
    HB.write_text("# 18r43 AGENT HEARTBEAT\nupdated=%s\nagent=longmon\nstatus=monitoring\nlast_poll=ok=%s fail=%s pend=%s await=%s phase=%s\nchrome=%s edge=%s package=%s stall=%s\nmatrix=%s web=%s super=%s\nnotes=longmon 20s Edge-safe\n" % (ts, ok, fail, pend, awaitp, phase, ch, ed, pkg, stall, procs.get(str(matrix_pid())), procs.get("23304"), procs.get("18728")), encoding="utf-8")
    if pkg:
        break
    time.sleep(20)
