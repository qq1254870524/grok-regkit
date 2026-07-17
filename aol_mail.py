# -*- coding: utf-8 -*-
"""AOL mailbox provider via IMAP protocol (email----password/app password).

Account line formats:
1) email----password          (password 或应用专用密码；用户也称为 TOTP 字段)
2) email----password----totp  (IMAP 仍用 password；totp 仅缓存备用)
Separators: ---- | , tab

create/acquire: rent mailbox from pool, IMAP LOGIN
poll_code: IMAP INBOX + Junk/Spam/Bulk, extract xAI/Grok code

Changelog:
- 2026-07-17c: 登录失败/注册成功后从账号池文件永久删除该行；内存+磁盘同步。
- 2026-07-17b: login fail -> mark bad + next account; scan ALL IMAP folders.
- 2026-07-17: initial AOL IMAP provider (imap.aol.com:993).
"""
from __future__ import annotations

import email
import imaplib
import json
import re
import ssl
import threading
import time
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import pyotp  # noqa: F401  # optional; not required for IMAP app-password
except Exception:
    pyotp = None  # type: ignore


def _log(cb, msg: str) -> None:
    if cb:
        try:
            cb(msg)
            return
        except Exception:
            pass
    print(msg)


def _root_dir() -> Path:
    return Path(__file__).resolve().parent


def _now() -> float:
    return time.time()


def _split_account_line(line: str) -> List[str]:
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        return []
    for sep in ("----", "|", "\t", ","):
        if sep in raw:
            return [p.strip() for p in raw.split(sep) if p.strip() != "" or True][:4]
    # fallback whitespace
    parts = raw.split()
    return parts[:4] if parts else []


@dataclass
class AolAccount:
    email: str
    password: str = ""
    totp_secret: str = ""
    status: str = "idle"  # idle | in_use | bad | registered
    cooldown_until: float = 0.0
    last_used_at: float = 0.0
    last_error: str = ""

    def identity(self) -> str:
        return (self.email or "").strip().lower()


def parse_account_line(line: str) -> Optional[AolAccount]:
    """Parse email----password[/app password] or email----password----totp."""
    parts = _split_account_line(line)
    # fix split that kept empty: re-split carefully
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        return None
    for sep in ("----", "|", "\t"):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep)]
            parts = [p for p in parts if p != ""]  # drop empties only
            break
    else:
        if "," in raw and "@" in raw.split(",", 1)[0]:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            parts = raw.split()
    if not parts:
        return None
    email_addr = parts[0].strip()
    if "@" not in email_addr:
        return None
    domain = email_addr.rsplit("@", 1)[-1].lower()
    if domain not in ("aol.com", "aim.com", "netscape.net", "verizon.net", "love.com", "gamesail.com", "cs.com"):
        # still allow if user forced aol provider
        pass
    password = ""
    totp = ""
    if len(parts) == 1:
        return None
    if len(parts) == 2:
        # email----secret  -> secret is IMAP password / app password (user may call it TOTP)
        password = parts[1].strip()
    else:
        password = parts[1].strip()
        totp = parts[2].strip()
    if not password:
        return None
    return AolAccount(email=email_addr, password=password, totp_secret=totp)


def load_accounts_from_text(text: str) -> List[AolAccount]:
    out, seen = [], set()
    for raw in (text or "").splitlines():
        acc = parse_account_line(raw)
        if not acc or acc.identity() in seen:
            continue
        seen.add(acc.identity())
        out.append(acc)
    return out


def load_accounts_from_file(path: str) -> List[AolAccount]:
    p = Path(path)
    if not p.is_file():
        return []
    return load_accounts_from_text(p.read_text(encoding="utf-8", errors="ignore"))


