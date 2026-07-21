import json, time, urllib.request
from pathlib import Path
from datetime import datetime

OUT = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r44_silent_20260722_014611\watch_live.txt")
API = "http://127.0.0.1:8092"
end = time.time() + 7200
while time.time() < end:
    try:
        with urllib.request.urlopen(API + "/api/status", timeout=8) as r:
            st = json.loads(r.read().decode())
        with urllib.request.urlopen(API + "/api/integration", timeout=10) as r:
            ig = json.loads(r.read().decode())
        line = (
            f"{datetime.now().strftime('%H:%M:%S')} run={st.get('running')} "
            f"s={st.get('success')}/{st.get('target')} f={st.get('fail')} "
            f"p={st.get('pending_sso')} ap={st.get('awaiting_pool')} "
            f"uf={st.get('post_success_unfinished')} phase={st.get('phase')} "
            f"g2a={(ig.get('g2a') or {}).get('account_count')} "
            f"sub2={(ig.get('sub2api') or {}).get('account_count')}"
        )
    except Exception as e:
        line = f"{datetime.now().strftime('%H:%M:%S')} ERR {e}"
    with OUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    time.sleep(20)
