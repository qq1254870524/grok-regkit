import time, json, urllib.request
from pathlib import Path
base = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
out = base / "_CODEX_18r43_LONGPOLL.jsonl"
for i in range(2880):  # 120 * 30s = 60 min
    try:
        s = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
        row = {
            "ts": time.strftime("%H:%M:%S"),
            "ok": s.get("success"),
            "fail": s.get("fail"),
            "pend": s.get("pending_sso"),
            "await": s.get("awaiting_pool"),
            "phase": s.get("phase"),
            "run": s.get("running"),
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        (base / "_CODEX_18r43_PROGRESS.md").write_text(
            "# 18r43 progress\nupdated=%s\nok=%s fail=%s pend=%s await=%s phase=%s run=%s\n"
            % (row["ts"], row["ok"], row["fail"], row["pend"], row["await"], row["phase"], row["run"]),
            encoding="utf-8",
        )
    except Exception as e:
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%H:%M:%S"), "err": str(e)}) + "\n")
    time.sleep(30)
