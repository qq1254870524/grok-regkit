# Restore stable-2026-07-19-sso-hold-signup-18r26

1. Stop only 8092 (keep 8010/8080/8317/8318)
2. Copy package files over grok-regkit or `git checkout stable-2026-07-19-sso-hold-signup-18r26`
3. `python -B web/server.py` or tools/start_web8092_hidden.ps1
4. Pending SSO now requires Turnstile solve before login submit
