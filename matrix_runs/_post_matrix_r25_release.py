# -*- coding: utf-8 -*-
"""Wait weak matrix PID (Windows-safe), then package/release. Never kill mid-run."""
from __future__ import annotations
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
LOG = ROOT / "matrix_runs" / "_post_matrix_r25_release.log"
# Prefer live weak runner detection by cmdline, fallback WEAK_PID
WEAK_PID = 156952
TAGS = [
    ("stable-2026-07-19-outlook-sso-nudge-18r23", "18r23 Outlook strict post-send + browser SSO nudge", "stable-2026-07-19-outlook-sso-nudge-18r23.zip"),
    ("stable-2026-07-19-pending-rotate-18r24c", "18r24c profile timeout/classify/pending rotate", "stable-2026-07-19-pending-rotate-18r24c.zip"),
    ("stable-2026-07-19-nsfw-direct-18r25", "18r25 NSFW socks->direct + Outlook early 110s + reload", "stable-2026-07-19-nsfw-direct-18r25.zip"),
    ("stable-2026-07-19-sso-hold-signup-18r26", "18r26 browser SSO nudge hold on active signup form", "stable-2026-07-19-sso-hold-signup-18r26.zip"),
]

def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, cwd=None, check=False, timeout=600):
    log("$ " + " ".join(str(x) for x in cmd))
    try:
        p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except Exception as e:
        log(f"run exc: {e}")
        class R: pass
        r = R(); r.returncode=1; r.stdout=""; r.stderr=str(e); return r
    if p.stdout: log(p.stdout[-2000:])
    if p.stderr: log(p.stderr[-1200:])
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed {cmd}")
    return p

def pid_alive_win(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        s = (out or "").strip()
        if not s or s.lower().startswith("info:"):
            return False
        return str(pid) in s
    except Exception:
        return False

def find_weak_pids() -> list[int]:
    pids = []
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'matrix_rerun_weak_18r24' } | "
             "Select-Object -ExpandProperty ProcessId"],
            text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        for line in (out or "").splitlines():
            line=line.strip()
            if line.isdigit():
                pids.append(int(line))
    except Exception as e:
        log(f"find_weak_pids {e}")
    if WEAK_PID and pid_alive_win(WEAK_PID) and WEAK_PID not in pids:
        pids.append(WEAK_PID)
    return pids

def wait_weak(max_h: float = 10.0) -> None:
    deadline = time.time() + max_h * 3600
    while time.time() < deadline:
        pids = find_weak_pids()
        st = api_status()
        running = bool(st.get("running"))
        log(f"wait_weak pids={pids} 8092_running={running} phase={st.get('phase')}")
        if not pids and not running:
            # require two consecutive idle checks
            time.sleep(8)
            pids2 = find_weak_pids()
            st2 = api_status()
            if not pids2 and not st2.get("running"):
                log("weak idle confirmed")
                return
        time.sleep(20)
    log("wait_weak timeout continue")

def api_status():
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def stop_job():
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8092/api/stop", data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log(f"stop_job {e}")

def kill_8092_only():
    log("kill 8092 only")
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'web\\\\server.py|web/server.py' } | "
             "Select-Object -ExpandProperty ProcessId"],
            text=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except Exception as e:
        log(f"find 8092 {e}"); return
    for line in (out or "").splitlines():
        line=line.strip()
        if line.isdigit():
            pid=int(line)
            log(f"taskkill server pid={pid}")
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)

def start_8092():
    log("start 8092")
    ps1 = ROOT / "tools" / "start_web8092_hidden.ps1"
    if ps1.is_file():
        run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)])
    else:
        subprocess.Popen([sys.executable, "-B", "web/server.py"], cwd=str(ROOT),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    for _ in range(40):
        st = api_status()
        if st.get("ok"):
            log(f"8092 up ok running={st.get('running')}")
            return
        time.sleep(1)
    log(f"8092 start uncertain {api_status()}")

def build_pkg(tag: str, notes: str) -> Path:
    import shutil, zipfile
    pkg = ROOT / "packages" / tag
    files = [
        "hybrid_register.py","grok_register_ttk.py","pending_sso_recovery.py",
        "web/server.py","web/index.html","tools/matrix_cross_run.py",
        "tools/matrix_rerun_weak_18r24.py","tools/_build_pkg_18r24.py",
        "tools/start_web8092_hidden.ps1","outlook_mail.py","aol_mail.py",
        "browser/token_harvester.py","sub2api_client.py",
    ]
    if pkg.exists(): shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    for rel in files:
        src = ROOT / rel
        if src.is_file():
            dst = pkg / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (pkg / "CHANGELOG.md").write_text(f"# {tag}\n\n{notes}\n\nPath: register -> immediate SSO -> pool; pending fallback only.\nDo not overwrite older packages/releases.\n", encoding="utf-8")
    (pkg / "RESTORE.md").write_text(f"# Restore {tag}\n\n1. Stop only 8092\n2. Copy package files or git checkout {tag}\n3. python -B web/server.py\n4. Keep 8010/8080/8317/8318\n", encoding="utf-8")
    zpath = ROOT / "packages" / f"{tag}.zip"
    if zpath.exists(): zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pkg.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(pkg.parent))
    log(f"built {zpath} size={zpath.stat().st_size}")
    return zpath

