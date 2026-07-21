# -*- coding: utf-8 -*-
"""Focused 18r44c validation: browser AOL + recovery + stop (2 rounds each)."""
from __future__ import annotations
import os, sys
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
sys.path.insert(0, str(ROOT / "tools"))
# set new out before import
from datetime import datetime
out = ROOT / "matrix_runs" / f"matrix_18r44c_validate_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.environ["MATRIX_OUT"] = str(out)
# patch cells by importing module after env
import importlib.util
spec = importlib.util.spec_from_file_location("matrix_18r44", ROOT / "tools" / "matrix_18r44_silent_stable.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.CELLS = [
    {"name": "browser__socks5__aol", "kind": "register", "register_mode": "browser", "proxy_mode": "socks5_list", "email_provider": "aol"},
    {"name": "pending_sso_recovery__socks5", "kind": "pending_sso_recovery", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
    {"name": "stop_test__hybrid__socks5", "kind": "stop_test", "register_mode": "hybrid", "proxy_mode": "socks5_list", "email_provider": "outlook"},
]
m.ROUNDS = 2
m.WORKERS = 2
m.PREHEAT = 4
m.COUNT = 4
print("OUT", m.OUT)
m.main()
