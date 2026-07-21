# -*- coding: utf-8 -*-
"""18r42d: session SSO vs Outlook mail_token import gates."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpa_xai.accounts import parse_accounts_file, parse_importable_sso_file
from protocol.sso_util import (
    classify_token_field,
    is_mail_token_blob,
    is_session_sso,
    normalize_sso_token,
)


def _mail_b64() -> str:
    blob = {
        "email": "t@outlook.com",
        "access_token": "aaa",
        "refresh_token": "bbb",
        "client_id": "cid",
    }
    raw = base64.urlsafe_b64encode(json.dumps(blob).encode()).decode().rstrip("=")
    return "b64:" + raw


def test_session_vs_mail():
    session = (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
        + base64.urlsafe_b64encode(
            json.dumps({"session_id": "abc-123", "user": "u"}).encode()
        ).decode().rstrip("=")
        + ".sig"
    )
    mail = _mail_b64()
    assert is_session_sso(session)
    assert not is_mail_token_blob(session)
    assert is_mail_token_blob(mail)
    assert not is_session_sso(mail)
    assert normalize_sso_token("-" + session) == session
    assert classify_token_field("pending_sso_no_sso") == "reason"


def test_parse_pending_not_importable(tmp_path: Path | None = None):
    root = Path(tmp_path) if tmp_path else ROOT / "matrix_runs" / "_tmp_sso_test"
    root.mkdir(parents=True, exist_ok=True)
    session = (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
        + base64.urlsafe_b64encode(
            json.dumps({"session_id": "zzz", "user": "u"}).encode()
        ).decode().rstrip("=")
        + ".sig"
    )
    mail = _mail_b64()
    pending = root / "pending.txt"
    nl = chr(10)
    pending.write_text(
        f"a@outlook.com----pw1----pending_sso_no_sso----{mail}{nl}"
        f"b@outlook.com----pw2----{session}{nl}",
        encoding="utf-8",
    )
    rows = parse_accounts_file(pending, include_pending=True)
    assert len(rows) == 2
    by = {r.email: r for r in rows}
    assert by["a@outlook.com"].sso == ""
    assert by["a@outlook.com"].mail_token
    assert by["a@outlook.com"].kind == "pending_mail_token"
    assert by["b@outlook.com"].sso
    assert is_session_sso(by["b@outlook.com"].sso)
    imp = parse_importable_sso_file(pending)
    assert len(imp) == 1
    assert imp[0].email == "b@outlook.com"


if __name__ == "__main__":
    test_session_vs_mail()
    test_parse_pending_not_importable()
    print("ok")
