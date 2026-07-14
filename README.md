# grok-regkit

xAI / Grok **account registration toolkit** (open snapshot):

| Feature | Description |
|---------|-------------|
| Modes | `browser` full Chromium · `hybrid` protocol RPC + short browser for tokens |
| SSO | `accounts_*.txt` · optional token pool (web models e.g. 4.20 / 4.3) |
| OIDC / CPA | Prefer protocol mint → `cpa_auths/xai-*.json` → CLIProxyAPI → **grok-4.5** |
| UI | Web console · GUI · CLI |

> **SSO ≠ OIDC.** SSO alone is not Build 4.5 auth. See [`docs/sso-cpa/`](./docs/sso-cpa/).

**Research / personal learning only.** Follow site ToS and local law. See [`NOTICE.md`](./NOTICE.md).

---

## Quick start

```bash
cd grok-regkit
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.json config.json
# fill mail API, proxy, register_mode
```

### Web (recommended)

```bash
# Linux + Xvfb: export DISPLAY=:99
uvicorn web.server:app --host 127.0.0.1 --port 8092 --workers 1
```

### GUI / CLI

```bash
python grok_register_ttk.py
python grok_register_ttk.py --cli
```

Hybrid: `"register_mode": "hybrid"` in `config.json`.

---

## Architecture

```text
temp mail ──► register accounts.x.ai ──► SSO
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
     pool (SSO)           CPA mint (OIDC)
     web reverse-proxy    xai-*.json → 4.5
```

| Doc | Content |
|-----|---------|
| [docs/sso-cpa/](./docs/sso-cpa/) | Mode matrix · SSO vs OIDC |
| [LOCAL_RUN.md](./LOCAL_RUN.md) | Local run details |
| [OPEN_SOURCE.md](./OPEN_SOURCE.md) | Snapshot sync from private tree |
| [SECURITY.md](./SECURITY.md) | Secrets & reporting |
| [NOTICE.md](./NOTICE.md) | Use boundaries |

**Related (not bundled):** [grokcli-2api](https://github.com/HM2899/grokcli-2api) is an OIDC API gateway + protocol register path. This kit focuses on **registration + CPA export**; hybrid still uses a browser for Turnstile/castle. Pure-HTTP + captcha services are a different trade-off (lighter, captcha cost, weaker vs hard CF pages).

---

## Layout

```text
grok-regkit/
  grok_register_ttk.py   # browser register + job runner
  hybrid_register.py     # hybrid register
  browser/ protocol/     # hybrid deps
  cpa_xai/ cpa_export.py # OIDC mint
  web/                   # FastAPI console
  scripts/               # backfill helpers
  docs/sso-cpa/
  config.example.json
```

---

## Requirements

- Python 3.9+ (3.11 / 3.12 recommended)
- Chrome / Chromium
- Reachable `accounts.x.ai`, mail API, proxy as needed
- Linux servers: Xvfb + headed Chromium recommended

---

## License

MIT — see [LICENSE](./LICENSE).

## Disclaimer

Not affiliated with xAI / Grok. Automation may get accounts or IPs banned. You use this at your own risk.
