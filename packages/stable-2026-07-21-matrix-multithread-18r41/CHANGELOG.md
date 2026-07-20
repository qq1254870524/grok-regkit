# CHANGELOG — stable-2026-07-21-matrix-multithread-18r41

## 2026-07-21 / matrix 18r41 multi-thread full cross-run (workers=2, count=4, preheat=4)

### Summary
- **Tag / Package**: `stable-2026-07-21-matrix-multithread-18r41` (does **not** overwrite 18r40 or older Packages)
- Multi-thread matrix: hybrid × full-browser × proxy (direct/SOCKS5) × mail (Outlook/AOL) × 2 rounds
- Plus pending SSO recovery (direct/SOCKS5 × 2) + stop registration tests × 2
- Total **22/22 cells**, all finished
- Hidden Python: no console windows (`tools/start_hidden.ps1`)

### 18r41b fix
- Bug: multi-thread full-browser last mail retry bare-raised `early_no_new_mail` / code timeout → worker **hard fail** (pending_sso=0)
- Fix: `grok_register_ttk.py` `_register_one_browser` last mail-stage fail → burn + `pending_sso:browser_code_fail`

### Stop tests (×2)
- `/api/stop`: stop Event + kill workers + clear pending/running + double browser cleanup
- Gateways **8010/8318 kept alive** after both stop cells
- Both: `stop_ok=true`, `running_after=false`
- detail: `stopped: running cleared + double browser cleanup; gateways kept alive`

### Register cells (16)
| Cell | success | fail | pending_sso |
|------|--------:|-----:|------------:|
| hybrid__direct__outlook__r1 | 2 | 0 | 2 |
| hybrid__direct__outlook__r2 | 1 | 0 | 3 |
| hybrid__direct__aol__r1 | 4 | 0 | 0 |
| hybrid__direct__aol__r2 | 4 | 0 | 0 |
| hybrid__socks5_list__outlook__r1 | 3 | 0 | 1 |
| hybrid__socks5_list__outlook__r2 | 1 | 0 | 3 |
| hybrid__socks5_list__aol__r1 | 4 | 0 | 0 |
| hybrid__socks5_list__aol__r2 | 4 | 0 | 0 |
| browser__direct__outlook__r1 | 3 | 0 | 1 |
| browser__direct__outlook__r2 | 4 | 0 | 0 |
| browser__direct__aol__r1 | 4 | 0 | 0 |
| browser__direct__aol__r2 | 4 | 0 | 0 |
| browser__socks5_list__outlook__r1 | 4 | 0 | 0 |
| browser__socks5_list__outlook__r2 | 4 | 0 | 0 |
| browser__socks5_list__aol__r1 | 4 | 0 | 0 |
| browser__socks5_list__aol__r2 | 4 | 0 | 0 |

- AOL: all 8 cells **4/4**
- Browser Outlook: strong (3–4/4); Hybrid Outlook soft pending_sso (acceptable)

### Pending SSO recovery (4)
| Cell | success | fail |
|------|--------:|-----:|
| pending_sso_recovery__direct__r1 | 4 | 0 |
| pending_sso_recovery__direct__r2 | 4 | 0 |
| pending_sso_recovery__socks5_list__r1 | 4 | 0 |
| pending_sso_recovery__socks5_list__r2 | 3 | 0 |

- Much stronger than 18r40 pending path

### Tools
- `tools/matrix_18r41_multithread.py`
- `tools/start_hidden.ps1`, `tools/start_web8092_hidden.ps1`, `tools/restart_all_hidden_18r40.ps1`
- Matrix report: `matrix_runs/MATRIX_18r41_20260721_003555.md`

### Exclusions
- No `config.json`, accounts, tokens, cpa_auths, proxies secrets in package
