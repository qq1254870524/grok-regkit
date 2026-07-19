from pathlib import Path
import py_compile

# --- server.py reload ---
sp = Path("web/server.py")
st = sp.read_text(encoding="utf-8")
old = '''        if job_kind == "pending_sso_recovery":
            from pending_sso_recovery import run_pending_sso_recovery_job
            result = run_pending_sso_recovery_job(
                count, log_callback=log_cb, controller=controller
            )
        else:
            result = engine.run_registration_job(
                count, log_callback=log_cb, controller=controller
            )
'''
new = '''        if job_kind == "pending_sso_recovery":
            import importlib
            import pending_sso_recovery as _pending_mod
            importlib.reload(_pending_mod)
            result = _pending_mod.run_pending_sso_recovery_job(
                count, log_callback=log_cb, controller=controller
            )
        else:
            # Prefer freshly loaded hybrid path helpers when modules were patched mid-process.
            try:
                import importlib
                import hybrid_register as _hy
                importlib.reload(_hy)
            except Exception:
                pass
            result = engine.run_registration_job(
                count, log_callback=log_cb, controller=controller
            )
'''
if "importlib.reload(_pending_mod)" not in st:
    if old not in st:
        raise SystemExit("server job block not found")
    st = st.replace(old, new, 1)
    sp.write_text(st, encoding="utf-8")
    print("server.py reloaded patch OK")
else:
    print("server.py already has reload")

# --- hybrid changelog ---
hp = Path("hybrid_register.py")
ht = hp.read_text(encoding="utf-8")
needle = "- 2026-07-19r24: browser 资料页默认 timeout 210s"
ins = "- 2026-07-19r24b: pending 失败后队首轮转到 accounts_registered_pending_sso 末尾；8092 pending job importlib.reload 热加载；避免 doron28 堵死 count=1。\n"
if "2026-07-19r24b:" not in ht and needle in ht:
    ht = ht.replace(needle, ins + needle, 1)
    hp.write_text(ht, encoding="utf-8")
    print("hybrid changelog OK")
else:
    print("hybrid changelog skip", "r24b" in ht, needle in ht)

# --- weak script: don't double-write summary (run_one already appends) ---
wp = Path("tools/matrix_rerun_weak_18r24.py")
wt = wp.read_text(encoding="utf-8")
oldw = '''            results.append(rec)
            with SUM.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
            log(
'''
# try both escaped forms
if 'with SUM.open("a"' in wt:
    wt2 = []
    lines = wt.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if 'with SUM.open("a"' in lines[i] and "encoding" in lines[i]:
            # skip with-block 2-3 lines
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                if lines[i].lstrip().startswith("f.write") or lines[i].lstrip().startswith("json") or lines[i].strip() == "":
                    # still inside with
                    if lines[i].lstrip().startswith("log("):
                        break
                    i += 1
                    continue
                break
            # if next non-skipped is f.write line already consumed
            continue
        wt2.append(lines[i])
        i += 1
    # simpler replace
    import re
    wt_new, n = re.subn(
        r"\n\s*with SUM\.open\(\"a\", encoding=\"utf-8\"\) as f:\n\s*f\.write\(json\.dumps\(rec, ensure_ascii=False\) \+ \"\\n\"\)\n",
        "\n",
        wt,
        count=1,
    )
    if n:
        wp.write_text(wt_new, encoding="utf-8")
        print("weak double-write removed", n)
    else:
        print("weak pattern not found; dump context")
        for j,l in enumerate(wt.splitlines()):
            if "SUM.open" in l or "results.append" in l:
                print(j+1, l)
else:
    print("no SUM.open in weak")

for f in (sp, hp, wp, Path("pending_sso_recovery.py"), Path("grok_register_ttk.py"), Path("tools/matrix_cross_run.py")):
    py_compile.compile(str(f), doraise=True)
    print("compile", f)
print("ALL_COMPILE_OK")
