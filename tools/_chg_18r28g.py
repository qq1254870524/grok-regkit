from pathlib import Path
p = Path("CHANGELOG.md")
old = p.read_text(encoding="utf-8")
entry = """# CHANGELOG

## 2026-07-19r28g / restore: stable-2026-07-19-pending-turnstile-18r28g

- **二次补 SSO 登录失败不再二次点登录**：`page_err in {auth_error,bad_password,account_missing,need_reregister}` 首次 submit 后立刻 `fail_reason=auth_error` → hybrid 重注册；日志 `NO second login click`。
- **sign-in 停顿 ≥10s 无 SSO**：`still on sign-in after first submit ... NO re-fill login` → 立即重注册（删除旧 re-fill 再点登录路径）。
- **CF stuck 后**：仅 inject Turnstile token，**禁止** re-fill + 再点登录（18r28g）；超时走重注册。
- **邮箱路由按域名/token**：`resolve_mailbox_provider`；全局 `email_provider=aol` 时 Outlook 仍走 Graph（修复 `AOL missing password for xxx@outlook.com`）。
- **热重载**：pending job 重载 `grok_register_ttk` + `pending_sso_recovery` 等，无需整进程重启。
- 实跑 pending_sso_recovery count=2：success=2 fail=0；两条均 login auth_error → IMMEDIATE re-register → Outlook Graph 收码 → protocol SignUp sso wrapper→session152 → g2a/Sub2API/CPA/NSFW 完成；pending 成功移出。
- 主路径不变：注册 → 即时 SSO → 入池；pending 仅兜底。
- 不覆盖旧 packages/releases/tags。

"""
if "18r28g" not in old[:1200]:
    # replace leading # CHANGELOG
    if old.startswith("# CHANGELOG"):
        p.write_text(entry + old[len("# CHANGELOG"):].lstrip("\n"), encoding="utf-8")
    else:
        p.write_text(entry + old, encoding="utf-8")
    print("changelog_ok")
else:
    print("changelog_exists")
