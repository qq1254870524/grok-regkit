# CHANGELOG — stable-2026-07-21-matrix-multithread-18r40

## 2026-07-21 / matrix 18r40 multi-thread full cross-run (workers=2, count=4, preheat=4)

### Summary
- **Tag / Package**: `stable-2026-07-21-matrix-multithread-18r40` (does **not** overwrite older Packages)
- Multi-thread matrix: hybrid × full-browser × proxy (direct/SOCKS5) × mail (Outlook/AOL) × 2 rounds
- Plus pending SSO recovery (direct/SOCKS5 × 2) + stop registration tests × 2
- Total **22 cells**, all finished
- Session totals during matrix: success≈59, fail≈7, pending_sso≈1
- Hidden Python: no console windows (`CREATE_NO_WINDOW` / `start_web8092_hidden.ps1` / `start_hidden.ps1`)

### Stop logic (validated ×2)
- `POST /api/stop`: set stop Event **first** → double `force_stop_registration` (browsers / preflight / workers)
- Clear running flag + pending job threads
- **Does not kill** G2A/Sub2/CPA gateways on 8010/8318 (or 8092 web itself)
- Matrix stop cells: both `stop_ok=true`, `running_after=false`, browsers cleaned, gateways stayed LISTENING

### Register matrix results (target 4 each)
| Cell | success | fail | pending_sso |
|------|---------|------|-------------|
| hybrid__direct__outlook r1/r2 | 4/4 | 0/0 | 0/0 |
| hybrid__direct__aol r1/r2 | 4/4 | 0/0 | 0/0 |
| hybrid__socks5_list__outlook r1/r2 | 3/4 | 0/0 | 1/0 |
| hybrid__socks5_list__aol r1/r2 | 4/4 | 0/0 | 0/0 |
| browser__direct__outlook r1/r2 | 2/2 | 2/2 | 0/0 |
| browser__direct__aol r1/r2 | 4/4 | 0/0 | 0/0 |
| browser__socks5_list__outlook r1/r2 | 2/3 | 2/1 | 0/0 |
| browser__socks5_list__aol r1/r2 | 4/4 | 0/0 | 0/0 |

### Pending SSO recovery
| Cell | success | notes |
|------|---------|-------|
| pending_sso_recovery__direct__r1 | 3 | solid |
| pending_sso_recovery__direct__r2 | 0 | soft zero under auth_error / re-register churn |
| pending_sso_recovery__socks5_list__r1 | 0 | soft zero |
| pending_sso_recovery__socks5_list__r2 | 0 | soft zero |

### Key code (18r35–18r40 lineage, packaged tree)
- `web/server.py`: 18r40 stop Event + double force_stop + running clear; gateways kept
- `worker_coord.py`: continuous preflight stop on force_stop; MT coordination
- `outlook_mail.py` / `aol_mail.py`: poll / early_no_new adjustments
- `grok_register_ttk.py`: create-email / UI fallback / browser path fixes
- `tools/matrix_18r40_multithread.py`: full 22-cell matrix runner
- `tools/start_web8092_hidden.ps1`, `tools/start_hidden.ps1`, `tools/restart_all_hidden_18r40.ps1`

### Soft outcomes (not hard crashes)
- Browser+Outlook: frequent `early_no_new_mail` / rate-limit → ~2–3/4 success
- Browser+AOL: reliable 4/4 all rounds
- Pending SSO under load: often soft zero after auth_error → hybrid re-register → UI fallback
- Sub2API post-process may hold cell end ~10–30s; reconcile runs at job end

### Residual / next
- Browser CreateEmail protocol-rescue parity with hybrid
- Map more `early_no_new_mail` on browser path to `pending_sso` instead of hard fail
- Log redaction for proxy URLs / emails in live dumps

### Restore
1. Unzip or checkout tag `stable-2026-07-21-matrix-multithread-18r40`
2. Copy local `config.json` / mail pools / proxies (not in package)
3. Start web hidden: `powershell -File tools/start_web8092_hidden.ps1`
4. Open http://127.0.0.1:8092/
