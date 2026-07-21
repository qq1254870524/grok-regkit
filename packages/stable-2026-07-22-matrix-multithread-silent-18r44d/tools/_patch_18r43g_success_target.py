from pathlib import Path

# --- worker_coord.py: success-based target ---
wp = Path("worker_coord.py")
wt = wp.read_text(encoding="utf-8")
if "18r43g:" not in wt[:200]:
    wt = "# 18r43g: claim_slot targets success count (pending/fail do not end job early)\n" + wt

old_claim = '''    def claim_slot(self) -> Optional[int]:
        """Return 1-based slot number, or None if target reached / pool empty / stop_extra."""
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            if self._slots_started >= self.target:
                return None
            self._slots_started += 1
            return self._slots_started'''

new_claim = '''    def claim_slot(self) -> Optional[int]:
        """Return 1-based attempt number, or None if success target reached / pool empty / stop_extra.

        18r43g: target is SUCCESS count, not attempt count. pending_sso/fail keep claiming
        until success hits target (safety: max attempts = target * 8 or slots cap).
        """
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            if int(self.success or 0) >= self.target:
                return None
            # safety cap so infinite pending cannot run forever
            max_attempts = max(self.target * 8, self.target + 50)
            if self._slots_started >= max_attempts:
                self._stop_extra = True
                return None
            self._slots_started += 1
            return self._slots_started'''

if old_claim not in wt:
    raise SystemExit("claim_slot block not found")
wt = wt.replace(old_claim, new_claim, 1)
wp.write_text(wt, encoding="utf-8")
print("worker_coord claim_slot patched")

# --- hybrid single-thread: while success_count < count ---
hp = Path("hybrid_register.py")
ht = hp.read_text(encoding="utf-8")
if "18r43g:" not in ht[:300]:
    ht = "# 18r43g: hybrid target = success count (pending/fail do not consume success quota)\n" + ht

# single-thread loop: while i < count -> while success_count < count with attempt safety
old_st = '''        i = 0

        switch_mailbox_tries = 0

        max_switch_mailbox = max(8, int(count) * 3)

        while i < count:'''

# file may not have blank lines between - try flexible
import re
m = re.search(r"i = 0\s*\n\s*switch_mailbox_tries = 0\s*\n\s*max_switch_mailbox = max\(8, int\(count\) \* 3\)\s*\n\s*while i < count:", ht)
if not m:
    # try without extra blanks
    m = re.search(r"i = 0\n\s*switch_mailbox_tries = 0\n\s*max_switch_mailbox = max\(8, int\(count\) \* 3\)\n\s*while i < count:", ht)
if not m:
    print("WARN single-thread loop pattern not found; skip ST")
else:
    new_st = '''i = 0
        switch_mailbox_tries = 0
        max_switch_mailbox = max(8, int(count) * 3)
        max_attempts = max(int(count) * 8, int(count) + 50)
        # 18r43g: keep going until success_count hits target (not attempt count)
        while success_count < int(count) and i < max_attempts:'''
    ht = ht[:m.start()] + new_st + ht[m.end():]
    print("hybrid ST loop patched")

# MT log line clarity
ht2 = ht.replace(
    'log(f"[*] 混合多线程启动 workers={wn} target={count}")',
    'log(f"[*] 混合多线程启动 workers={wn} success_target={count} (18r43g success-based)")',
    1,
)
if ht2 == ht:
    # maybe different formatting
    ht2 = ht.replace(
        "混合多线程启动 workers={wn} target={count}",
        "混合多线程启动 workers={wn} success_target={count} (18r43g success-based)",
        1,
    )
ht = ht2
hp.write_text(ht, encoding="utf-8")
print("hybrid written")

# package notes
pp = Path("tools/package_18r43_silent.py")
pt = pp.read_text(encoding="utf-8")
if "18r43g" not in pt:
    pt = pt.replace(
        '"- 18r43f: Sub2API verify fail-fast permanent permission-denied; matrix verify_timeout=35 attempts=1",',
        '"- 18r43f: Sub2API verify fail-fast permanent permission-denied; matrix verify_timeout=35 attempts=1",\n        "- 18r43g: register count is SUCCESS target (pending/fail no longer end job early)",',
        1,
    )
    pp.write_text(pt, encoding="utf-8")
    print("package notes ok")

import ast
ast.parse(wp.read_text(encoding="utf-8"))
ast.parse(hp.read_text(encoding="utf-8"))
print("syntax ok")
