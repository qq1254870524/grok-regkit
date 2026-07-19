from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_post_matrix_r25_release.py")
t = p.read_text(encoding="utf-8")
# Update TAGS to include 18r26 and keep 18r24c/18r25
old_tags = '''TAGS = [
    ("stable-2026-07-19-outlook-sso-nudge-18r23", "18r23 Outlook strict post-send + browser SSO nudge", "stable-2026-07-19-outlook-sso-nudge-18r23.zip"),
    ("stable-2026-07-19-pending-rotate-18r24c", "18r24c profile timeout/classify/pending rotate", "stable-2026-07-19-pending-rotate-18r24c.zip"),
    ("stable-2026-07-19-nsfw-direct-18r25", "18r25 NSFW socks->direct + Outlook early 110s + reload", "stable-2026-07-19-nsfw-direct-18r25.zip"),
]
'''
new_tags = '''TAGS = [
    ("stable-2026-07-19-outlook-sso-nudge-18r23", "18r23 Outlook strict post-send + browser SSO nudge", "stable-2026-07-19-outlook-sso-nudge-18r23.zip"),
    ("stable-2026-07-19-pending-rotate-18r24c", "18r24c profile timeout/classify/pending rotate", "stable-2026-07-19-pending-rotate-18r24c.zip"),
    ("stable-2026-07-19-nsfw-direct-18r25", "18r25 NSFW socks->direct + Outlook early 110s + reload", "stable-2026-07-19-nsfw-direct-18r25.zip"),
    ("stable-2026-07-19-sso-hold-signup-18r26", "18r26 browser SSO nudge hold on active signup form", "stable-2026-07-19-sso-hold-signup-18r26.zip"),
]
'''
if old_tags not in t:
    print('tags block missing or already changed')
else:
    t = t.replace(old_tags, new_tags, 1)
    print('tags updated')
# extend git_release to build 18r26
if 'stable-2026-07-19-sso-hold-signup-18r26' not in t.split('def git_release')[1][:2500]:
    needle = 'build_pkg("stable-2026-07-19-nsfw-direct-18r25", notes25)\n    write_report()'
    repl = '''build_pkg("stable-2026-07-19-nsfw-direct-18r25", notes25)
    notes26 = (
        "18r26 browser SSO nudge: never navigate away while signup form still present\\n"
        "pure signing-in dwell 18s before grok.com nudge\\n"
        "18r25 NSFW proxy->direct + Outlook early 110s included\\n"
    )
    build_pkg("stable-2026-07-19-sso-hold-signup-18r26", notes26)
    write_report()'''
    if needle not in t:
        print('build needle missing')
    else:
        t = t.replace(needle, repl, 1)
        print('build 18r26 added')
# commit message
t = t.replace(
    '18r25: NSFW socks->direct; Outlook early 110s; hot reload; packages 18r24c+18r25',
    '18r26: SSO hold on signup form; 18r25 NSFW direct; packages 18r24c+18r25+18r26'
)
p.write_text(t, encoding='utf-8')
print('post script updated')
import py_compile
py_compile.compile(str(p), doraise=True)
print('post syntax ok')
# note: running post process already loaded old script - need restart post after weak OR it uses old tags
print('NOTE: live post PID still has old code until restart')
