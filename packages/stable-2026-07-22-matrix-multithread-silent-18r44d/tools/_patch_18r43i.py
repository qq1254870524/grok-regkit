from pathlib import Path

# hybrid_register: depth-scaled drain
p = Path("hybrid_register.py")
t = p.read_text(encoding="utf-8")
old = "engine.wait_post_success_queue(timeout=20 if controller.should_stop() else 120, log_callback=log)"
new = "engine.wait_post_success_queue(timeout=20 if controller.should_stop() else None, log_callback=log)"
c = t.count(old)
if c:
    t = t.replace(old, new)
    if "18r43i:" not in "\n".join(t.splitlines()[:20]):
        t = "# 18r43i: hybrid job-end wait_post timeout=None (depth-scaled drain)\n" + t
    p.write_text(t, encoding="utf-8")
    print("hybrid replaced", c)
else:
    print("hybrid pattern missing", t.count("wait_post_success_queue"))

# grok_register_ttk: re-ensure workers in wait loop
g = Path("grok_register_ttk.py")
gt = g.read_text(encoding="utf-8")
marker = 'log(f"[*] 等待后处理队列… 剩余约 {pending}（CPA/NSFW 后台中）")'
if marker not in gt:
    marker = 'log(f"[*] \u7b49\u5f85\u540e\u5904\u7406\u961f\u5217\u2026 \u5269\u4f59\u7ea6 {pending}\uff08CPA/NSFW \u540e\u53f0\u4e2d\uff09")'
idx = gt.find('剩余约 {pending}')
print("idx", idx)
if "ensure_post_success_worker(log_callback=log)" in gt[gt.find("def wait_post_success_queue"):gt.find("def wait_post_success_queue")+800]:
    print("already has ensure in wait")
else:
    old_snip = """        if pending > 0 and (now - last_log) >= 10.0:
            log(f"[*] 等待后处理队列… 剩余约 {pending}（CPA/NSFW 后台中）")
            last_log = now
        time.sleep(1.0)"""
    new_snip = """        if pending > 0 and (now - last_log) >= 10.0:
            log(f"[*] 等待后处理队列… 剩余约 {pending}（CPA/NSFW 后台中）")
            last_log = now
            # 18r43i: re-ensure drain workers while waiting (replace dead threads)
            try:
                ensure_post_success_worker(log_callback=log)
            except Exception:
                pass
        time.sleep(1.0)"""
    if old_snip in gt:
        gt = gt.replace(old_snip, new_snip)
        if not gt.startswith("# 18r43i:"):
            gt = "# 18r43i: wait_post re-ensure drain workers every 10s\n" + gt
        g.write_text(gt, encoding="utf-8")
        print("grok wait ensure patched")
    else:
        print("snip missing")
        i = gt.find("等待后处理队列")
        print(repr(gt[i-60:i+120]))

# worker_coord: log claim mode on init
w = Path("worker_coord.py")
wt = w.read_text(encoding="utf-8")
if "claim_mode=success" not in wt:
    old_init = """        self._stop_extra = False

    def worker_enter(self) -> None:"""
    new_init = """        self._stop_extra = False
        try:
            self.log(
                f"[coord] success_target={self.target} claim_mode=success "
                f"max_attempts={max(self.target * 8, self.target + 50)} (18r43g/i)"
            )
        except Exception:
            pass

    def worker_enter(self) -> None:"""
    if old_init in wt:
        wt = wt.replace(old_init, new_init, 1)
        if "18r43i:" not in wt[:200]:
            wt = "# 18r43i: log success-based claim_mode on JobCoordinator init\n" + wt
        w.write_text(wt, encoding="utf-8")
        print("worker_coord log patched")
    else:
        print("worker_coord init snip missing")
else:
    print("worker_coord already logs")
print("done")
