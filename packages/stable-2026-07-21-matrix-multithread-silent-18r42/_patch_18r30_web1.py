# -*- coding: utf-8 -*-
from pathlib import Path
import re
import py_compile

# ---- web/server.py ----
sp = Path("web/server.py")
st = sp.read_text(encoding="utf-8")

if "workers: int" not in st:
    st = st.replace(
        '''class StartBody(BaseModel):
    # 单次任务上限（2G 机器仍建议分批；允许 1000 方便面板一次提交）
    count: int = Field(default=1, ge=1, le=1000)
''',
        '''class StartBody(BaseModel):
    # 单次任务上限（2G 机器仍建议分批；允许 1000 方便面板一次提交）
    count: int = Field(default=1, ge=1, le=1000)
    # 18r30 multi-thread workers (1=serial)
    workers: int = Field(default=1, ge=1, le=32)
''',
    )
    print("StartBody workers")

if "workers: Optional[int]" not in st:
    st = st.replace(
        "    register_count: Optional[int] = None\n    register_mode: Optional[str] = None\n",
        "    register_count: Optional[int] = None\n    workers: Optional[int] = None\n    thread_count: Optional[int] = None\n    mail_top_per_folder: Optional[int] = None\n    email_preflight_on_start: Optional[bool] = None\n    register_mode: Optional[str] = None\n",
    )
    print("ConfigBody workers")

# _run_job signature
if "def _run_job(count: int, job_kind: str = \"register\", workers: int = 1)" not in st:
    st = st.replace(
        "def _run_job(count: int, job_kind: str = \"register\") -> None:",
        "def _run_job(count: int, job_kind: str = \"register\", workers: int = 1) -> None:",
    )
    print("_run_job sig")

# pass workers into jobs
st2 = st
# pending call
st2 = st2.replace(
    '''            result = _pending_mod.run_pending_sso_recovery_job(
                count, log_callback=log_cb, controller=controller
            )''',
    '''            result = _pending_mod.run_pending_sso_recovery_job(
                count, log_callback=log_cb, controller=controller, workers=workers
            )''',
)
st2 = st2.replace(
    '''            result = engine.run_registration_job(
                count, log_callback=log_cb, controller=controller
            )''',
    '''            # persist workers into config for engine resolve_workers
            try:
                engine.config["workers"] = int(workers or 1)
                engine.config["thread_count"] = int(workers or 1)
            except Exception:
                pass
            result = engine.run_registration_job(
                count, log_callback=log_cb, controller=controller, workers=workers
            )''',
)
if st2 == st:
    print("WARN job call replace may have failed")
st = st2

# start endpoint - find api start
# Look for body.count usage
if "body.workers" not in st:
    # common pattern
    for pat in [
        (r'(_run_job\(\s*int\(body\.count\)\s*,\s*[^)]*)\)', r'\1, workers=int(getattr(body, "workers", 1) or 1))'),
        (r'_run_job\(count\)', '_run_job(count, workers=int(getattr(body, "workers", 1) or 1))'),
    ]:
        pass
    # manual search
    m = re.search(r'def (?:api_)?start\w*\([^)]*\):[\s\S]{0,1200}?_run_job\([^\)]+\)', st)
    if m:
        block = m.group(0)
        print("found start block snippet:", block[-200:])
    # replace all _run_job(count variants
    st = re.sub(
        r'_run_job\(\s*([^,\)]+)\s*\)',
        r'_run_job(\1, workers=int(getattr(body, "workers", 1) or 1) if "body" in dir() else 1)',
        st,
    )
    # that's fragile - better find actual lines
print("scanning _run_job calls:")
for i,l in enumerate(st.splitlines(),1):
    if '_run_job' in l:
        print(i, l.strip()[:120])

sp.write_text(st, encoding="utf-8")
