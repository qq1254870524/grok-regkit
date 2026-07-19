from pathlib import Path
import re, py_compile, importlib.util

p = Path(r"C:\Users\zhang\grok-regkit\tools\matrix_cross_run.py")
t = p.read_text(encoding="utf-8")
if "18r29g: page-structure" in t or "precheck page-structure fails" in t:
    print("already patched-ish")
else:
    # insert early return after tl =
    pat = r"(def classify\(logs: str\) -> str:.*?tl = \(logs or \"\"\)\.lower\(\) if False else t\.lower\(\)\n)"
    # actual code uses tl = t.lower()
    m = re.search(r"def classify\(logs: str\) -> str:.*?tl = t\.lower\(\)\n", t, flags=re.S)
    if not m:
        raise SystemExit("classify head not found")
    head = m.group(0)
    if "inputs=none" in head and "return \"create_email_fail\"" in head:
        print("head already has precheck")
    else:
        insert_after = head + (
            "    # 18r29g: page-structure fails must beat '您正在登录' noise inside error dumps\n"
            "    if (\"未找到邮箱输入框\" in t) or (\"inputs=none\" in tl) or (\"未找到邮箱输入框或注册按钮\" in t):\n"
            "        return \"create_email_fail\"\n"
        )
        t = t.replace(head, insert_after, 1)
        if "2026-07-19r29g" not in t:
            t = t.replace(
                "Changelog:\n",
                "Changelog:\n- 2026-07-19r29g: classify missing email input before sso_timeout (avoid 您正在登录 dump false positive).\n",
                1,
            )
        p.write_text(t, encoding="utf-8")
        print("patched classify")

py_compile.compile(str(p), doraise=True)
spec = importlib.util.spec_from_file_location("m", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for name in ["r05", "r07"]:
    lp = Path(rf"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041\browser__socks5_list__outlook_{name}.log")
    if not lp.exists():
        lp = Path(rf"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041\browser__socks5_list__outlook_{name.replace('r','r0') if len(name)==3 else name}.log")
# direct
for fn in [
    "browser__socks5_list__outlook_r05.log",
    "browser__socks5_list__outlook_r07.log",
]:
    lp = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041") / fn
    print(fn, "->", mod.classify(lp.read_text(encoding="utf-8", errors="replace")))
print("ok")
