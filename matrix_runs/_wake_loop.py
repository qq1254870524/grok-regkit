import time
from pathlib import Path
from datetime import datetime
p = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_wake_markers.txt")
for i in range(1, 31):
    time.sleep(60)
    p.write_text(f"wake_{i} {datetime.now().isoformat()}\n", encoding="utf-8")
