import json, time, urllib.request
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
PULSE = ROOT / "matrix_runs" / "_live_pulse_18r29.txt"
API = "http://127.0.0.1:8092"
while True:
    lines = [f"ts={datetime.now().isoformat(timespec='seconds')}"]
    try:
        with urllib.request.urlopen(API+"/api/status", timeout=8) as r:
            st = json.loads(r.read().decode())
        lines.append(f"running={st.get('running')} kind={st.get('job_kind')} phase={st.get('phase')} s={st.get('success')} f={st.get('fail')} p={st.get('pending_sso')} event={(st.get('last_event') or '')[:160]}")
    except Exception as e:
        lines.append(f"status_err={e}")
    summ = OUT / "summary.jsonl"
    if summ.exists():
        rows = [json.loads(x) for x in summ.read_text(encoding='utf-8').splitlines() if x.strip()]
        ok = sum(1 for r in rows if r.get('ok'))
        lines.append(f"matrix_rows={len(rows)} ok={ok} last={rows[-1] if rows else None}")
        from collections import Counter
        c = Counter(r.get('class') for r in rows)
        lines.append(f"classes={dict(c)}")
    clog = ROOT / "matrix_runs" / "matrix_18r29_runner_console.log"
    if clog.exists():
        tail = clog.read_text(encoding='utf-8', errors='replace').splitlines()[-8:]
        lines.append("console:")
        lines.extend(tail)
    # matrix still alive?
    import subprocess
    try:
        out = subprocess.check_output('wmic process where "CommandLine like \'%matrix_cross_run%\'" get ProcessId /value', shell=True, text=True, errors='replace')
        lines.append('matrix_proc=' + ' '.join(x.strip() for x in out.splitlines() if x.strip()))
    except Exception as e:
        lines.append(f'proc_err={e}')
    PULSE.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # stop if report exists and no matrix
    if (OUT / 'REPORT.md').exists():
        lines.append('REPORT_READY')
        PULSE.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        # keep pulsing a bit more then exit when no matrix
        break
    time.sleep(20)