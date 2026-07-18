
## 2026-07-19 18r28g pending no-second-login

- Tag/release/package: `stable-2026-07-19-pending-turnstile-18r28g` (non-overwrite)
- Commits: `68a604e` (fix) + `0b9c4a5` (packages)
- Fix: login `auth_error` after first Turnstile submit -> IMMEDIATE hybrid re-register; CF-stuck inject-only; Outlook route by domain even if configured=aol
- Run A pending count=2: success=2 fail=0 (touseysiagosto9, jodyceciliafnx) auth_error->reregister->Graph code->SignUp sso152->pool/CPA/NSFW
- Run B pending count=2 in progress after release (pensamorisem success path same; spaethkindtj started)


# MATRIX_REPORT
