#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reconcile success TXT / token.json(G2A local) / G2A remote / Sub2API / CPA counts.

18r29k: ops tool for pool sync visibility. No secrets printed.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def emails_in(text: str) -> set[str]:
    return {x.lower() for x in re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text or "")}


def main() -> int:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    tok = json.loads((ROOT / "token.json").read_text(encoding="utf-8"))
    pool = str(cfg.get("grok2api_pool_name") or "ssoBasic")
    items = tok.get(pool) or []
    tok_emails = set()
    for e in items:
        if isinstance(e, dict):
            n = str(e.get("note") or e.get("email") or "").strip().lower()
            if "@" in n:
                tok_emails.add(n)

    success = set()
    for pat in (
        "accounts_hybrid*.txt",
        "accounts_browser*.txt",
        "accounts_2026*.txt",
        "accounts_reregistered*.txt",
    ):
        for f in ROOT.glob(pat):
            success |= emails_in(f.read_text(encoding="utf-8", errors="replace"))

    pending_path = ROOT / "accounts_registered_pending_sso.txt"
    pending = emails_in(pending_path.read_text(encoding="utf-8", errors="replace")) if pending_path.exists() else set()

    cpa_dir = Path(str(cfg.get("cpa_auth_dir") or "cpa_auths"))
    if not cpa_dir.is_absolute():
        cpa_dir = ROOT / cpa_dir
    cpa_n = len(list(cpa_dir.glob("*.json"))) if cpa_dir.is_dir() else 0

    # G2A remote
    remote_n = None
    try:
        base = str(cfg.get("grok2api_remote_base") or "http://127.0.0.1:8010").rstrip("/")
        key = str(cfg.get("grok2api_remote_app_key") or "")
        req = urllib.request.Request(
            base + "/admin/api/tokens",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        tokens = data.get("tokens") or []
        remote_n = len(tokens) if isinstance(tokens, list) else None
    except Exception as exc:
        remote_n = f"err:{exc}"

    # Sub2API
    sub2_n = None
    try:
        sys.path.insert(0, str(ROOT))
        from sub2api_client import get_client

        client = get_client(cfg, log_callback=None)
        token = client.login(force=False)
        _resp, payload = client._request_json(
            "GET",
            "/api/v1/admin/accounts?page=1&page_size=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = client._payload_data(payload) if isinstance(payload, dict) else {}
        sub2_n = int(data.get("total") or 0) if isinstance(data, dict) else None
    except Exception as exc:
        sub2_n = f"err:{exc}"

    report = {
        "g2a_local_token_json": len(items) if isinstance(items, list) else 0,
        "g2a_local_emails": len(tok_emails),
        "g2a_remote": remote_n,
        "sub2api_total": sub2_n,
        "cpa_files": cpa_n,
        "success_txt_emails": len(success),
        "pending_sso_emails": len(pending),
        "success_txt_not_in_token": sorted(success - tok_emails)[:30],
        "success_txt_not_in_token_count": len(success - tok_emails),
        "pending_also_in_token_count": len(pending & tok_emails),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = ROOT / "matrix_runs" / "_pool_reconcile_latest.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
