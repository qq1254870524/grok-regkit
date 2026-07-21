from pathlib import Path

# matrix: faster permanent-verify for silent stable matrix
mp = Path("tools/matrix_18r43_silent_stable_mt.py")
mt = mp.read_text(encoding="utf-8")
if "sub2api_verify_timeout_sec" not in mt:
    # inject near post_success_workers
    needle = '        "post_success_workers": 6,'
    add = '''        "post_success_workers": 6,
        # 18r43f: permanent permission-denied fail-fast; short verify keeps awaiting_pool moving
        "sub2api_verify_after_add": True,
        "sub2api_require_verify_success": False,
        "sub2api_verify_attempts": 1,
        "sub2api_verify_timeout_sec": 35,
        "sub2api_verify_retry_delay_sec": 1,'''
    if needle not in mt:
        raise SystemExit("matrix needle missing")
    mt = mt.replace(needle, add, 1)
    mp.write_text(mt, encoding="utf-8")
    print("matrix inject ok")
else:
    print("matrix already has verify timeout keys")

# package notes append 18r43f if present
pp = Path("tools/package_18r43_silent.py")
if pp.exists():
    pt = pp.read_text(encoding="utf-8")
    if "18r43f" not in pt:
        pt2 = pt.replace("18r43e", "18r43e / 18r43f", 1) if "18r43e" in pt else pt
        if "18r43f" not in pt2:
            # try notes list
            if "notes" in pt2 or "NOTES" in pt2 or "18r43" in pt2:
                pt2 = pt2.replace("18r43e resume", "18r43e resume; 18r43f Sub2API verify fail-fast permanent 403", 1)
        pp.write_text(pt2, encoding="utf-8")
        print("package notes touched")
    else:
        print("package already 18r43f")

# changelog IN PROGRESS line
cp = Path("CHANGELOG.md")
if cp.exists():
    ct = cp.read_text(encoding="utf-8")
    if "18r43f" not in ct:
        ct = ct.replace(
            "18r43 **IN PROGRESS**",
            "18r43 **IN PROGRESS** (18r43f Sub2API verify fail-fast permanent permission-denied)",
            1,
        )
        if "18r43f" not in ct:
            # prepend under first ## 
            lines = ct.splitlines(True)
            for i,l in enumerate(lines):
                if "18r43" in l and ("IN PROGRESS" in l or "2026-07-21" in l):
                    lines.insert(i+1, "- 18r43f: Sub2API 可用性验证对 permanent permission-denied 立即失败，避免 awaiting_pool 被 105s×N 拖死（下一次 /api/start 生效）\n")
                    break
            ct = "".join(lines)
        cp.write_text(ct, encoding="utf-8")
        print("changelog updated")
    else:
        print("changelog already 18r43f")

print("done")
