import json, time, urllib.request
from pathlib import Path
from datetime import datetime
base = Path(r"C:\Users\zhang\grok-regkit\matrix_runs")
out = base / "_agent_poll_18r35.txt"
end = time.time() + 2700
last_cell = ""
while time.time() < end:
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=8) as r:
            st = json.loads(r.read().decode("utf-8", "replace"))
        pulse = ""
        pp = base / "_live_pulse_18r35.txt"
        if pp.exists():
            pulse = pp.read_text(encoding="utf-8", errors="replace").strip().replace("\n", " | ")
        # jsonl cells
        jl = base / "matrix_18r30_20260720_003737.jsonl"
        cells = 0
        if jl.exists():
            cells = sum(1 for _ in jl.open(encoding="utf-8", errors="replace") if _.strip())
        line = (
            f"{ts} run={st.get('running')} phase={st.get('phase')} "
            f"ok={st.get('success')} fail={st.get('fail')} pend={st.get('pending_sso')} "
            f"sess={st.get('session_success')}/{st.get('session_fail')}/{st.get('session_pending_sso')} "
            f"jobs={st.get('jobs_finished')}/{st.get('jobs_started')} cells_done={cells} | "
            f"{str(st.get('last_event',''))[:140]}\n"
        )
        with out.open("a", encoding="utf-8") as f:
            f.write(line)
        # progress board
        board = base / "_PROGRESS_BOARD_18r35.md"
        board.write_text(
            f"# 18r35 Progress\n\nUpdated: {datetime.now().isoformat()}\n\n"
            f"- running: {st.get('running')}\n"
            f"- phase: {st.get('phase')}\n"
            f"- cell counters: ok={st.get('success')} fail={st.get('fail')} pend={st.get('pending_sso')} target={st.get('target')}\n"
            f"- session: ok={st.get('session_success')} fail={st.get('session_fail')} pend={st.get('session_pending_sso')}\n"
            f"- jobs: {st.get('jobs_finished')}/{st.get('jobs_started')}\n"
            f"- cells_done_jsonl: {cells}/8 (+pending)\n"
            f"- last_event: {st.get('last_event')}\n"
            f"- pulse: {pulse}\n",
            encoding="utf-8",
        )
    except Exception as e:
        with out.open("a", encoding="utf-8") as f:
            f.write(f"{ts} ERR {e}\n")
    time.sleep(45)
