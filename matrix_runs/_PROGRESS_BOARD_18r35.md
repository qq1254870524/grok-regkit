# PROGRESS BOARD 18r35k — live matrix validation 2026-07-20

## Status: VALIDATED + RELEASE NOTES PACKAGE

### Gateways (kept running)
- 8092 grok-regkit web OK
- 8010 Grok2API OK
- 8080 Sub2API OK
- 8317/8318 CPA/CLIProxy OK

### Session totals (api/status after runs)
- session_success ≈ 30
- session_fail = 0
- session_pending_sso = 2 (legacy outlook empty-mail from prior hybrid socks cell)
- jobs_finished = 7 this continuous session

### Cells
1. hybrid×direct×aol 4/0/0
2. hybrid×socks×aol 4/0/0
3. browser×direct×aol 4/0/0
4. browser×socks×aol 4/0/0
5. pending_sso recover 6/0/0
(+ prior outlook cells)

### RATE_LIMIT hard fails: 0

### Release
- Existing hotfix tag kept: stable-2026-07-20-matrix-hotfix-18r35k
- New validation package tag: stable-2026-07-20-matrix-validation-18r35k-live
