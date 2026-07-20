from pathlib import Path
import py_compile
import re

p = Path(r"C:\Users\zhang\grok-regkit\pending_sso_recovery.py")
t = p.read_text(encoding="utf-8")

# Update header changelog
old_head = "18r24: pending-sso sign-in prefers ?email=true deep-link; after 2 empty social-btn clicks force email form URL."
new_head = """18r24b: pending fail rotates account to end of accounts_registered_pending_sso.txt so count=1 matrix no longer stuck on same head (e.g. doron28).
18r24: pending-sso sign-in prefers ?email=true deep-link; after 2 empty social-btn clicks force email form URL."""
if old_head in t and "18r24b:" not in t:
    t = t.replace(old_head, new_head, 1)

rotate_fn = '''
def rotate_pending_sso_account_to_end(email: str, log: Callable[[str], None] | None = None) -> bool:
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
            moved.append(ln if ln.strip() else parsed.get("raw") or ln)
        else:
            keep.append(ln)
    if not moved:
        return False
    # de-dupe moved, preserve last note variant
    seen_m: set[str] = set()
    uniq_moved: list[str] = []
    for ln in moved:
        key = ln.strip().lower()
        if key in seen_m:
            continue
        seen_m.add(key)
        uniq_moved.append(ln)
    new_lines = keep + uniq_moved
    try:
        path.write_text(("\\n".join(new_lines) + ("\\n" if new_lines else "")), encoding="utf-8")
    except Exception as exc:
        if log:
            log(f"[pending] rotate write fail: {exc}")
        return False
    if log:
        log(f"[pending] rotated {target} to end of {path.name} (moved={len(uniq_moved)} remain_head_shift=1)")
    return True


'''

if "def rotate_pending_sso_account_to_end" not in t:
    # insert after remove_pending_sso_account
    anchor = "def recover_one_pending_sso("
    idx = t.find(anchor)
    if idx < 0:
        raise SystemExit("anchor recover_one missing")
    t = t[:idx] + rotate_fn + t[idx:]

# After fail_count += 1 block, add rotate. Find unique snippet.
old_fail = '''            else:
                fail_count += 1
                # 密码错误/账号不存在/auth_error：走 hybrid 重注册。
                # 关键：accounts_registered_pending_sso 仅在最终成功后才移出；
                # 若重注册失败仍保留原 pending，避免数据丢失。
                if fail_reason in {"bad_password", "account_missing", "auth_error"} or res.get("remove_pending"):
'''

new_fail = '''            else:
                fail_count += 1
                # 18r24b: always rotate failed head to end so next round / count=1 is not stuck.
                try:
                    rotate_pending_sso_account_to_end(email, log=log)
                except Exception as rot_exc:
                    log(f"[pending] rotate after fail error: {rot_exc}")
                # 密码错误/账号不存在/auth_error：走 hybrid 重注册。
                # 关键：accounts_registered_pending_sso 仅在最终成功后才移出；
                # 若重注册失败仍保留原 pending，避免数据丢失。
                if fail_reason in {"bad_password", "account_missing", "auth_error"} or res.get("remove_pending"):
'''

if "18r24b: always rotate failed head" not in t:
    if old_fail not in t:
        raise SystemExit("fail block not found")
    t = t.replace(old_fail, new_fail, 1)

p.write_text(t, encoding="utf-8")
py_compile.compile(str(p), doraise=True)
print("pending_sso_recovery.py patched OK")

# Immediate rotate doron28 to end for upcoming pending cells
path = Path(r"C:\Users\zhang\grok-regkit\accounts_registered_pending_sso.txt")
lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
head = lines[0] if lines else ""
print("OLD_HEAD", head[:80] if head else None)
target = "doron28@aol.com"
keep, moved = [], []
for ln in lines:
    if ln.strip().lower().startswith(target):
        moved.append(ln)
    else:
        keep.append(ln)
if moved:
    path.write_text("\\n".join(keep + moved) + "\\n", encoding="utf-8")
    print("NEW_HEAD", (keep[0] if keep else moved[0])[:80])
    print("moved", len(moved), "total", len(keep)+len(moved))
else:
    print("doron28 not in file or already not present")
