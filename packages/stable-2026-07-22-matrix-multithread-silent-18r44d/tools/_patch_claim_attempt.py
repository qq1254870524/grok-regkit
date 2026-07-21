from pathlib import Path
import re
p = Path(r"C:\Users\zhang\grok-regkit\worker_coord.py")
t = p.read_text(encoding="utf-8")
if not t.startswith("# 18r43m"):
    t = "# 18r43m: claim_mode=attempt hard-cap slots_started<=target\n" + t
if "self.claim_mode" not in t:
    t = t.replace("self._stop_extra = False", "self._stop_extra = False\n        self.claim_mode = \"attempt\"", 1)
new_claim = '''    def claim_slot(self) -> Optional[int]:
        """Return 1-based attempt number, or None if quota reached / pool empty / stop_extra.

        18r43m default claim_mode=attempt: hard stop when slots_started >= target
        (fail/pending_sso consume register_count). Legacy success only if claim_mode=success.
        """
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return None
            mode = str(getattr(self, "claim_mode", "attempt") or "attempt").strip().lower()
            if mode in ("success", "success_based", "ok"):
                if int(self.success or 0) >= self.target:
                    return None
                max_attempts = max(self.target * 8, self.target + 50)
                if self._slots_started >= max_attempts:
                    self._stop_extra = True
                    return None
            else:
                if self._slots_started >= self.target:
                    return None
            self._slots_started += 1
            return self._slots_started
'''
t2, n = re.subn(
    r"    def claim_slot\(self\) -> Optional\[int\]:.*?\n            return self\._slots_started\n",
    new_claim,
    t,
    count=1,
    flags=re.S,
)
print("claim_slot replacements", n)
if n != 1:
    raise SystemExit(2)
t = t2
t = t.replace(
    'f"[coord] success_target={self.target} claim_mode=success "\n                f"max_attempts={max(self.target * 8, self.target + 50)} (18r43g/i)"',
    'f"[coord] attempt_target={self.target} claim_mode={getattr(self, \"claim_mode\", \"attempt\")} hard_cap={self.target} (18r43m)"',
)
old_h = """    def should_halt(self) -> bool:
        with self._lock:
            return bool(self._stop_extra or self.pool_empty)"""
new_h = """    def should_halt(self) -> bool:
        with self._lock:
            if self._stop_extra or self.pool_empty:
                return True
            mode = str(getattr(self, "claim_mode", "attempt") or "attempt").strip().lower()
            if mode not in ("success", "success_based", "ok") and self._slots_started >= self.target:
                return True
            if mode in ("success", "success_based", "ok") and int(self.success or 0) >= self.target:
                return True
            return False"""
if old_h in t:
    t = t.replace(old_h, new_h)
    print("should_halt patched")
else:
    print("should_halt already or mismatch")
p.write_text(t, encoding="utf-8")
print("OK worker_coord")