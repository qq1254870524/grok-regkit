"""Export only importable session-SSO account lines.

18r42d: merge recovered/reregistered/hybrid success files into a clean
email----password----session_sso dump. Never include pending mail_token rows.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]


def _iter_source_files(root: Path) -> list[Path]:
    pats = (
        "accounts_reregistered_*.txt",
        "accounts_pending_sso_recovered_*.txt",
        "accounts_hybrid_*.txt",
        "accounts_hybrid*.txt",
        "accounts_cli.txt",
        "accounts_success_*.txt",
    )
    seen: set[str] = set()
    out: list[Path] = []
    for pat in pats:
        for p in sorted(root.glob(pat), key=lambda x: x.stat().st_mtime if x.is_file() else 0):
            key = str(p.resolve()).lower()
            if key in seen:
                continue
            # never export pending queue
            name = p.name.lower()
            if "pending_sso" in name and "recovered" not in name:
                continue
            if name.startswith("accounts_no_sso"):
                continue
            if name == "accounts_registered_pending_sso.txt":
                continue
            if name.startswith("accounts_pending_sso_exhausted"):
                continue
            seen.add(key)
            out.append(p)
    return out


def collect_importable_sso_lines(
    root: Optional[Path] = None,
    *,
    sources: Optional[Iterable[Path]] = None,
) -> tuple[list[str], dict]:
    root = Path(root or ROOT)
    try:
        from protocol.sso_util import is_session_sso, normalize_sso_token
    except Exception:
        from sso_util import is_session_sso, normalize_sso_token  # type: ignore

    files = list(sources) if sources is not None else _iter_source_files(root)
    by_email: dict[str, tuple[str, str, str]] = {}  # em -> (pw, sso, src)
    scanned = 0
    kept = 0
    skipped_mail = 0
    skipped_other = 0
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#") or "----" not in s:
                continue
            scanned += 1
            parts = s.split("----")
            if len(parts) < 3 or "@" not in parts[0]:
                skipped_other += 1
                continue
            email = parts[0].strip()
            password = parts[1].strip()
            sso = ""
            for part in parts[2:]:
                if is_session_sso(part):
                    sso = normalize_sso_token(part)
                    break
            if not sso:
                # mail_token / reason / wrapper
                blob = "----".join(parts[2:])
                if "b64:" in blob or ("access_token" in blob and "refresh_token" in blob):
                    skipped_mail += 1
                else:
                    skipped_other += 1
                continue
            key = email.lower()
            prev = by_email.get(key)
            # prefer longer session sso (usually stable 152)
            if prev is None or len(sso) >= len(prev[1]):
                by_email[key] = (password, sso, path.name)
            kept += 1

    out_lines = [
        f"{email}----{pw}----{sso}"
        for email, (pw, sso, _src) in sorted(by_email.items(), key=lambda kv: kv[0])
    ]
    meta = {
        "files_scanned": len(files),
        "rows_scanned": scanned,
        "rows_with_session_sso": kept,
        "unique_emails": len(out_lines),
        "skipped_mail_token": skipped_mail,
        "skipped_other": skipped_other,
        "sources": [p.name for p in files[:80]],
    }
    return out_lines, meta


def write_importable_sso_export(
    root: Optional[Path] = None,
    *,
    out_path: Optional[Path] = None,
) -> dict:
    root = Path(root or ROOT)
    lines, meta = collect_importable_sso_lines(root)
    if out_path is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = root / f"accounts_importable_sso_{stamp}.txt"
    else:
        out_path = Path(out_path)
    nl = chr(10)
    body = nl.join(lines)
    if body:
        body += nl
    out_path.write_text(body, encoding="utf-8")
    meta["out_file"] = out_path.name
    meta["out_path"] = str(out_path)
    meta["line_count"] = len(lines)
    return meta
