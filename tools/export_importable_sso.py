#!/usr/bin/env python3
"""CLI: merge recovered/hybrid session SSO into accounts_importable_sso_*.txt"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.export_importable_sso import write_importable_sso_export


def main() -> int:
    meta = write_importable_sso_export(ROOT)
    print(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
