# Restore stable-2026-07-19-outlook-sso-nudge-18r23

1. Stop only grok-regkit web 8092 (do not kill 8010/8080/8317/8318).
2. Copy files from this package over `C:\Users\zhang\grok-regkit` (or checkout tag).
3. Start: `python -B web/server.py`
4. Keep Sub2API/g2a/CLIProxy/cpa_gateway running.

Files included:
- hybrid_register.py
- outlook_mail.py
- grok_register_ttk.py
- aol_mail.py
- tools/matrix_cross_run.py
- docs/CPA_AUTH_JSON_FORMAT.md
- web/server.py
- web/index.html
- sso_to_auth_json.py
- browser/token_harvester.py
- AGENT_COORD.md
- cpa_export.py
- CHANGELOG.md
- README.md
