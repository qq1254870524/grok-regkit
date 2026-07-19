import time, json, os, urllib.request
from pathlib import Path
base = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
out = base / "matrix_18r29_20260719_070041"
status_path = base / "_agent_watch_live_18r29.txt"
done_flag = base / "_agent_matrix_done.flag"
board = base / "_progress_board_18r29.txt"
console = base / "matrix_18r29_runner_console.log"
report = out / "REPORT.md"
for i in range(600):  # up to ~5h at 30s
    lines = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"ts={now} tick={i}")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5) as r:
            st = json.loads(r.read().decode("utf-8", "replace"))
        lines.append(f"running={st.get('running')} phase={st.get('phase')} job={st.get('job_kind')} last={str(st.get('last_event',''))[:160]}")
        lines.append(f"sess s/f/p={st.get('session_success')}/{st.get('session_fail')}/{st.get('session_pending_sso')} jobs={st.get('jobs_started')}/{st.get('jobs_finished')}")
    except Exception as e:
        lines.append(f"status_err={e}")
    if board.exists():
        lines.append("---BOARD---")
        lines.append(board.read_text(encoding="utf-8", errors="replace")[:1200])
    if console.exists():
        tail = console.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
        lines.append("---CONSOLE---")
        lines.extend(tail)
    pend = sorted(out.glob("pending_sso_recovery*"), key=lambda p: p.stat().st_mtime)
    lines.append(f"pending_logs={len(pend)} latest={[p.name for p in pend[-4:]]}")
    lines.append(f"report={report.exists()} done_flag={done_flag.exists()}")
    # summary count
    sj = out / "summary.jsonl"
    if sj.exists():
        from collections import Counter, defaultdict
        c = Counter(); stc = defaultdict(Counter)
        for line in sj.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            cell = d.get("cell") or "?"
            c[cell] += 1
            stc[cell][str(d.get("class") or d.get("ok"))] += 1
        for k in sorted(c):
            if "pending" in k or c[k] < 10:
                lines.append(f"cell {k}: {c[k]} {dict(stc[k])}")
        lines.append(f"rows={sum(c.values())} cells_ge10={sum(1 for v in c.values() if v>=10)}")
    status_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if report.exists() and done_flag.exists():
        break
    if report.exists() and not any("pending_sso_recovery" in k and c.get(k,0) < 10 for k in list(c.keys()) + ["pending_sso_recovery__direct","pending_sso_recovery__socks5_list"]):
        # wait for publish flag a bit longer
        pass
    time.sleep(30)
status_path.write_text(status_path.read_text(encoding="utf-8", errors="replace") + "\nWATCH_EXIT\n", encoding="utf-8")
