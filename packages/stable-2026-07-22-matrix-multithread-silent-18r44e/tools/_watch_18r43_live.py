# -*- coding: utf-8 -*-
import json, time, urllib.request
from datetime import datetime
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs"
BOARD = OUT / "_CODEX_MATRIX_18r43_LIVE.md"
SNAP = OUT / "_CODEX_STATUS_18r43.jsonl"
BASE = "http://127.0.0.1:8092"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=12) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

while True:
    try:
        st = get("/api/status")
        try:
            lg = get("/api/logs/snapshot?limit=15")
            lines = [str(x) for x in (lg.get("lines") or [])[-10:]]
        except Exception:
            lines = []
        chrome = edge = dr = 0
        try:
            import psutil
            for p in psutil.process_iter(["name", "cmdline"]):
                try:
                    n = (p.info.get("name") or "").lower()
                    cl = " ".join(p.info.get("cmdline") or [])
                    if n == "chrome.exe":
                        chrome += 1
                        if "DrissionPage" in cl or ".chrome-data" in cl:
                            dr += 1
                    if n == "msedge.exe":
                        edge += 1
                except Exception:
                    pass
        except Exception:
            pass
        now = datetime.now().isoformat(timespec="seconds")
        rec = {
            "ts": now,
            "running": st.get("running"),
            "success": st.get("success"),
            "fail": st.get("fail"),
            "pending_sso": st.get("pending_sso"),
            "awaiting_pool": st.get("awaiting_pool") or st.get("pending_pool") or 0,
            "skipped": st.get("skipped"),
            "target": st.get("target"),
            "phase": st.get("phase"),
            "job_kind": st.get("job_kind"),
            "event": str(st.get("last_event") or "")[:180],
            "chrome": chrome,
            "drission": dr,
            "edge": edge,
        }
        with SNAP.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        md = [
            "# 18r43 silent matrix LIVE (Edge-safe)",
            f"updated={now}",
            (
                f"running={rec['running']} ok={rec['success']} fail={rec['fail']} "
                f"pending={rec['pending_sso']} awaiting_pool={rec['awaiting_pool']} "
                f"skip={rec['skipped']} target={rec['target']}"
            ),
            f"phase={rec['phase']} kind={rec['job_kind']}",
            f"chrome={chrome} drission_script={dr} edge={edge} (Edge never minimized)",
            f"event={rec['event']}",
            "",
            "## recent logs",
        ] + [f"- {x[:200]}" for x in lines]
        BOARD.write_text("\n".join(md) + "\n", encoding="utf-8")
    except Exception as exc:
        try:
            BOARD.write_text("# live error\n" + datetime.now().isoformat() + "\n" + str(exc) + "\n", encoding="utf-8")
        except Exception:
            pass
    time.sleep(20)
