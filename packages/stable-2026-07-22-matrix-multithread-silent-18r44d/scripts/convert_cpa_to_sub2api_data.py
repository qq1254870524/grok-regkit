#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert CLIProxy/CPA xai-*.json into Sub2API backup export JSON.

Output shape:
  {
    "type": "sub2api-data",
    "version": 1,
    "exported_at": "...",
    "proxies": [],
    "accounts": [{platform:grok,type:oauth,credentials:...}]
  }

This is what Sub2API Web "导入数据" accepts. Raw xai-*.json is NOT accepted by
stock Sub2API Import Data UI.

Usage:
  python -B scripts/convert_cpa_to_sub2api_data.py --file path\\to\\xai-xxx.json --out out.json
  python -B scripts/convert_cpa_to_sub2api_data.py --dir "C:\\Users\\zhang\\Desktop\\Grok\\cpa" --out bundle.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sub2api_client import iter_cpa_auth_files, parse_cpa_auth_file  # noqa: E402


def _account_from_parsed(parsed: dict) -> dict:
    name = str(parsed.get("name") or parsed.get("email") or "grok-cpa").strip()
    return {
        "name": name,
        "platform": "grok",
        "type": "oauth",
        "credentials": parsed.get("credentials") or {},
        "concurrency": 1,
        "priority": 50,
        "auto_pause_on_expired": True,
    }


def build_payload(paths: list[Path]) -> dict:
    accounts = []
    for path in paths:
        parsed = parse_cpa_auth_file(path)
        accounts.append(_account_from_parsed(parsed))
    return {
        "type": "sub2api-data",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "proxies": [],
        "accounts": accounts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert CPA xai JSON to Sub2API data export")
    parser.add_argument("--dir", dest="directory", default="")
    parser.add_argument("--file", dest="file", default="")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.directory and not args.file:
        parser.error("需要 --dir 或 --file")

    paths: list[Path] = []
    if args.file:
        paths.append(Path(args.file))
    if args.directory:
        paths.extend(iter_cpa_auth_files(args.directory))
    # de-dupe preserve order
    seen = set()
    uniq: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    if args.limit and args.limit > 0:
        uniq = uniq[: args.limit]
    if not uniq:
        print("no cpa files", file=sys.stderr)
        return 2

    payload = build_payload(uniq)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] wrote {out} accounts={len(payload['accounts'])} files={len(uniq)}")
    print("[*] 这个文件可以直接在 Sub2API 网页「导入数据」上传")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
