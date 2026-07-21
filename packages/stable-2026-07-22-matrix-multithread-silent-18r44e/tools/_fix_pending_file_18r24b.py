from pathlib import Path
import inspect
import pending_sso_recovery as ps

p = Path("accounts_registered_pending_sso.txt")
t = p.read_text(encoding="utf-8", errors="ignore")
if "\\n" in t and t.count("\n") < 2:
    # file contains literal backslash-n sequences
    parts = [x.strip() for x in t.replace("\r\n", "\n").replace("\r", "\n").split("\\n") if x.strip()]
else:
    parts = [x.strip() for x in t.splitlines() if x.strip()]
seen = set()
out = []
for ln in parts:
    k = ln.lower()
    if k in seen:
        continue
    seen.add(k)
    out.append(ln)
p.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
b = p.read_bytes()
print("fixed lines", len(out), "nl", b.count(b"\n"), "literal_bs_n", b.count(b"\\n"))
print("head", out[0][:100] if out else None)
print("tail", out[-1][:100] if out else None)

# Fix rotate function if it writes literal \n
src_path = Path("pending_sso_recovery.py")
src = src_path.read_text(encoding="utf-8")
bad1 = 'path.write_text(("\\\\n".join(new_lines) + ("\\\\n" if new_lines else "")), encoding="utf-8")'
bad2 = 'path.write_text(("\\n".join(new_lines) + ("\\n" if new_lines else "")), encoding="utf-8")'
# Check actual content around rotate write
import re
m = re.search(r"def rotate_pending_sso_account_to_end[\s\S]*?return True\n", src)
if not m:
    print("rotate fn block not found by regex")
else:
    block = m.group(0)
    print("---rotate write lines---")
    for line in block.splitlines():
        if "write_text" in line or "join" in line:
            print(repr(line))

# Safer: rewrite rotate function cleanly
start = src.find("def rotate_pending_sso_account_to_end")
end = src.find("def recover_one_pending_sso", start)
if start < 0 or end < 0:
    raise SystemExit(f"markers missing start={start} end={end}")
new_fn = '''def rotate_pending_sso_account_to_end(email: str, log: Callable[[str], None] | None = None) -> bool:
    """Move email line to end of primary pending file so next job picks another head."""
    target = str(email or "").strip().lower()
    if not target:
        return False
    path = ROOT / "accounts_registered_pending_sso.txt"
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        if log:
            log(f"[pending] rotate read fail: {exc}")
        return False
    keep: list[str] = []
    moved: list[str] = []
    for ln in lines:
        parsed = parse_pending_account_line(ln)
        if parsed and parsed["email"].lower() == target:
            moved.append(ln.strip() or (parsed.get("raw") or ln))
        else:
            keep.append(ln)
    if not moved:
        return False
    seen_m: set[str] = set()
    uniq_moved: list[str] = []
    for ln in moved:
        key = ln.strip().lower()
        if key in seen_m:
            continue
        seen_m.add(key)
        uniq_moved.append(ln)
    new_lines = [x for x in keep if str(x).strip()] + uniq_moved
    try:
        text = "\\n".join(new_lines)
        if new_lines:
            text += "\\n"
        path.write_text(text, encoding="utf-8")
    except Exception as exc:
        if log:
            log(f"[pending] rotate write fail: {exc}")
        return False
    if log:
        log(
            f"[pending] rotated {target} to end of {path.name} "
            f"(moved={len(uniq_moved)} remain={len(new_lines)})"
        )
    return True


'''
# In this file content, we need real newlines in the generated function. Use chr.
nl = chr(10)
new_fn = new_fn.replace("\\n", "<<<NL>>>")
# Wait - the triple quoted string above already has real newlines for code structure.
# The "\\n".join in the template becomes \n.join in the written source which is correct Python.
src2 = src[:start] + new_fn + src[end:]
# Fix accidental <<<NL>>> if any
src2 = src2.replace("<<<NL>>>", "\\n")
src_path.write_text(src2, encoding="utf-8")
import py_compile
py_compile.compile(str(src_path), doraise=True)

# validate join line is correct Python (backslash-n inside quotes = one escaped newline char in source)
src_check = src_path.read_text(encoding="utf-8")
for line in src_check.splitlines():
    if "rotate" in line and False:
        pass
idx = src_check.find("def rotate_pending_sso_account_to_end")
chunk = src_check[idx:idx+1200]
for line in chunk.splitlines():
    if "join" in line or "write_text" in line or "text +=" in line:
        print("SRC", repr(line))

# functional test on a copy logic
ok = ps.rotate_pending_sso_account_to_end  # reimport
import importlib
importlib.reload(ps)
head_before = Path("accounts_registered_pending_sso.txt").read_text(encoding="utf-8").splitlines()[0]
email = head_before.split("----", 1)[0]
print("test rotate", email)
ps.rotate_pending_sso_account_to_end(email, log=print)
lines = Path("accounts_registered_pending_sso.txt").read_text(encoding="utf-8").splitlines()
print("after lines", len(lines), "new_head", lines[0][:80], "tail", lines[-1][:80])
assert lines[-1].lower().startswith(email.lower())
assert not lines[0].lower().startswith(email.lower()) or len(lines)==1
print("ROTATE_OK")
