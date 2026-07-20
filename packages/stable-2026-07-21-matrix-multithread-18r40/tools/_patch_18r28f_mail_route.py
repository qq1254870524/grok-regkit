from pathlib import Path

p = Path("grok_register_ttk.py")
text = p.read_text(encoding="utf-8")

helper = r'''
def resolve_mailbox_provider(email: str = "", configured: str = "", token_blob: str = "") -> str:
    """Route mailbox ops by email domain / token shape first, then global config.

    18r28f: when UI email_provider=aol, Outlook forced re-register still must use Graph.
    Previously get_oai_code only looked at get_email_provider() and called aol_mail,
    raising "AOL missing password for user@outlook.com" after CreateEmail already sent.
    """
    em = str(email or "").strip().lower()
    conf = str(configured or "").strip().lower()
    tb = str(token_blob or "").strip()
    aol_suffixes = (
        "@aol.com", "@aim.com", "@verizon.net", "@love.com",
        "@ygm.com", "@games.com", "@wow.com",
    )
    outlook_suffixes = (
        "@outlook.com", "@hotmail.com", "@live.com", "@msn.com",
        "@office365.com", "@outlook.jp", "@outlook.fr", "@hotmail.co.uk",
    )
    if em.endswith(outlook_suffixes):
        return "outlook"
    if em.endswith(aol_suffixes):
        return "aol"
    if tb.startswith("{") and (
        "access_token" in tb or "refresh_token" in tb or '"client_id"' in tb
    ):
        return "outlook"
    if "----" in tb:
        left, right = tb.split("----", 1)
        left_l = left.strip().lower()
        right_s = right.strip()
        if "@" in left_l and (
            left_l.endswith(outlook_suffixes)
            or "refresh" in right_s.lower()
            or right_s.startswith("M.")
            or len(right_s) > 80
        ):
            return "outlook"
    if not conf:
        try:
            conf = str(get_email_provider() or "").strip().lower()
        except Exception:
            conf = ""
    try:
        if outlook_mail is not None and outlook_mail.is_outlook_provider(conf):
            return "outlook"
    except Exception:
        pass
    try:
        if aol_mail is not None and aol_mail.is_aol_provider(conf):
            return "aol"
    except Exception:
        pass
    if conf in {"outlook", "microsoft", "hotmail", "graph", "ms", "outlook_mail"}:
        return "outlook"
    if conf in {"aol", "aol_mail", "aol.com", "aim", "verizon_aol"}:
        return "aol"
    return conf or "outlook"


'''

if "def resolve_mailbox_provider(" not in text:
    text = text.replace(
        "\ndef get_oai_code(\n",
        "\n" + helper + "def get_oai_code(\n",
        1,
    )
    print("inserted resolve_mailbox_provider")
else:
    print("resolve_mailbox_provider already exists")

old = """def get_oai_code(
    dev_token,
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
    resend_callback=None,
    since_ts=None,
    ignore_existing=True,
    **kwargs,
):
    provider = get_email_provider()
    if public_email is not None and public_email.is_public_provider(provider):
"""

new = """def get_oai_code(
    dev_token,
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
    resend_callback=None,
    since_ts=None,
    ignore_existing=True,
    **kwargs,
):
    # 18r28f: domain/token-first routing (do not trust global provider alone)
    configured = ""
    try:
        configured = str(get_email_provider() or "")
    except Exception:
        configured = ""
    provider = resolve_mailbox_provider(email, configured=configured, token_blob=dev_token)
    if log_callback:
        try:
            log_callback(
                f"[mail] get_oai_code route email={email} provider={provider} "
                f"configured={configured or '-'} token_len={len(str(dev_token or ''))}"
            )
        except Exception:
            pass
    if public_email is not None and public_email.is_public_provider(provider):
"""

if old not in text:
    raise SystemExit("get_oai_code block not found exactly")
text = text.replace(old, new, 1)

if "18r28f:" not in text[:3000]:
    text = text.replace(
        "Changelog:\n",
        "Changelog:\n"
        "- 2026-07-19r28f: get_oai_code domain/token-first routing (Outlook not misrouted to AOL when UI source=AOL);\n"
        "  fix CreateEmail-sent then \"AOL missing password for @outlook.com\" code fetch fail.\n",
        1,
    )

p.write_text(text, encoding="utf-8")
print("grok_register_ttk.py OK")

# unit check without full app
ns = {}
exec(helper, {"get_email_provider": lambda: "aol", "outlook_mail": type("O", (), {"is_outlook_provider": staticmethod(lambda n: n in {"outlook","microsoft","hotmail","ms_outlook"})})(), "aol_mail": type("A", (), {"is_aol_provider": staticmethod(lambda n: n in {"aol","aol_mail"})})()}, ns)
fn = ns["resolve_mailbox_provider"]
assert fn("a@outlook.com", "aol") == "outlook", fn("a@outlook.com", "aol")
assert fn("a@aol.com", "outlook") == "aol"
assert fn("x@custom.com", "aol", '{"refresh_token":"x"}') == "outlook"
assert fn("x@custom.com", "aol") == "aol"
print("unit OK", fn("kubinzudavids09a@outlook.com", "aol"))
