from pathlib import Path
import re

# hybrid serial loop: attempt-based
hp = Path(r"C:\Users\zhang\grok-regkit\hybrid_register.py")
ht = hp.read_text(encoding="utf-8")
if not ht.startswith("# 18r43m"):
    ht = "# 18r43m: attempt-based quota (register_count=N max attempts); no success overshoot\n" + ht
ht2, n = re.subn(
    r"max_attempts = max\(int\(count\) \* 8, int\(count\) \+ 50\)\s*\n\s*# 18r43g: keep going until success_count hits target \(not attempt count\)\s*\n\s*while success_count < int\(count\) and i < max_attempts:",
    "max_attempts = int(count)\n        # 18r43m: attempt-based — exactly register_count attempts max\n        while i < max_attempts:",
    ht,
    count=1,
)
print("hybrid serial loop", n)
if n != 1:
    # looser
    ht2, n = re.subn(
        r"while success_count < int\(count\) and i < max_attempts:",
        "while i < int(count):  # 18r43m attempt-based",
        ht,
        count=1,
    )
    print("hybrid serial loose", n)
ht = ht2
ht = ht.replace(
    'log(f"[*] 混合多线程启动 workers={wn} success_target={count} (18r43g success-based)")',
    'log(f"[*] 混合多线程启动 workers={wn} attempt_target={count} claim_mode=attempt (18r43m)")',
)
# JobCoordinator creation in hybrid - pass claim_mode attempt
ht = ht.replace(
    "coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max_switch)",
    'coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max_switch, claim_mode="attempt")',
)
# if JobCoordinator doesn't accept claim_mode kw yet - we set attr on init default
hp.write_text(ht, encoding="utf-8")
print("hybrid patched")

# worker_coord __init__ accept claim_mode
wp = Path(r"C:\Users\zhang\grok-regkit\worker_coord.py")
wt = wp.read_text(encoding="utf-8")
if "claim_mode: str" not in wt and "claim_mode:" not in wt.split("def __init__")[1][:400]:
    wt = wt.replace(
        "max_switch_mailbox: int = 0,\n    ):",
        'max_switch_mailbox: int = 0,\n        claim_mode: str = "attempt",\n    ):',
        1,
    )
    wt = wt.replace(
        'self.claim_mode = "attempt"',
        'mode = str(claim_mode or "attempt").strip().lower()\n        self.claim_mode = "success" if mode in ("success", "success_based", "ok") else "attempt"',
        1,
    )
    wp.write_text(wt, encoding="utf-8")
    print("worker_coord init claim_mode param ok")
else:
    print("worker_coord init already has claim_mode or check")

# browser mt JobCoordinator
gp = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
gt = gp.read_text(encoding="utf-8")
gt2 = gt.replace(
    "coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max(8, int(count) * 3))",
    'coord = JobCoordinator(int(count), log=log, max_switch_mailbox=max(8, int(count) * 3), claim_mode="attempt")',
)
if gt2 != gt:
    if not gt2.startswith("# 18r43m"):
        gt2 = "# 18r43m: attempt-based JobCoordinator claim_mode\n" + gt2
    gp.write_text(gt2, encoding="utf-8")
    print("grok_register_ttk coord claim_mode ok")
else:
    print("grok_register_ttk coord replace miss")

# matrix disable top-up re-runs that multiply attempts
mp = Path(r"C:\Users\zhang\grok-regkit\tools\matrix_18r43_silent_stable_mt.py")
mt = mp.read_text(encoding="utf-8")
if not mt.startswith("# 18r43m"):
    mt = "# 18r43m: no success top-up re-run (attempt-based cells; one run per cell)\n" + mt
# force max_topup default 0
mt = mt.replace(
    "def topup_register_until_target(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, first_result=None, max_topup=3):",
    "def topup_register_until_target(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, first_result=None, max_topup=0):",
)
mt = mt.replace(
    '"""Re-run register job until success>=count or max_topup extra runs (18r43i)."""',
    '"""18r43m: default max_topup=0 — do not re-run full count (attempt-based quota)."""',
)
mp.write_text(mt, encoding="utf-8")
print("matrix topup default 0")

# verify claim_slot
import ast
ast.parse(wp.read_text(encoding="utf-8"))
ast.parse(hp.read_text(encoding="utf-8"))
print("syntax ok")