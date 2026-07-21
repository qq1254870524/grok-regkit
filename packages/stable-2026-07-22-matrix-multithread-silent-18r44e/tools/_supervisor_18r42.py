# -*- coding: utf-8 -*-
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(r"C:/Users/zhang/grok-regkit")
OUT = ROOT / "matrix_runs"
LOG = OUT / "_CODEX_SUPERVISOR_18r42.log"
JSONL = OUT / "matrix_18r42_20260721_024738.jsonl"
CREATE_NO_WINDOW = 0x08000000
PY = r"C:/Python312/python.exe"

def ts():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def log(msg):
    line = "%s %s" % (ts(), msg)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)

def api_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=6) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"_error": str(e)}

def list_cmds():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        return [(int(x.get("ProcessId") or 0), str(x.get("CommandLine") or "")) for x in (data or [])]
    except Exception as e:
        log("list_cmds err %s" % e)
        return []

def has_cmd(token):
    t = token.lower().replace("/", "\\")
    for pid, cmd in list_cmds():
    if t in (cmd or "").lower().replace("/", "\\"):
        return True
    return False

def start_hidden(args):
    try:
        subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return True
    except Exception as e:
        log("start fail %s" % e)
        return False

def ensure():
    st = api_status()
    if ("_error" in st) and (not has_cmd("server.py")):
        log("restart web server 8092")
        start_hidden([PY, "-B", "web/server.py"])
        time.sleep(2)
   if not has_cmd("silence_safe"):
        log("
estart silence_safe")
        start_hidden([PY, "-B", "tools/_silence_safe_drission.py"])
    if not has_cmd("_watch_18r42"):
        log("restart watch")
        start_hidden([PY, "-B", "tools/_watch_18r42live.py"])
    if not has_cmd("matrix_18r42"):
        log("WARN matrix_18r42 process missing")

def chrome_counts():
    try:
        r = subprocess.run(["powershell","-NoProfile","-Command",
            "(Get-Process chrome -EA SilentlyContinue|Measure).Count; (Get-Process msedge -EA SilentlyContinue|Measure).Count"],
            capture_output=True, text=True, timeout=10)
        parts = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
       if len(parts) >= 2:
            return parts[0] + " " + parts[1]
        return (r.stdout or "").strip()
    except Exception:
        return "?"

def main():
    log("'supervisor v2 start edge_safe=1")
    last_jf = None
    while True:
        try:
            ensure()
            d = api_status()
            jf = d.get("jobs_finished"); js = d.get("hobs_started"); run = d.get("running")
            ok = d.get("success"); fail = d.get("fail"); pend = d.get("pending_sso"); phase = d.get("phase")
            event = str(d.get("last_event") or "")[:160]
            ce = chrome_counts()
            done = 0
           if JSONL.exists():
                done = len([x for x in JSONL.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()])
            log("cells=%s/12 js=%s jf=%s run=%s ok=%s fail=%s pend=%s phase=%s chrome_edge=%s event=%s" % (
                done, js, jf, run, ok, fail, pend, phase, ce, event))
           if last_jf is not None and jf is not None and jf != last_jf:
                log("jobs_finished advanced %s->%s" % (last_jf, jf))
            last_jf = jf
            if done >= 12 and (not run):
                log("ALL 12 CELLS DONE")
                time.sleep(20)
                if not api_status().get("running"):
                    log("'supervisor exit matrix complete")
                    return
            time.sleep(25)
        except Exception as e:
            log("loop err %s" % e)
            time.sleep(10)

if __name__ == "__main__":
    main()
