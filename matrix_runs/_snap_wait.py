import time, json, urllib.request
from pathlib import Path
from datetime import datetime
root=Path(r"C:\Users\zhang\grok-regkit")
weak=root/"matrix_runs"/"matrix_18r24_weak_20260719_033411"
out=root/"matrix_runs"/"_snap.txt"
time.sleep(120)
s=json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
rl=(weak/"runner.log").read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
out.write_text("\n".join([
    datetime.now().isoformat(),
    str({k:s.get(k) for k in ['running','phase','success','fail','pending_sso','last_event','jobs_started','jobs_finished']}),
    *rl
]), encoding="utf-8")
