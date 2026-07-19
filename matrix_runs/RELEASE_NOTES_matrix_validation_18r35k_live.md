# RELEASE NOTES — matrix-validation-18r35k-live (2026-07-20)

## Tag
`stable-2026-07-20-matrix-validation-18r35k-live`

Does **not** overwrite `stable-2026-07-20-matrix-hotfix-18r35k` or older Packages.

## What this package is
Live multi-cell matrix validation on hotfixed **18r35k** tree (no code regression vs 18r35k).
Documents proven success rates and operational notes after cross runs.

## Matrix results (plain)
### Register
- hybrid×direct×aol: 4/0/0
- hybrid×socks5×aol: 4/0/0
- browser×direct×aol: 4/0/0
- browser×socks5×aol: 4/0/0
- browser×direct×outlook (prior): 6/0/0
- hybrid×socks5×outlook (prior): 2/0/2 pending (mailbox empty, not code bug)

### pending_sso recover
- count=6 workers=3: **6/0/0**
- Turnstile token used on sign-in
- Login fail path re-registers (no login hammer loop)

### Anti rate-limit
- 0× 「验证码过多」 hard fail across this session
- skip re-click + 4.0s CreateEmail gate working

## Main path (unchanged)
register success → **instant SSO** → NSFW → Grok2API → CPA OIDC → Sub2API
`accounts_registered_pending_sso.txt` is fallback only.

## Ops
- Web UI: http://127.0.0.1:8092
- Stop register only: POST /api/stop
- Keep gateways: 8010 G2A, 8080 Sub2, 8317/8318 CPA/CLIProxy

## Files
- matrix_runs/CELL_RESULTS_18r35k.md
- matrix_runs/NOTE_rate_limit_create_email_18r35k.md (prior)
- source zip of current tree (secrets excluded by .gitignore)

### Post-release outlook cell
- hybrid×direct×outlook count=4 w=2: **3/0/1** pending (early_no_new_mail class; 0 RATE_LIMIT)

