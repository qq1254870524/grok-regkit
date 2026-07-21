import psutil, subprocess, time, os, urllib.request
for p in list(psutil.process_iter(["pid", "cmdline"])):
    try:
        cl = " ".join(p.info.get("cmdline") or [])
    except Exception:
        continue
    if "silence_safe" in cl or "silence_grok" in cl or "_watch_18r42" in cl:
        print("kill", p.pid)
        try:
            p.kill()
        except Exception as e:
            print(e)
k = 0
for p in list(psutil.process_iter(["pid", "name", "cmdline"])):
    try:
        name = (p.info.get("name") or "").lower()
        if name != "chrome.exe":
            continue
        cl = " ".join(p.info.get("cmdline") or [])
        if "DrissionPage" in cl:
            p.kill()
            k += 1
    except Exception:
        pass
print("killed_script_chrome", k)
edge = chrome = dr = 0
for p in psutil.process_iter(["name", "cmdline"]):
    try:
        n = (p.info.get("name") or "").lower()
        cl = " ".join(p.info.get("cmdline") or [])
        if "msedge.exe" == n:
            edge += 1
        if n == "chrome.exe":
            chrome += 1
            if "DrissionPage" in cl:
                dr += 1
    except Exception:
        pass
print("edge", edge, "chrome", chrome, "drission", dr)
edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.isfile(edge_exe):
    subprocess.Popen([edge_exe, "--new-window", "about:blank"])
    print("edge_launched")
web_up = False
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cl = " ".join(p.info.get("cmdline") or [])
        if "web\\server.py" in cl or "web/server.py" in cl:
            web_up = True
            print("web_pid", p.pid)
    except Exception:
        pass
if not web_up:
    subprocess.Popen(
        [r"C:\Python312\python.exe", "-B", r"web\server.py"],
        cwd=r"C:\Users\zhang\grok-regkit",
        creationflags=0x08000000,
    )
    print("web_started")
    time.sleep(2)
try:
    print(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode()[:200])
except Exception as e:
    print("api", e)