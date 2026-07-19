from pathlib import Path
p = Path("MATRIX_REPORT.md")
text = p.read_text(encoding="utf-8") if p.exists() else "# MATRIX_REPORT\n"
block = """
## 2026-07-19 18r28g pending no-second-login

- Tag/release/package: `stable-2026-07-19-pending-turnstile-18r28g` (non-overwrite)
- Commits: `68a604e` (fix) + `0b9c4a5` (packages)
- Fix: login `auth_error` after first Turnstile submit -> IMMEDIATE hybrid re-register; CF-stuck inject-only; Outlook route by domain even if configured=aol
- Run A pending count=2: success=2 fail=0 (touseysiagosto9, jodyceciliafnx) auth_error->reregister->Graph code->SignUp sso152->pool/CPA/NSFW
- Run B pending count=2 in progress after release (pensamorisem success path same; spaethkindtj started)

"""
if "18r28g pending no-second-login" not in text:
    p.write_text(block + "\n" + text, encoding="utf-8")
    print("matrix_report_updated")
else:
    print("matrix_report_exists")
