# -*- coding: utf-8 -*-
import json, time, urllib.request
from datetime import datetime
from pathlib import Path
ROOT = Path(r"C:/Users/zhang/grok-regkit")
OUT = ROOT / "matrix_runs"
HEALTH = OUT / "_CODEX_18r43_HEALTH.md"
ALERT = OUT / "_CODEX_18r43_ALERTS.jsonl"
BASE = "http://127.0.0.1:8092"
STATE = {"last_ok": None, "stall_ticks": 0}

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=12) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

while True:
    now = datetime.now().isoformat(timespec="seconds")
    alerts = []
    try:
        st = get("/api/status")
        ok = int(st.get("success") or 0)
        fail = int(st.get("fail") or 0)
        pend = int(st.get("pending_sso") or 0)
        await_p = int(st.get("awaiting_pool") or st.get("pending_pool") or 0)
        running = bool(st.get("running"))
        target = int(st.get("target") or 0)
        phase = str(st.get("phase") or "")
        evt = str(st.get("last_event") or "")[:200]
        if STATE["last_ok"] is None:
            STATE["last_ok"] = ok
        if running and ok == STATE["last_ok"]:
            STATE["stall_ticks"] += 1
        else:
            STATE["stall_ticks"] = 0
            STATE["last_ok"] = ok
        if running and STATE["stall_ticks"] >= 45:
            alerts.append({"ts": now, "type": "stall", "ok": ok, "phase": phase, "evt": evt})
        if fail > 50 and fail > max(ok, 1) * 0.5:
            alerts.append({"ts": now, "type": "high_fail", "ok": ok, "fail": fail})
        chrome = edge = 0
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                n = (p.info.get("name") or "").lower()
                if n == "chrome.exe":
                    chrome += 1
                if n == "msedge.exe":
                    edge += 1
        except Exception:
            pass
        md = [
            "# 18r43 health",
            f"updated={now}",
            f"running={running} ok={ok} fail={fail} pending={pend} awaiting_pool={await_p} target={target}",
            f"phase={phase} stall_ticks={STATE['stall_ticks']}",
            f"chrome={chrome} edge={edge}",
            f"event={evt}",
            f"alerts_last={alerts[-1] if alerts else None}",
        ]
        HEALTH.write_text("\n".join(md) + "\n", encoding="utf-8")
        for a in alerts:
            with ALERT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
    except Exception as exc:
        HEALTH.write_text("# health error\n" + now + "\n" + str(exc) + "\n", encoding="utf-8")
    time.sleep(20)
