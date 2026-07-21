from pathlib import Path
p = Path("tools/matrix_18r43_silent_stable_mt.py")
t = p.read_text(encoding="utf-8")
old = '''        # 18r43i: drop trailing incomplete register cells (success < COUNT) so they re-run
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
'''
new = '''        # 18r43i: keep completed cells even if success<COUNT (historical attempt-based);
        # top-up only applies to cells run after this process start.
        print(f"[matrix] resume from state stamp={stamp} done_cells={len(results)}", flush=True)
'''
if old in t:
    t = t.replace(old, new, 1)
    p.write_text(t, encoding="utf-8")
    print("softened resume drop")
else:
    print("block not found")
import py_compile
py_compile.compile(str(p), doraise=True)
print("ok")