def write_report():
    weak_dirs = sorted((ROOT/"matrix_runs").glob("matrix_18r24_weak_*"), key=lambda p: p.stat().st_mtime)
    if not weak_dirs: return
    latest = weak_dirs[-1]
    lines = []
    uniq = {}
    sf = latest/"summary.jsonl"
    if sf.is_file():
        for x in sf.read_text(encoding="utf-8", errors="replace").splitlines():
            if not x.strip(): continue
            r=json.loads(x); uniq[(r.get("cell"), r.get("round"))]=r
    report = latest/"REPORT.md"
    body = ["# Weak matrix 18r24/18r25 report", f"dir: `{latest}`", "", "| cell | round | class | ok | elapsed |", "|---|---:|---|:---:|---:|"]
    for (c,r),v in sorted(uniq.items(), key=lambda x:(str(x[0][0]), x[0][1] or 0)):
        body.append(f"| {c} | {r} | {v.get('class')} | {v.get('ok')} | {v.get('elapsed_s')} |")
    body += ["", "## Notes", "- Main path: register -> immediate SSO -> pool", "- Outlook true no-mail => pending/burn", "- 18r25: NSFW proxy fail -> direct; early_no_new 110s", ""]
    report.write_text("\n".join(body), encoding="utf-8")
    log(f"wrote {report}")

def git_release():
    notes24 = "18r24c profile timeout+classify+pending rotate+email log_callback"
    notes25 = (
        "18r25 NSFW enable: proxy fail -> direct fallback\n"
        "Outlook early_no_new_mail threshold 75s -> 110s\n"
        "8092 register hot-reload outlook/aol/sub2api/ttk/hybrid\n"
        "Windows-safe post watcher; matrix weak evidence\n"
    )
    p24 = ROOT/"packages"/"stable-2026-07-19-pending-rotate-18r24c"
    if not p24.is_dir():
        build_pkg("stable-2026-07-19-pending-rotate-18r24c", notes24)
    build_pkg("stable-2026-07-19-nsfw-direct-18r25", notes25)
    notes26 = (
        "18r26 browser SSO nudge: never navigate away while signup form still present\n"
        "pure signing-in dwell 18s before grok.com nudge\n"
        "18r25 NSFW proxy->direct + Outlook early 110s included\n"
    )
    build_pkg("stable-2026-07-19-sso-hold-signup-18r26", notes26)
    write_report()
    add = [
        "hybrid_register.py","grok_register_ttk.py","pending_sso_recovery.py",
        "web/server.py","web/index.html","tools/matrix_cross_run.py",
        "tools/matrix_rerun_weak_18r24.py","tools/_build_pkg_18r24.py",
        "outlook_mail.py","aol_mail.py","browser/token_harvester.py",
        "sub2api_client.py","packages/",
    ]
    run(["git","add","-A","--"]+add)
    st = run(["git","status","--porcelain"])
    if st.stdout.strip():
        run(["git","commit","-m","18r26: SSO hold on signup form; 18r25 NSFW direct; packages 18r24c+18r25+18r26"], check=False)
    else:
        log("nothing to commit")
    run(["git","push","mygithub","main"], check=False, timeout=180)
    for tag, title, zname in TAGS:
        ex = run(["git","tag","-l", tag])
        if tag not in (ex.stdout or ""):
            run(["git","tag","-a", tag, "-m", title], check=False)
        run(["git","push","mygithub", tag], check=False, timeout=120)
        chk = run(["gh","release","view", tag, "-R","qq1254870524/grok-regkit"])
        if chk.returncode == 0:
            log(f"release exists skip {tag}"); continue
        zf = ROOT/"packages"/zname
        notes = ROOT/"packages"/tag/"CHANGELOG.md"
        cmd = ["gh","release","create", tag, "-R","qq1254870524/grok-regkit","--title", title, "--latest=false"]
        if notes.is_file(): cmd += ["--notes-file", str(notes)]
        else: cmd += ["--notes", title]
        if zf.is_file(): cmd.append(str(zf))
        run(cmd, check=False, timeout=180)

def main():
    log("post_matrix_r25_release v2 start (windows-safe wait)")
    wait_weak()
    # ensure idle
    for _ in range(60):
        st = api_status()
        if not st.get("running") and not find_weak_pids():
            break
        if st.get("running"):
            # only stop if weak runner gone
            if not find_weak_pids():
                stop_job()
        time.sleep(2)
    kill_8092_only()
    time.sleep(2)
    start_8092()
    git_release()
    log("DONE post_matrix_r25_release v2")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL {e}")
        raise
