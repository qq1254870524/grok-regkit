from pathlib import Path
p = Path("grok_register_ttk.py")
t = p.read_text(encoding="utf-8")

old1 = """_post_success_q = queue.Queue()
_post_success_worker_lock = threading.Lock()
_post_success_worker_started = False
_post_success_pending = 0
_post_success_pending_lock = threading.Lock()
"""
new1 = """_post_success_q = queue.Queue()
_post_success_worker_lock = threading.Lock()
_post_success_worker_started = False
_post_success_worker_count = 0
_post_success_pending = 0
_post_success_pending_lock = threading.Lock()
# 18r43a: multi post-success workers drain awaiting_pool under high concurrency
_POST_SUCCESS_DEFAULT_WORKERS = 6
"""
if old1 not in t:
    raise SystemExit("old1 missing")
t = t.replace(old1, new1, 1)

old2 = '''def ensure_post_success_worker(log_callback=None):
    global _post_success_worker_started
    with _post_success_worker_lock:
        if _post_success_worker_started:
            return
        t = threading.Thread(
            target=_post_success_worker_loop,
            name="post-success-worker",
            daemon=True,
        )
        t.start()
        _post_success_worker_started = True
        if log_callback:
            log_callback("[*] 后处理后台线程已启动（g2a/Sub2API/CPA/NSFW 可异步）")
'''
new2 = '''def ensure_post_success_worker(log_callback=None, workers=None):
    """Start N background post-success workers (G2A/Sub2/CPA/NSFW).

    18r43a: default 6 workers so awaiting_pool keeps up with register workers=20.
    Safe to call repeatedly; only starts missing workers up to target count.
    """
    global _post_success_worker_started, _post_success_worker_count
    try:
        n = int(workers) if workers is not None else 0
    except Exception:
        n = 0
    if n <= 0:
        try:
            n = int((config or {}).get("post_success_workers") or 0)
        except Exception:
            n = 0
    if n <= 0:
        try:
            reg_w = int((config or {}).get("workers") or (config or {}).get("thread_count") or 0)
        except Exception:
            reg_w = 0
        if reg_w >= 10:
            n = _POST_SUCCESS_DEFAULT_WORKERS
        elif reg_w >= 4:
            n = 3
        else:
            n = 1
    n = max(1, min(16, int(n)))
    with _post_success_worker_lock:
        while _post_success_worker_count < n:
            idx = _post_success_worker_count + 1
            th = threading.Thread(
                target=_post_success_worker_loop,
                name=f"post-success-worker-{idx}",
                daemon=True,
            )
            th.start()
            _post_success_worker_count += 1
        _post_success_worker_started = _post_success_worker_count > 0
        if log_callback:
            log_callback(
                f"[*] 后处理后台线程已启动 workers={_post_success_worker_count} "
                f"（g2a/Sub2API/CPA/NSFW 可异步；awaiting_pool 并行排空）"
            )
'''
if old2 not in t:
    raise SystemExit("old2 missing")
t = t.replace(old2, new2, 1)

# changelog header
if not t.lstrip().startswith("#") and "18r43a" not in t[:300]:
    pass
# insert near top changelog if present
if "18r43a: multi post-success" not in t[:2500]:
    # find first line after docstring or top
    lines = t.splitlines(True)
    insert_at = 0
    for i, line in enumerate(lines[:40]):
        if line.startswith("#") or line.startswith('"""') or line.startswith("'''"):
            insert_at = i + 1
            break
    lines.insert(0, "# 18r43a: multi post-success workers (default 6) drain awaiting_pool under workers=20\n")
    t = "".join(lines)

p.write_text(t, encoding="utf-8")
import ast
ast.parse(t)
print("patched grok_register_ttk.py post-success multi-worker")
