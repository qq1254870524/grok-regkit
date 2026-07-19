# -*- coding: utf-8 -*-
"""When matrix 18r35 DONE, publish git tag + release without overwriting old packages."""
from __future__ import annotations
import json, os, subprocess, time, zipfile
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
DONE = OUT / "_matrix_18r35_DONE.flag"
while not DONE.exists():
    time.sleep(30)
    # also detect matrix process exit + idle
    try:
        import urllib.request
        st=json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8).read().decode())
        alive = subprocess.run(
            ["powershell","-NoProfile","-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'matrix_18r30_multithread' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=20,
        )
        n=int((alive.stdout or "0").strip() or 0)
        if (not st.get("running")) and n==0:
            # wait for report files
            time.sleep(20)
            if list(OUT.glob("matrix_18r30_20260720_003737*")) or list(OUT.glob("MATRIX_18r30_20260720*")):
                DONE.write_text(json.dumps({"auto":True,"ts":datetime.now().isoformat(),"status":st}, ensure_ascii=False, indent=2), encoding="utf-8")
                break
    except Exception:
        pass

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
tag = f"stable-2026-07-20-matrix-multithread-18r35-w10-r40"
# collect summary
summaries = sorted(OUT.glob("matrix_18r30_*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
report = summaries[0] if summaries else None
# update changelog with final numbers
cl = ROOT / "CHANGELOG_18r35.md"
extra = ["", f"## Final ({stamp})", f"- tag: `{tag}`"]
if report and report.exists():
    try:
        data=json.loads(report.read_text(encoding="utf-8"))
        for r in data:
            extra.append(f"- `{r.get('cell')}` success={r.get('success')} fail={r.get('fail')} pending={r.get('pending_sso')} err={r.get('error') or ''}")
    except Exception as e:
        extra.append(f"- summary parse err: {e}")
cl.write_text(cl.read_text(encoding="utf-8") + "\n".join(extra) + "\n", encoding="utf-8")

# zip release artifact (source without venv/heavy)
zip_path = OUT / f"grok-regkit-18r35-{stamp}.zip"
exclude = {".venv", "__pycache__", ".git", "matrix_runs"}
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & exclude or any(x in rel.parts for x in (".venv","__pycache__",".git")):
            continue
        if rel.suffix in {".pyc"}:
            continue
        # skip huge account pools from zip? keep small code only under size
        try:
            if p.stat().st_size > 5_000_000:
                continue
        except Exception:
            continue
        try:
            z.write(p, arcname=str(rel))
        except Exception:
            pass

os.chdir(ROOT)
# git commit + tag + push
def run(cmd):
    print("RUN", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=False)

run('git add -A')
run(f'git commit -m "release: {tag} multi-thread matrix w10 r40"')
run(f'git tag -a {tag} -m "{tag}"')
run(f'git push mygithub HEAD')
run(f'git push mygithub {tag}')
# gh release if available
run(f'gh release create {tag} "{zip_path}" --title "{tag}" --notes-file CHANGELOG_18r35.md --repo qq1254870524/grok-regkit')
(OUT / "_matrix_18r35_PUBLISH_DONE.json").write_text(json.dumps({
    "tag": tag, "zip": str(zip_path), "ts": stamp
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("PUBLISH DONE", tag, zip_path, flush=True)