# xAI markers (shared logic with outlook_mail)
_XAI_FROM_HINTS = ("x.ai", "xai.com", "mail.x.ai", "grok")
_XAI_TEXT_HINTS = re.compile(
    r"\b(xai|x\.ai|grok|verify(?:\s+your)?\s+email|email\s+verification|"
    r"confirmation\s+code|verification\s+code)\b",
    re.I,
)
_XAI_SUBJECT_CODE = re.compile(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI\b", re.I)
_DASH_CODE = re.compile(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", re.I)


def _decode_mime_header(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _message_text_from_email(msg: email.message.Message) -> str:
    chunks: List[str] = []
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = (part.get_content_type() or "").lower()
                if ctype not in ("text/plain", "text/html"):
                    continue
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(payload.decode(charset, errors="replace"))
                except Exception:
                    continue
        else:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
    except Exception:
        pass
    return "\n".join(chunks)


def is_xai_related(subject: str = "", text: str = "", frm: str = "") -> bool:
    frm_l = (frm or "").lower()
    for hint in _XAI_FROM_HINTS:
        if hint in frm_l:
            return True
    if _XAI_SUBJECT_CODE.search(subject or ""):
        return True
    blob = f"{subject}\n{text}"
    return bool(_XAI_TEXT_HINTS.search(blob))


def extract_code(text: str = "", subject: str = "") -> Optional[str]:
    subject = subject or ""
    text = text or ""
    m = _XAI_SUBJECT_CODE.search(subject)
    if m:
        return m.group(1)
    blob = f"{subject}\n{text}"
    has_xai = bool(_XAI_TEXT_HINTS.search(blob))
    if has_xai:
        m = _DASH_CODE.search(blob)
        if m:
            return m.group(1)
    for pattern in (
        r"verification\s+code[:\s]+(\d{4,8})",
        r"your\s+code[:\s]+(\d{4,8})",
        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",
    ):
        m = re.search(pattern, blob, re.I)
        if m and has_xai:
            return m.group(1)
    return None


class AolImapSession:
    """IMAP SSL session for AOL (imap.aol.com)."""

    HOST = "imap.aol.com"
    PORT = 993
    # common folder names across AOL/Yahoo
    FOLDERS = (
        "INBOX",
        "Junk",
        "Bulk Mail",
        "Spam",
        "Trash",
        "INBOX.Trash",
        "INBOX.Spam",
        "INBOX.Bulk Mail",
    )

    def __init__(self, email_addr: str, password: str, log_callback=None, timeout: int = 30):
        self.email = email_addr
        self.password = password
        self.log_callback = log_callback
        self.timeout = timeout
        self.M: Optional[imaplib.IMAP4_SSL] = None

    def _lg(self, msg: str) -> None:
        _log(self.log_callback, msg)

    def connect_login(self) -> None:
        self._lg(f"[*] AOL IMAP connect {self.HOST}:{self.PORT} email={self.email}")
        ctx = ssl.create_default_context()
        self.M = imaplib.IMAP4_SSL(self.HOST, self.PORT, ssl_context=ctx, timeout=self.timeout)
        self.M.sock.settimeout(self.timeout)
        typ, data = self.M.login(self.email, self.password)
        self._lg(f"[+] AOL IMAP login OK email={self.email} typ={typ} data={data}")

    def logout(self) -> None:
        if not self.M:
            return
        try:
            self.M.close()
        except Exception:
            pass
        try:
            self.M.logout()
        except Exception:
            pass
        self.M = None

    def list_folders(self) -> List[str]:
        assert self.M
        typ, data = self.M.list()
        names: List[str] = []
        if typ != "OK" or not data:
            return names
        for raw in data:
            try:
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
                # last quoted segment is folder name
                m = re.search(r' "([^"]+)"\s*$', line)
                if m:
                    names.append(m.group(1))
                else:
                    parts = line.rsplit(" ", 1)
                    if len(parts) == 2:
                        names.append(parts[1].strip('"'))
            except Exception:
                continue
        return names

    def _select_folder(self, folder: str) -> bool:
        assert self.M
        for cand in (folder, f'"{folder}"'):
            try:
                typ, _ = self.M.select(cand, readonly=True)
                if typ == "OK":
                    return True
            except Exception:
                continue
        return False

    def fetch_recent(self, top_per_folder: int = 30) -> List[dict]:
        """Return recent messages from ALL IMAP folders (LIST), newest first per folder."""
        assert self.M
        available = self.list_folders()
        self._lg(
            f"[*] AOL IMAP LIST folders count={len(available)} all={available}"
        )
        # Prefer INBOX first, then rest alphabetically for stable logs
        ordered: List[str] = []
        seen_f: set[str] = set()
        for preferred in ("INBOX", "Inbox", "inbox"):
            for a in available:
                if a == preferred or a.upper() == "INBOX":
                    if a.lower() not in seen_f:
                        ordered.append(a)
                        seen_f.add(a.lower())
        for a in available:
            k = a.lower()
            if k in seen_f:
                continue
            # skip non-selectable / noselect if flagged in name quirks later
            ordered.append(a)
            seen_f.add(k)
        if not ordered:
            ordered = ["INBOX"]

        out: List[dict] = []
        folder_counts: Dict[str, int] = {}
        folder_errors: Dict[str, str] = {}
        for folder in ordered:
            if not self._select_folder(folder):
                folder_errors[folder] = "select_fail"
                self._lg(f"[!] AOL skip folder select fail: {folder}")
                continue
            try:
                typ, data = self.M.search(None, "ALL")
            except Exception as exc:
                folder_errors[folder] = str(exc)
                self._lg(f"[!] AOL search fail folder={folder}: {exc}")
                continue
            if typ != "OK" or not data or not data[0]:
                folder_counts[folder] = 0
                continue
            ids = data[0].split()
            recent = ids[-int(top_per_folder) :]
            recent = list(reversed(recent))  # newest first
            folder_counts[folder] = len(recent)
            for mid in recent:
                try:
                    typ2, msg_data = self.M.fetch(mid, "(RFC822)")
                    if typ2 != "OK" or not msg_data:
                        continue
                    raw = None
                    for part in msg_data:
                        if isinstance(part, tuple) and len(part) >= 2:
                            raw = part[1]
                            break
                    if not raw:
                        continue
                    msg = email.message_from_bytes(raw)
                    subject = _decode_mime_header(msg.get("Subject") or "")
                    frm = _decode_mime_header(msg.get("From") or "")
                    date_hdr = msg.get("Date") or ""
                    body = _message_text_from_email(msg)
                    recv_ts = 0.0
                    try:
                        recv_ts = parsedate_to_datetime(date_hdr).timestamp()
                    except Exception:
                        recv_ts = 0.0
                    uid = f"{folder}:{mid.decode() if isinstance(mid, bytes) else mid}"
                    out.append(
                        {
                            "id": uid,
                            "folder": folder,
                            "subject": subject,
                            "from": frm,
                            "date": date_hdr,
                            "received_ts": recv_ts,
                            "body": body,
                        }
                    )
                except Exception as exc:
                    self._lg(f"[!] AOL fetch fail folder={folder} mid={mid}: {exc}")
                    continue
            self._lg(
                f"[*] AOL IMAP folder={folder} fetched={folder_counts.get(folder, 0)} "
                f"top={top_per_folder}"
            )
        out.sort(key=lambda m: float(m.get("received_ts") or 0), reverse=True)
        self._lg(
            f"[*] AOL ALL-folders merged counts={folder_counts} total={len(out)} "
            f"scanned_folders={list(folder_counts.keys())} "
            f"errors={folder_errors or {}} 每夹 top≈{top_per_folder}"
        )
        return out


class AolAccountPool:
    def __init__(self, accounts: List[AolAccount], log_callback=None):
        self.accounts = accounts
        self.log_callback = log_callback
        self._idx = 0

    def _lg(self, msg: str) -> None:
        _log(self.log_callback, msg)

    def ensure_login(self, acc: AolAccount) -> AolAccount:
        """Validate IMAP credentials (login + logout)."""
        sess = AolImapSession(acc.email, acc.password, log_callback=self.log_callback)
        try:
            sess.connect_login()
            # light list to confirm Mail.Read equivalent
            folders = sess.list_folders()
            self._lg(
                f"[+] AOL preflight login OK email={acc.email} folders={len(folders)} "
                f"sample={folders[:8]}"
            )
        finally:
            sess.logout()
        return acc

    def acquire(self) -> Tuple[str, str]:
        with _POOL_LOCK:
            if not self.accounts:
                raise Exception("AOL account pool empty; configure aol_accounts or aol_accounts.txt")
            last_err = None
            # while: 登录失败会删除账号，列表长度变化，不能用固定 range(n)
            attempts = 0
            max_attempts = max(1, len(self.accounts) * 2)
            while attempts < max_attempts and self.accounts:
                attempts += 1
                n = len(self.accounts)
                if n <= 0:
                    break
                if self._idx >= n:
                    self._idx = 0
                acc = self.accounts[self._idx % n]
                if acc.status in ("bad", "registered") or acc.cooldown_until > _now() or acc.status == "in_use":
                    self._idx = (self._idx + 1) % n
                    continue
                try:
                    self._lg(f"[*] AOL acquire: {acc.email} | pool={n} | auth=IMAP password/app-password")
                    self.ensure_login(acc)
                    acc.status = "in_use"
                    acc.last_used_at = _now()
                    acc.last_error = ""
                    self._idx = (self._idx + 1) % max(1, len(self.accounts))
                    token_blob = json.dumps(
                        {
                            "email": acc.email,
                            "password": acc.password,
                            "totp_secret": acc.totp_secret,
                            "provider": "aol",
                            "protocol": "imap",
                        },
                        ensure_ascii=False,
                    )
                    self._lg(f"[+] AOL ready: {acc.email} | protocol=IMAP imap.aol.com:993")
                    return acc.email, token_blob
                except Exception as exc:
                    last_err = exc
                    acc.last_error = str(exc)
                    msg = str(exc)
                    auth_fail = (
                        "AUTHENTICATIONFAILED" in msg
                        or "Invalid credentials" in msg
                        or "LOGIN failed" in msg
                        or "authentication failed" in msg.lower()
                    )
                    if auth_fail:
                        self._lg(
                            f"[!] AOL IMAP 登录失败，从账号池删除并换下一个 | email={acc.email} | "
                            f"err={exc}"
                        )
                        self.accounts = [a for a in self.accounts if a.identity() != acc.identity()]
                        try:
                            self.persist_accounts_file()
                        except Exception as pe:
                            self._lg(f"[!] AOL 删除后写回失败: {pe}")
                        # 删除后不推进 idx，下一轮从同位置取“下一个”
                        if self._idx >= len(self.accounts) and self.accounts:
                            self._idx = 0
                    else:
                        acc.status = "idle"
                        acc.cooldown_until = _now() + 120
                        self._lg(
                            f"[!] AOL 临时失败，冷却 120s 后可再试 | email={acc.email} | err={exc}"
                        )
                        self._idx = (self._idx + 1) % max(1, len(self.accounts))
                    self._lg(
                        f"[*] AOL 继续尝试池内下一个账号 | tried={acc.email} | "
                        f"pool={len(self.accounts)}"
                    )
            raise Exception(f"AOL no available account (all login failed): {last_err}")

    def release(self, email: str, ok: bool = True, bad: bool = False) -> None:
        with _POOL_LOCK:
            em = (email or "").lower()
            if bad:
                # 登录失败：直接从池删除（内存+文件）
                before = len(self.accounts)
                self.accounts = [a for a in self.accounts if a.identity() != em]
                if before != len(self.accounts):
                    self._lg(
                        f"[*] AOL release 登录失败删除 email={email} remaining={len(self.accounts)}"
                    )
                    try:
                        self.persist_accounts_file()
                    except Exception as pe:
                        self._lg(f"[!] AOL release 写回失败: {pe}")
                return
            for acc in self.accounts:
                if acc.identity() == em:
                    if acc.status == "registered":
                        pass
                    else:
                        acc.status = "idle"
                        if not ok:
                            acc.cooldown_until = _now() + 60
                    break


    def _format_line(self, acc: AolAccount) -> str:
        if acc.totp_secret:
            return f"{acc.email}----{acc.password}----{acc.totp_secret}"
        return f"{acc.email}----{acc.password}"

    def persist_accounts_file(self) -> None:
        """Rewrite source accounts file from current in-memory pool (no secrets in logs)."""
        path = (self.source_file or "").strip()
        if not path:
            self._lg("[!] AOL persist skip: no source_file")
            return
        p = Path(path)
        lines = [self._format_line(a) for a in self.accounts if (a.email or "").strip()]
        body = "\n".join(lines)
        if body:
            body += "\n"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        self._lg(f"[*] AOL 账号池已写回 file={p} remaining={len(self.accounts)}")

    def remove_account(self, email: str, reason: str = "removed") -> bool:
        """Permanently remove email from memory pool and accounts file."""
        em = (email or "").strip().lower()
        if not em:
            return False
        with _POOL_LOCK:
            before = len(self.accounts)
            self.accounts = [a for a in self.accounts if a.identity() != em]
            removed = before - len(self.accounts)
            if removed:
                self._lg(
                    f"[*] AOL 从账号池删除 email={email} reason={reason} "
                    f"removed={removed} remaining={len(self.accounts)}"
                )
                try:
                    self.persist_accounts_file()
                except Exception as exc:
                    self._lg(f"[!] AOL 写回账号池失败: {exc}")
                return True
            self._lg(f"[*] AOL 删除跳过(池中无此号) email={email} reason={reason}")
            return False

    def resolve_credentials(self, email: str, token_blob: str) -> Tuple[str, str]:
        data = {}
        try:
            data = json.loads(token_blob) if token_blob else {}
        except Exception:
            data = {}
        password = str(data.get("password") or "")
        with _POOL_LOCK:
            for a in self.accounts:
                if a.identity() == (email or data.get("email") or "").lower():
                    if not password:
                        password = a.password
                    return a.email, password
        em = email or data.get("email") or ""
        if not password:
            raise Exception(f"AOL missing password for {em}")
        return em, password


_POOL: Optional[AolAccountPool] = None
_POOL_LOCK = threading.RLock()


def build_pool_from_config(config: dict, log_callback=None) -> AolAccountPool:
    text = str((config or {}).get("aol_accounts") or "").strip()
    accounts = []
    if text:
        accounts.extend(load_accounts_from_text(text))
    path = str((config or {}).get("aol_accounts_file") or "aol_accounts.txt").strip() or "aol_accounts.txt"
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = _root_dir() / file_path
    if file_path.is_file():
        for acc in load_accounts_from_file(str(file_path)):
            if acc.identity() not in {a.identity() for a in accounts}:
                accounts.append(acc)
    _log(log_callback, f"[*] AOL pool loaded accounts={len(accounts)} file={file_path}")
    pool = AolAccountPool(accounts, log_callback=log_callback, source_file=file_path)
    return pool


def get_pool(config: dict, log_callback=None, force_reload: bool = False) -> AolAccountPool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None or force_reload:
            _POOL = build_pool_from_config(config, log_callback=log_callback)
        elif log_callback and _POOL.log_callback is not log_callback:
            _POOL.log_callback = log_callback
        return _POOL


def get_email_and_token(config: dict, proxies=None, log_callback=None) -> Tuple[str, str]:
    # proxies unused for IMAP (direct); kept for API parity
    if proxies:
        _log(log_callback, f"[*] AOL IMAP ignores HTTP proxy for mail fetch (direct IMAP) proxies={proxies}")
    pool = get_pool(config, log_callback=log_callback)
    return pool.acquire()


def preflight_mailbox(config, token_blob: str, email: str, *, log_callback=None, top: int = 15) -> dict:
    pool = get_pool(config, log_callback=log_callback)
    em, password = pool.resolve_credentials(email, token_blob)
    _log(
        log_callback,
        f"[*] AOL preflight start email={em} protocol=IMAP host=imap.aol.com "
        f"scanned_folders=ALL IMAP folders top={int(top)}",
    )
    sess = AolImapSession(em, password, log_callback=log_callback)
    try:
        sess.connect_login()
        msgs = sess.fetch_recent(top_per_folder=int(top))
        for i, msg in enumerate(msgs[:12]):
            xai = is_xai_related(msg.get("subject") or "", msg.get("body") or "", msg.get("from") or "")
            _log(
                log_callback,
                f"[*] AOL preflight mail[{i}] folder={msg.get('folder')} xai={xai} "
                f"date={msg.get('date')} from={msg.get('from')} subject={(msg.get('subject') or '')[:100]} "
                f"id={msg.get('id')}",
            )
        folder_counts: Dict[str, int] = {}
        for m in msgs:
            f = str(m.get("folder") or "INBOX")
            folder_counts[f] = folder_counts.get(f, 0) + 1
        summary = {
            "email": em,
            "auth": "IMAP password/app-password",
            "ok": True,
            "total": len(msgs),
            "folder_counts": folder_counts,
            "scanned_folders": "ALL",
            "top": int(top),
            "full_mailbox": False,
            "protocol": "imap",
        }
        _log(
            log_callback,
            f"[+] AOL preflight OK email={em} total={len(msgs)} counts={folder_counts} all_folders=True",
        )
        return summary
    finally:
        sess.logout()


def get_oai_code(
    config,
    token_blob,
    email,
    timeout=180,
    poll_interval=3.0,
    log_callback=None,
    cancel_callback=None,
    extract_fn=None,
    proxies=None,
    ignore_existing: bool = True,
    since_ts: Optional[float] = None,
) -> str:
    def cancelled():
        if not cancel_callback:
            return False
        try:
            return bool(cancel_callback())
        except Exception:
            return False

    TOP = 40
    pool = get_pool(config, log_callback=log_callback)
    poll_started = _now()
    baseline_ts = float(since_ts) if since_ts else poll_started
    _log(
        log_callback,
        f"[*] AOL poll code | email={email} | protocol=IMAP imap.aol.com "
        f"scanned_folders=ALL IMAP folders top={TOP}"
        f" | ignore_existing={ignore_existing} | since_ts={baseline_ts:.3f}",
    )
    deadline = poll_started + timeout
    seen = set()
    baseline_done = not ignore_existing
    last_err = None
    poll_round = 0
    em, password = pool.resolve_credentials(email, token_blob)

    while _now() < deadline:
        if cancelled():
            raise Exception("cancelled")
        poll_round += 1
        sess = AolImapSession(em, password, log_callback=log_callback)
        try:
            sess.connect_login()
            msgs = sess.fetch_recent(top_per_folder=TOP)
            _log(
                log_callback,
                f"[*] AOL poll round={poll_round} email={em} count={len(msgs)} "
                f"remain={max(0, deadline - _now()):.0f}s",
            )
            dump_n = min(len(msgs), 12 if poll_round <= 2 else 6)
            for i, msg in enumerate(msgs[:dump_n]):
                xai = is_xai_related(msg.get("subject") or "", msg.get("body") or "", msg.get("from") or "")
                _log(
                    log_callback,
                    f"[*] AOL dump r{poll_round}[{i}] folder={msg.get('folder')} xai={xai} "
                    f"date={msg.get('date')} from={msg.get('from')} "
                    f"subject={(msg.get('subject') or '')[:100]} id={msg.get('id')}",
                )

            if not baseline_done:
                skipped = 0
                for msg in msgs:
                    mid = msg.get("id") or ""
                    if not mid:
                        continue
                    if is_xai_related(msg.get("subject") or "", msg.get("body") or "", msg.get("from") or ""):
                        continue
                    seen.add(mid)
                    skipped += 1
                _log(log_callback, f"[*] AOL baseline skip non-xAI existing={skipped}")
                baseline_done = True

            cutoff = baseline_ts - 120
            for msg in msgs:
                mid = msg.get("id") or ""
                if mid and mid in seen:
                    continue
                if mid:
                    seen.add(mid)
                subject = msg.get("subject") or ""
                body = msg.get("body") or ""
                frm = msg.get("from") or ""
                recv_ts = float(msg.get("received_ts") or 0)
                if recv_ts and recv_ts < cutoff:
                    _log(
                        log_callback,
                        f"[*] AOL skip old mail date={msg.get('date')} subject={subject[:60]}",
                    )
                    continue
                if not is_xai_related(subject, body, frm):
                    _log(
                        log_callback,
                        f"[*] AOL skip non-xAI mail subject={subject[:80]} from={frm}",
                    )
                    continue
                _log(
                    log_callback,
                    f"[*] AOL check xAI mail folder={msg.get('folder')} subject={subject[:80]} "
                    f"from={frm} date={msg.get('date')}",
                )
                code = None
                if extract_fn:
                    try:
                        code = extract_fn(body, subject)
                    except TypeError:
                        code = extract_fn(body)
                if not code:
                    code = extract_code(body, subject)
                if code:
                    _log(
                        log_callback,
                        f"[+] AOL code ok email={em} code={code} subject={subject[:60]} "
                        f"from={frm} source=IMAP/{msg.get('folder')}",
                    )
                    pool.release(email, ok=True)
                    return code
                _log(log_callback, f"[*] AOL xAI mail has no parseable code yet subject={subject[:60]}")
        except Exception as exc:
            last_err = exc
            _log(log_callback, f"[!] AOL poll error: {exc}")
        finally:
            sess.logout()
        time.sleep(max(1.0, float(poll_interval)))

    pool.release(email, ok=False)
    raise Exception(
        f"AOL code timeout email={email} last_error={last_err} rounds={poll_round} "
        f"protocol=IMAP top={TOP} all_folders=True"
    )


def is_aol_provider(name: str) -> bool:
    return str(name or "").strip().lower() in {
        "aol",
        "aol_mail",
        "aol.com",
        "aim",
        "verizon_aol",
    }


def remove_from_pool(config: dict, email: str, reason: str = "removed", log_callback=None) -> bool:
    """Public helper: permanently drop mailbox from AOL pool file."""
    pool = get_pool(config, log_callback=log_callback)
    return pool.remove_account(email, reason=reason)
