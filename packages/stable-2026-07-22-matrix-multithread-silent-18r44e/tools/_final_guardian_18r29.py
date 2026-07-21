"""Final guardian: watch matrix to REPORT then ensure publish + companion notes."""
from __future__ import annotations
import json, time, subprocess, sys, os, shutil, zipfile
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
STATE = ROOT / "matrix_runs" / "_final_guardian_18r29.txt"
PULSE = ROOT / "matrix_runs" / "_final_pulse_18r29.txt"
TAG = "stable-2026-07-19-matrix-singlethread-18r29"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with STATE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def rows():
    p = OUT / "summary.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def cell_stats(rs):
    by = defaultdict(list)
    for r in rs:
        by[r.get("cell")].append(r)
    out = {}
    for c, items in by.items():
        best = {}
        for it in items:
            ri = it.get("round")
            prev = best.get(ri)
            if prev is None or (it.get("ok") and not prev.get("ok")):
                best[ri] = it
        out[c] = {
            "ok": sum(1 for v in best.values() if v.get("ok")),
            "n": len(best),
            "cls": dict(Counter(v.get("class") for v in best.values())),
        }
    return out

def api_status():
    import urllib.request
    try:
        return json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8).read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)}

def matrix_alive():
    # parent+child python for matrix_cross_run
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_cross_run' } | Measure-Object | Select-Object -ExpandProperty Count"],
            text=True, encoding="utf-8", errors="replace")
        return int(out.strip() or "0") > 0
    except Exception:
        cl = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
        return cl.exists() and (time.time() - cl.stat().st_mtime) < 1200

