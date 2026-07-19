import time, json, urllib.request
from pathlib import Path
from datetime import datetime

root = Path(r"C:\Users\zhang\grok-regkit")
out = root / "matrix_runs" / "matrix_18r29_20260719_070041"
sj = out / "summary.jsonl"
dst = root / "matrix_runs" / "_wait_snap_18r29.jsonl"

def snap(tag):
    st = {}
    try:
        st = json.loads(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5).read().decode())
    except Exception as e:
        st = {"error": str(e)}
    rows = []
    if sj.exists():
        rows = [json.loads(x) for x in sj.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
    rec = {
        "tag": tag,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "n": len(rows),
        "last": rows[-1] if rows else None,
        "session_success": st.get("session_success"),
        "session_pending_sso": st.get("session_pending_sso"),
        "session_fail": st.get("session_fail"),
        "running": st.get("running"),
        "phase": st.get("phase"),
        "evt": (st.get("last_event") or "")[:200],
        "report": (out / "REPORT.md").exists(),
    }
    with dst.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

# wait ~3 minutes total, snap every 30s
for i in range(7):
    r = snap(f"w{i}")
    print(r["ts"], "n", r["n"], "phase", r["phase"], "sess", r["session_success"], "last_r", (r["last"] or {}).get("round"), (r["last"] or {}).get("cell"), (r["last"] or {}).get("class"))
    if i < 6:
        time.sleep(30)
print("done wait")
