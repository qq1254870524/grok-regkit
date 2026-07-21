"""Parse register machine accounts_cli.txt lines.

18r42d: distinguish session SSO vs pending mail_token.
  - importable: email----password----session_sso
  - pending queue (NOT importable SSO): email----password----reason----b64:mail_token
  - never treat Outlook access/refresh mail_token as Grok SSO
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AccountLine:
    email: str
    password: str
    sso: str
    raw: str
    line_no: int
    mail_token: str = ""
    note: str = ""
    kind: str = ""  # session_sso | pending_mail_token | no_sso | mixed | empty


def _classify_parts(parts: list[str]) -> tuple[str, str, str, str]:
    """Return (sso, mail_token, note, kind)."""
    try:
        from protocol.sso_util import (
            classify_token_field,
            normalize_sso_token,
            pick_mail_token_from_parts,
            pick_session_sso_from_parts,
        )
    except Exception:
        # fallback: legacy 3-field behavior without mail_token acceptance
        sso = parts[2].strip() if len(parts) > 2 else ""
        if sso.lower().startswith("b64:") or (len(parts) >= 4 and parts[3].strip().lower().startswith("b64:")):
            return "", (parts[3].strip() if len(parts) >= 4 else sso), (parts[2].strip() if len(parts) >= 3 else ""), "pending_mail_token"
        return sso, "", "", ("session_sso" if sso else "empty")

    sso = pick_session_sso_from_parts(parts)
    mail_token = pick_mail_token_from_parts(parts)
    note = ""
    for part in parts[2:]:
        kind = classify_token_field(part)
        if kind == "reason":
            note = part.strip()
            break
        if kind not in {"session_sso", "mail_token", "empty"} and not note:
            # keep first non-token annotation (e.g. pending_sso_no_sso)
            if part.strip() and not part.strip().startswith("eyJ"):
                note = part.strip()

    if sso:
        return normalize_sso_token(sso), mail_token, note, "session_sso"
    if mail_token:
        return "", mail_token, note or "pending_mail_token", "pending_mail_token"
    if note:
        return "", "", note, "no_sso"
    # legacy: third field unknown — do NOT invent SSO
    third = parts[2].strip() if len(parts) > 2 else ""
    if third:
        kind = classify_token_field(third)
        if kind == "wrapper_sso":
            return normalize_sso_token(third), "", "wrapper_sso", "mixed"
        return "", "", third, "no_sso"
    return "", "", "", "empty"


def parse_accounts_file(
    path: str | Path,
    *,
    require_session_sso: bool = False,
    include_pending: bool = True,
) -> list[AccountLine]:
    """Parse account lines.

    require_session_sso=True → only rows with real session SSO (import-ready).
    include_pending=False → drop pending mail_token rows.
    """
    path = Path(path)
    out: list[AccountLine] = []
    if not path.is_file():
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split("----")
        if len(parts) < 2:
            continue
        email = parts[0].strip()
        password = parts[1].strip()
        if not email or not password:
            continue
        sso, mail_token, note, kind = _classify_parts(parts)
        if require_session_sso and not sso:
            continue
        if not include_pending and kind == "pending_mail_token":
            continue
        out.append(
            AccountLine(
                email=email,
                password=password,
                sso=sso,
                raw=s,
                line_no=i,
                mail_token=mail_token,
                note=note,
                kind=kind,
            )
        )
    return out


def parse_importable_sso_file(path: str | Path) -> list[AccountLine]:
    """Only rows with real session SSO suitable for G2A/Sub2API import."""
    return parse_accounts_file(path, require_session_sso=True, include_pending=False)


def existing_cpa_emails(auth_dir: str | Path) -> set[str]:
    """Emails already present as xai-*.json in auth_dir."""
    auth_dir = Path(auth_dir)
    found: set[str] = set()
    if not auth_dir.is_dir():
        return found
    for p in auth_dir.glob("xai-*.json"):
        name = p.name[len("xai-") : -len(".json")]
        if name:
            found.add(name.lower())
        try:
            import json

            d = json.loads(p.read_text(encoding="utf-8"))
            em = str(d.get("email") or "").strip().lower()
            if em:
                found.add(em)
        except Exception:
            continue
    return found
