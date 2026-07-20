from pathlib import Path
import re

path = Path(r"C:\Users\zhang\grok-regkit\grok_register_ttk.py")
text = path.read_text(encoding="utf-8")

# Fix both burn blocks to mint password when empty
old_snip = '''                                    burn_mailbox_to_pending(
                                        email,
                                        "",
                                        reason=_reason,
                                        log=self.log,
                                        mail_token=str(dev_token or ""),
                                    )'''
new_snip = '''                                    _pw = ""
                                    try:
                                        _g, _f, _pw = build_profile()
                                    except Exception:
                                        _pw = "N" + __import__("uuid").uuid4().hex[:8] + "!a7#TmpPw9x"
                                    burn_mailbox_to_pending(
                                        email,
                                        _pw,
                                        reason=_reason,
                                        log=self.log,
                                        mail_token=str(dev_token or ""),
                                    )'''
if old_snip not in text:
    raise SystemExit('self.log burn block not found')
text = text.replace(old_snip, new_snip, 1)

old_snip2 = '''                                burn_mailbox_to_pending(
                                    email,
                                    "",
                                    reason=_reason,
                                    log=log,
                                    mail_token=str(dev_token or ""),
                                )'''
new_snip2 = '''                                _pw = ""
                                try:
                                    _g, _f, _pw = build_profile()
                                except Exception:
                                    _pw = "N" + __import__("uuid").uuid4().hex[:8] + "!a7#TmpPw9x"
                                burn_mailbox_to_pending(
                                    email,
                                    _pw,
                                    reason=_reason,
                                    log=log,
                                    mail_token=str(dev_token or ""),
                                )'''
if old_snip2 not in text:
    raise SystemExit('cli burn block not found')
text = text.replace(old_snip2, new_snip2, 1)

# also allow save_to_pending with empty password if mail_token present - better fix hybrid
path.write_text(text, encoding="utf-8")
print('browser path password mint ok')

# hybrid: allow pending save when email + mail_token even if password empty (use placeholder)
hpath = Path(r"C:\Users\zhang\grok-regkit\hybrid_register.py")
ht = hpath.read_text(encoding="utf-8")
old = '''    em = (email or "").strip()
    pw = (password or "").strip()
    if not em or not pw:
        if log:
            log(f"[hybrid] skip pending_sso save missing email/password reason={reason}")
        return None'''
new = '''    em = (email or "").strip()
    pw = (password or "").strip()
    if not em:
        if log:
            log(f"[hybrid] skip pending_sso save missing email reason={reason}")
        return None
    if not pw:
        # 18r29b: code-timeout / early_no_new_mail may burn before profile password exists
        pw = "PENDING_NO_PW"
        if log:
            log(f"[hybrid] pending_sso password placeholder used email={em} reason={reason}")'''
if old not in ht:
    raise SystemExit('hybrid save guard not found')
if "PENDING_NO_PW" not in ht:
    ht = ht.replace(old, new, 1)
    # changelog
    if "18r29b" not in ht[:800]:
        ht = ht.replace(
            "- 2026-07-19r25:",
            "- 2026-07-19r29b: pending_sso 允许无密码占位写入（early_no_new_mail/验证码超时仍落盘+mail_token）；browser 同步 burn。\n- 2026-07-19r25:",
            1,
        )
    hpath.write_text(ht, encoding="utf-8")
    print('hybrid pending password guard patched')
else:
    print('hybrid already has PENDING_NO_PW')

import py_compile
py_compile.compile(str(path), doraise=True)
py_compile.compile(str(hpath), doraise=True)
print('compile ok')

# retro-save venitamargiebl6 to pending with token
import sys
sys.path.insert(0, r'C:\Users\zhang\grok-regkit')
from hybrid_register import save_to_pending_sso_file, remove_mailbox_from_pool
root = Path(r'C:\Users\zhang\grok-regkit')
token=''
for line in (root/'mail_credentials.txt').read_text(encoding='utf-8',errors='replace').splitlines():
    if line.startswith('venitamargiebl6@outlook.com'):
        parts=line.split('\t',1)
        if len(parts)==2: token=parts[1].strip()
save_to_pending_sso_file('venitamargiebl6@outlook.com','',reason='early_no_new_mail',log=print,mail_token=token)
pend=(root/'accounts_registered_pending_sso.txt').read_text(encoding='utf-8',errors='replace')
print('in_pending', 'venitamargiebl6' in pend)
