from pathlib import Path

p = Path("tools/matrix_18r43_silent_stable_mt.py")
t = p.read_text(encoding="utf-8")

if "18r43i:" not in t[:800]:
    t = (
        '# 18r43i: register cells top-up until success>=count; resume re-runs incomplete register cells\n'
        + t
    )

# Add helper after result_from_status / before run_register_round
helper = '''
def _register_success_ok(success, count) -> bool:
    """True when cell met success target (18r43g success-based)."""
    try:
        ok = int(success or 0)
        tgt = int(count or 0)
    except Exception:
        return False
    if tgt <= 0:
        return True
    return ok >= tgt


def topup_register_until_target(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, first_result=None, max_topup=3):
    """Re-run register job until success>=count or max_topup extra runs (18r43i)."""
    name = f"{mode}__{proxy}__{email}__r{round_i}"
    res = first_result
    runs = []
    if res is not None:
        runs.append(res)
    topup = 0
    while not _register_success_ok((res or {}).get("success"), count) and topup < int(max_topup):
        topup += 1
        ok0 = int((res or {}).get("success") or 0)
        print(
            f"[matrix] 18r43i top-up {topup}/{max_topup} cell={name} success={ok0}<{count} -> re-run full count",
            flush=True,
        )
        res = run_register_round(mode, proxy, email, round_i, workers=workers, count=count, attach_if_running=False)
        res["topup_round"] = topup
        res["topup_prev_success"] = ok0
        runs.append(res)
    if res is None:
        res = run_register_round(mode, proxy, email, round_i, workers=workers, count=count)
        runs.append(res)
    # aggregate note
    try:
        res = dict(res or {})
        res["topup_runs"] = len(runs)
        res["topup_successes"] = [int(r.get("success") or 0) for r in runs]
        res["success_target_met"] = _register_success_ok(res.get("success"), count)
    except Exception:
        pass
    return res


'''

if "def topup_register_until_target" not in t:
    anchor = "def run_register_round(mode, proxy, email, round_i, workers=WORKERS, count=COUNT, attach_if_running=False):"
    if anchor not in t:
        raise SystemExit("run_register_round anchor missing")
    t = t.replace(anchor, helper + anchor, 1)
    print("added topup helper")
else:
    print("topup helper exists")

# Wrap main register path to top-up
old_main = '''        if kind == "register":
            res = run_register_round(mode, proxy, email, r, attach_if_running=attach)
        elif kind == "pending":'''
new_main = '''        if kind == "register":
            res = run_register_round(mode, proxy, email, r, attach_if_running=attach)
            # 18r43i: attempt-based legacy jobs stop at ~count attempts; top-up to success target
            if not _register_success_ok(res.get("success"), COUNT):
                res = topup_register_until_target(
                    mode, proxy, email, r, workers=WORKERS, count=COUNT, first_result=res, max_topup=3
                )
        elif kind == "pending":'''
if old_main in t and "topup_register_until_target(" not in t.split("if kind == \"register\":")[1][:500]:
    t = t.replace(old_main, new_main, 1)
    print("main topup wired")
elif "topup_register_until_target(" in t:
    print("main topup already")
else:
    print("main wire failed", old_main in t)

# discover_resume: drop trailing incomplete register cells so they re-run
old_disc = '''        print(f"[matrix] resume from state stamp={stamp} done_cells={len(results)}", flush=True)
        return (
            stamp,
            jsonl,
            OUT / f"matrix_18r43_{stamp}_summary.json",
            OUT / f"MATRIX_18r43_{stamp}.md",
            results,
            len(results),
        )'''
new_disc = '''        # 18r43i: drop trailing incomplete register cells (success < COUNT) so they re-run
        while results:
            last = results[-1]
            if str(last.get("kind") or "") == "register" and not _register_success_ok(last.get("success"), COUNT):
                print(
                    f"[matrix] 18r43i resume drop incomplete {last.get('cell')} "
                    f"ok={last.get('success')}<{COUNT}",
                    flush=True,
                )
                results.pop()
                continue
            break
        print(f"[matrix] resume from state stamp={stamp} done_cells={len(results)}", flush=True)
        return (
            stamp,
            jsonl,
            OUT / f"matrix_18r43_{stamp}_summary.json",
            OUT / f"MATRIX_18r43_{stamp}.md",
            results,
            len(results),
        )'''
if "resume drop incomplete" not in t:
    if old_disc in t:
        t = t.replace(old_disc, new_disc, 1)
        print("resume incomplete drop wired")
    else:
        print("resume block missing")
else:
    print("resume drop exists")

# Problem: _register_success_ok used in discover_resume before it's defined if helper is after discover
# Move helpers earlier - before discover_resume
if t.find("def _register_success_ok") > t.find("def discover_resume"):
    print("WARN: helper after discover_resume - need reorder")
    # extract helper and place before discover_resume
    import re
    m = re.search(r"\ndef _register_success_ok\(.*?\ndef topup_register_until_target\(.*?\n    return res\n\n\n", t, re.S)
    if not m:
        # try non-greedy different
        start = t.find("def _register_success_ok")
        end = t.find("def run_register_round")
        block = t[start:end]
        t = t[:start] + t[end:]
        ins_at = t.find("def discover_resume")
        t = t[:ins_at] + block + t[ins_at:]
        print("reordered helpers before discover_resume")
    else:
        block = m.group(0)
        t = t.replace(block, "\n", 1)
        ins_at = t.find("def discover_resume")
        t = t[:ins_at] + block + t[ins_at:]
        print("reordered via regex")

p.write_text(t, encoding="utf-8")
# syntax check
import py_compile
py_compile.compile(str(p), doraise=True)
print("matrix syntax ok")
