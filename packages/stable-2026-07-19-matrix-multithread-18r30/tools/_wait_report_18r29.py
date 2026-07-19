"""Wait for matrix REPORT.md then mark ready. Does not push git."""
import time
from pathlib import Path
from datetime import datetime
ROOT = Path(r"C:\Users\zhang\grok-regkit")
OUT = ROOT / "matrix_runs" / "matrix_18r29_20260719_070041"
FLAG = ROOT / "matrix_runs" / "_18r29_READY.txt"
ALERT = ROOT / "matrix_runs" / "_alerts_18r29.txt"
while True:
    if (OUT / "REPORT.md").exists():
        # wait matrix process exit briefly
        time.sleep(5)
        text = (OUT / "REPORT.md").read_text(encoding="utf-8", errors="replace")
        summ_n = 0
        sj = OUT / "summary.jsonl"
        if sj.exists():
            summ_n = len([x for x in sj.read_text(encoding="utf-8").splitlines() if x.strip()])
        msg = f"READY ts={datetime.now().isoformat(timespec='seconds')} summary_rows={summ_n}\n"
        FLAG.write_text(msg + text[:4000], encoding="utf-8")
        with ALERT.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] REPORT_READY rows={summ_n}\n")
        break
    time.sleep(30)
