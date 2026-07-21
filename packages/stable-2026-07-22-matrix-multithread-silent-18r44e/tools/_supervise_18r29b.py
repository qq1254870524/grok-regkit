"""Supervisor for 18r29 matrix: monitor, capture fail details, ensure publish trigger."""
from __future__ import annotations
import json, time, urllib.request, subprocess, os, sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
STATE = ROOT / "matrix_runs" / "_supervise_18r29_state.txt"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
PULSE = ROOT / "matrix_runs" / "_supervise_pulse.txt"
os.chdir(ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

seen_fails = set()
last_ok_count = 0

def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with STATE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def api(path: str):
    try:
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:8092{path}", timeout=8).read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)}

def load_rows():
    p = OUT / "summary.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def cell_stats(rows):
    by = defaultdict(list)
    for r in rows:
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
            "fails": [v for v in best.values() if not v.get("ok")],
        }
    return out

def matrix_alive() -> bool:
    try:
        import psutil  # type: ignore
    except Exception:
        # fallback wmic-less: check via tasklist style not available; use process scan
        pass
    # simple: check runner.log mtime and console
    cl = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if cl.exists() and (time.time() - cl.stat().st_mtime) < 900:
        return True
    # also check if REPORT exists
    return (OUT / "REPORT.md").exists()

def capture_fail(row: dict):
    key = f"{row.get('cell')}|{row.get('round')}|{row.get('class')}|{row.get('finished')}"
    if key in seen_fails:
        return
    seen_fails.add(key)
    msg = f"FAIL {key} err={(row.get('error') or '')[:400]}"
    log(msg)
    with ALERT.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    # dump recent api logs
    logs = api("/api/logs/snapshot?limit=120")
    dump = OUT / f"FAIL_{row.get('cell')}_r{row.get('round')}_{datetime.now().strftime('%H%M%S')}.log"
    try:
        lines = logs.get("lines") if isinstance(logs, dict) else None
        text = "\n".join(lines) if isinstance(lines, list) else json.dumps(logs, ensure_ascii=False)[:20000]
        dump.write_text(text, encoding="utf-8")
        log(f"wrote fail dump {dump.name}")
    except Exception as e:
        log(f"fail dump err {e}")

def try_trigger_publish():
    if not (OUT / "REPORT.md").exists():
        return
    pub_state = ROOT / "matrix_runs" / "_publish_18r29_state.txt"
    text = pub_state.read_text(encoding="utf-8", errors="replace") if pub_state.exists() else ""
    if "DONE" in text or "published" in text.lower() or "tag pushed" in text.lower():
        log("publish already done")
        return
    # if auto_publish still waiting but report exists >60s, kick publish
    log("REPORT ready — ensuring publish")
    # run auto publish once more if previous stuck
    if "REPORT found" not in text and "building package" not in text:
        subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "tools" / "_auto_publish_18r29.py")],
            cwd=str(ROOT),
            stdout=open(ROOT / "matrix_runs" / "_auto_publish_18r29_rerun.out", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        log("spawned auto_publish rerun")

log("supervisor start")
while True:
    rows = load_rows()
    cells = cell_stats(rows)
    st = api("/api/status")
    for c, v in cells.items():
        for fr in v.get("fails") or []:
            if fr.get("class") != "empty_log":
                capture_fail(fr)
    ok_unique = sum(v["ok"] for v in cells.values())
    lines = [
        f"ts={datetime.now().isoformat(timespec='seconds')}",
        f"matrix_alive={matrix_alive()} report={(OUT/'REPORT.md').exists()}",
        f"status running={st.get('running')} phase={st.get('phase')} s={st.get('success')}/{st.get('fail')} sess={st.get('session_success')}/{st.get('session_fail')} ev={(st.get('last_event') or '')[:160]}",
        f"summary_rows={len(rows)} ok_unique≈{ok_unique}",
    ]
    for c, v in cells.items():
        lines.append(f"  {c}: {v['ok']}/{v['n']} {v['cls']}")
    cl = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if cl.exists():
        lines.append("console:")
        lines.extend(cl.read_text(encoding="utf-8", errors="replace").splitlines()[-10:])
    PULSE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if ok_unique != last_ok_count:
        last_ok_count = ok_unique
        log(f"progress ok_unique={ok_unique} cells={ {k:f'{v['ok']}/{v['n']}' for k,v in cells.items()} }")
    if (OUT / "REPORT.md").exists():
        log("REPORT detected")
        try_trigger_publish()
        # wait for package
        tag = "stable-2026-07-19-matrix-singlethread-18r29"
        zip_path = ROOT / "packages" / f"{tag}.zip"
        for _ in range(120):
            if zip_path.exists():
                log(f"package ready {zip_path}")
                break
            time.sleep(5)
        log("supervisor done")
        break
    # deadlock detection: not running and no progress for long? matrix owns sequencing
    time.sleep(30)