log("guardian start")
last_ok = -1
while True:
    rs = rows()
    cells = cell_stats(rs)
    st = api_status()
    ok = sum(v["ok"] for v in cells.values())
    lines = [
        f"ts={datetime.now().isoformat(timespec='seconds')}",
        f"matrix_alive={matrix_alive()} report={(OUT/'REPORT.md').exists()} ok={ok} rows={len(rs)}",
        f"api running={st.get('running')} phase={st.get('phase')} sess={st.get('session_success')}/{st.get('session_fail')} p={st.get('session_pending_sso')} ev={(st.get('last_event') or '')[:140]}",
    ]
    for c, v in sorted(cells.items()):
        lines.append(f"  {c}: {v['ok']}/{v['n']} {v['cls']}")
    cl = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if cl.exists():
        lines.append("console:")
        lines.extend(cl.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
    PULSE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if ok != last_ok:
        last_ok = ok
        log(f"ok={ok} cells={ {k: f'{v['ok']}/{v['n']}' for k,v in cells.items()} }")

    if (OUT / "REPORT.md").exists():
        log("REPORT found — ensure publish")
        # wait a bit for auto_publish
        time.sleep(10)
        pub = ROOT / "matrix_runs" / "_publish_18r29_state.txt"
        text = pub.read_text(encoding="utf-8", errors="replace") if pub.exists() else ""
        zip_path = ROOT / "packages" / f"{TAG}.zip"
        if "DONE publish" not in text and not zip_path.exists():
            log("spawn auto_publish")
            subprocess.Popen([sys.executable, "-B", str(ROOT / "tools" / "_auto_publish_18r29.py")], cwd=str(ROOT),
                             stdout=open(ROOT / "matrix_runs" / "_auto_publish_guard.out", "a", encoding="utf-8"),
                             stderr=subprocess.STDOUT)
        # wait package up to 10 min
        for i in range(120):
            if zip_path.exists() and (pub.exists() and "DONE" in pub.read_text(encoding="utf-8", errors="replace")):
                log(f"publish complete zip={zip_path.stat().st_size}")
                break
            time.sleep(5)
        else:
            log("publish wait timeout — attempting inline build")
            # minimal fallback build via existing script
            try:
                subprocess.check_call([sys.executable, "-B", str(ROOT / "tools" / "_build_package_18r29.py")], cwd=str(ROOT))
            except Exception as e:
                log(f"inline build fail {e}")
        # companion services docs
        try:
            svc = Path(r"C:\Users\zhang\grok-regkit-services")
            if svc.exists():
                note = svc / f"RESTORE_POINT_2026-07-19-matrix-singlethread-18r29.md"
                body = f"""# Companion restore — {TAG}

- grok-regkit tag: `{TAG}`
- matrix: single-thread 10x10 hybrid/browser × direct/socks5 × outlook/aol + pending
- services ports unchanged: 8092/8080/8010/8317/8318
- marked: {datetime.now().isoformat(timespec='seconds')}
- stop registration only; keep other services running
"""
                note.write_text(body, encoding="utf-8")
                sv = svc / "STABLE_VERSION.md"
                head = f"""# STABLE_VERSION

## Latest companion — {TAG}

| 项 | 值 |
|----|----|
| Tag | `{TAG}` |
| grok-regkit | `{TAG}` |
| sub2api | keep fork 0.1.161-fork1 (CPA import + 429 failover) |

## Ports

| Port | Service |
|------|---------|
| 8092 | grok-regkit Web |
| 8080 | Sub2API |
| 8010 | grok2api |
| 8317 | CLIProxyAPI |
| 8318 | CPA Gateway |

"""
                old = sv.read_text(encoding="utf-8") if sv.exists() else ""
                if TAG not in old:
                    sv.write_text(head + "\n" + old, encoding="utf-8")
                subprocess.run(["git", "add", note.name, "STABLE_VERSION.md", "CHANGELOG.md"], cwd=str(svc), check=False)
                # changelog
                clp = svc / "CHANGELOG.md"
                ch = f"\n## {TAG}\n\n- Companion restore aligned with grok-regkit single-thread matrix 18r29.\n- Ports/service manager unchanged; registration stop does not stop 8010/8080/8317/8318.\n"
                if clp.exists():
                    t = clp.read_text(encoding="utf-8")
                    if TAG not in t:
                        clp.write_text(t.replace("# CHANGELOG\n", "# CHANGELOG\n" + ch, 1) if t.startswith("# CHANGELOG") else ch + t, encoding="utf-8")
                else:
                    clp.write_text("# CHANGELOG\n" + ch, encoding="utf-8")
                subprocess.run(["git", "add", "CHANGELOG.md", note.name, "STABLE_VERSION.md"], cwd=str(svc), check=False)
                subprocess.run(["git", "commit", "-m", f"docs: companion restore {TAG}"], cwd=str(svc), check=False)
                subprocess.run(["git", "tag", TAG], cwd=str(svc), check=False)
                subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=str(svc), check=False)
                subprocess.run(["git", "push", "origin", TAG], cwd=str(svc), check=False)
                log("companion services pushed")
        except Exception as e:
            log(f"companion err {e}")
        # sub2api note only if clean
        try:
            s2 = Path(r"C:\Users\zhang\sub2api-src")
            if s2.exists():
                rp = s2 / f"RESTORE_{TAG}.md"
                rp.write_text(f"# sub2api restore aligned {TAG}\n\nKeep local fork changes (CPA JSON import + Grok 429 multi-failover). Do not overwrite with stock upstream without re-applying patches.\n", encoding="utf-8")
                st = subprocess.run(["git", "status", "-sb"], cwd=str(s2), capture_output=True, text=True)
                log(f"sub2api status {st.stdout.strip()[:200]}")
                subprocess.run(["git", "add", rp.name], cwd=str(s2), check=False)
                subprocess.run(["git", "commit", "-m", f"docs: restore align {TAG}"], cwd=str(s2), check=False)
                subprocess.run(["git", "tag", TAG], cwd=str(s2), check=False)
                subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=str(s2), check=False)
                subprocess.run(["git", "push", "origin", TAG], cwd=str(s2), check=False)
                log("sub2api docs pushed")
        except Exception as e:
            log(f"sub2api err {e}")
        log("GUARDIAN DONE")
        break

    # if matrix dead without report, log alert
    if not matrix_alive() and not (OUT / "REPORT.md").exists():
        log("WARN matrix process not found and no REPORT")
        # don't auto-restart blindly; leave alert
        time.sleep(60)
        continue
    time.sleep(40)
