#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import CLIProxy/CPA xai-*.json OAuth files into Sub2API.

Usage examples:
  python -B scripts/import_cpa_to_sub2api.py --dir "C:\\Users\\zhang\\Desktop\\Grok\\cpa"
  python -B scripts/import_cpa_to_sub2api.py --file path\\to\\xai-xxx.json --verify
  python -B scripts/import_cpa_to_sub2api.py --dir ./cpa_auths --limit 20 --no-verify

Never prints access/refresh/id tokens or admin password.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sub2api_client import (  # noqa: E402
    import_cpa_dir_to_sub2api,
    import_cpa_file_to_sub2api,
    parse_cpa_auth_file,
)


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _log(msg: str) -> None:
    print(msg, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import CPA/CLIProxy xai OAuth JSON into Sub2API")
    parser.add_argument("--dir", dest="directory", default="", help="CPA auth directory (xai-*.json)")
    parser.add_argument("--file", dest="file", default="", help="Single CPA auth JSON file")
    parser.add_argument("--config", default=str(ROOT / "config.json"), help="config.json path")
    parser.add_argument("--limit", type=int, default=0, help="Max files for directory import")
    parser.add_argument("--verify", action="store_true", help="Run Sub2API account test after import")
    parser.add_argument("--no-verify", action="store_true", help="Skip account test (default for dir)")
    parser.add_argument("--no-update", action="store_true", help="Do not update existing accounts")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop directory import on first error")
    parser.add_argument("--dry-parse", action="store_true", help="Only parse and print meta, no API calls")
    args = parser.parse_args(argv)

    if not args.directory and not args.file:
        parser.error("需要 --dir 或 --file")

    cfg = _load_config(Path(args.config))
    verify = bool(args.verify)
    if args.no_verify:
        verify = False
    elif args.file and not args.verify and not args.no_verify:
        # single file defaults to config verify setting via wrapper when verify_after_import=None
        verify = None  # type: ignore

    update_existing = not args.no_update

    if args.file:
        path = Path(args.file)
        if args.dry_parse:
            parsed = parse_cpa_auth_file(path)
            safe = {
                "email": parsed.get("email"),
                "sub": parsed.get("sub"),
                "has_access_token": parsed.get("has_access_token"),
                "has_refresh_token": parsed.get("has_refresh_token"),
                "has_id_token": parsed.get("has_id_token"),
                "has_sso": parsed.get("has_sso"),
                "client_id": parsed.get("client_id"),
                "team_id": parsed.get("team_id"),
                "expires_at": parsed.get("expires_at"),
                "base_url": parsed.get("base_url"),
                "source": Path(str(parsed.get("source") or path)).name,
            }
            print(json.dumps(safe, ensure_ascii=False, indent=2))
            return 0
        result = import_cpa_file_to_sub2api(
            path,
            config=cfg,
            log_callback=_log,
            update_existing=update_existing,
            verify_after_import=verify,
        )
        safe = {
            "ok": result.get("ok"),
            "action": result.get("action") or result.get("mode"),
            "account_id": result.get("account_id"),
            "email": result.get("email"),
            "usable": result.get("usable"),
            "source": Path(str(result.get("source") or path)).name,
        }
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    directory = Path(args.directory)
    if args.dry_parse:
        from sub2api_client import iter_cpa_auth_files

        files = iter_cpa_auth_files(directory)
        if args.limit:
            files = files[: args.limit]
        rows = []
        for p in files:
            try:
                parsed = parse_cpa_auth_file(p)
                rows.append(
                    {
                        "file": p.name,
                        "email": parsed.get("email"),
                        "sub": (str(parsed.get("sub") or "")[:12] + "...") if parsed.get("sub") else "",
                        "has_refresh": bool(parsed.get("has_refresh_token")),
                        "has_sso": bool(parsed.get("has_sso")),
                    }
                )
            except Exception as exc:
                rows.append({"file": p.name, "error": f"{type(exc).__name__}: {exc}"})
        print(json.dumps({"total": len(rows), "items": rows}, ensure_ascii=False, indent=2))
        return 0

    # directory default: no verify unless --verify
    dir_verify = True if args.verify else False
    summary = import_cpa_dir_to_sub2api(
        directory,
        config=cfg,
        log_callback=_log,
        update_existing=update_existing,
        verify_after_import=dir_verify,
        limit=int(args.limit or 0),
        stop_on_error=bool(args.stop_on_error),
    )
    safe = {
        "ok": summary.get("ok"),
        "directory": summary.get("directory"),
        "total": summary.get("total"),
        "imported": summary.get("imported"),
        "created": summary.get("created"),
        "updated": summary.get("updated"),
        "failed": summary.get("failed"),
        "errors": summary.get("errors") or [],
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
