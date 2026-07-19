from pathlib import Path
import re, ast

p = Path("hybrid_register.py")
t = p.read_text(encoding="utf-8")

bad_def = """def handle_create_email_rate_limited(
    email: str,
    password: str,
    *,
    log: Callable[[str], None] | None = None,
    source: str = \"unknown\",
    evidence: str = \"\",
    mail_token: str = \"\",
,
                    mail_token=mail_token,
                ) -> dict:"""

good_def = """def handle_create_email_rate_limited(
    email: str,
    password: str,
    *,
    log: Callable[[str], None] | None = None,
    source: str = \"unknown\",
    evidence: str = \"\",
    mail_token: str = \"\",
) -> dict:"""

if bad_def not in t:
    # try find current def
    m = re.search(r"def handle_create_email_rate_limited\([\s\S]{0,500}?\)\s*->\s*dict:", t)
    print("current def block:\n", m.group(0) if m else "NONE")
else:
    t = t.replace(bad_def, good_def, 1)
    print("fixed def")

# Fix any call that has broken pattern: line ending then lone comma then mail_token=
t = re.sub(
    r"(evidence=[^\n]+)\n([ \t]*),\n([ \t]*)mail_token=mail_token,\n([ \t]*)\)",
    r"\1,\n\3mail_token=mail_token,\n\4)",
    t,
)

# Fix pattern where evidence line already has comma? unlikely
# Also fix: evidence=...\n                ,\n                    mail_token
t = re.sub(
    r"(evidence=[^\n,]+)\r?\n([ \t]+),\r?\n([ \t]+)mail_token=mail_token,\r?\n([ \t]+)\)",
    r"\1,\n\3mail_token=mail_token,\n\4)",
    t,
)

# Ensure every handle_create call (not def) has mail_token=
def fix_calls(src: str) -> str:
    out = []
    i = 0
    while True:
        j = src.find("handle_create_email_rate_limited(", i)
        if j < 0:
            out.append(src[i:])
            break
        # skip if this is the def
        before = src[max(0, j - 20) : j]
        out.append(src[i:j])
        k = j + len("handle_create_email_rate_limited(")
        depth = 1
        while k < len(src) and depth:
            ch = src[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            k += 1
        call = src[j:k]
        if "def " in before:
            out.append(call)
        else:
            # normalize broken commas
            call2 = re.sub(r",\s*,", ",", call)
            call2 = call2.replace("\n,", "\n")
            if "mail_token=" not in call2:
                call2 = call2[:-1].rstrip()
                if not call2.endswith(","):
                    call2 += ","
                call2 += "\n                    mail_token=mail_token,\n                )"
            # remove orphan lone-comma lines inside
            lines = []
            for ln in call2.splitlines():
                if ln.strip() == ",":
                    continue
                lines.append(ln)
            call2 = "\n".join(lines)
            # ensure evidence line ends with comma if mail_token follows
            call2 = re.sub(
                r"(evidence=[^\n]+?)(\n)([ \t]*mail_token=)",
                lambda m: m.group(1) + ("" if m.group(1).rstrip().endswith(",") else ",") + m.group(2) + m.group(3),
                call2,
            )
            out.append(call2)
            print("normalized call")
        i = k
    return "".join(out)

t = fix_calls(t)

# Show defs and calls
print("=== DEF ===")
m = re.search(r"def handle_create_email_rate_limited\([\s\S]{0,400}?\)\s*->\s*dict:", t)
print(m.group(0) if m else "NONE")
print("=== CALLS ===")
i = 0
while True:
    j = t.find("handle_create_email_rate_limited(", i)
    if j < 0:
        break
    before = t[max(0, j - 10) : j]
    k = j + len("handle_create_email_rate_limited(")
    depth = 1
    while k < len(t) and depth:
        if t[k] == "(": depth += 1
        elif t[k] == ")": depth -= 1
        k += 1
    if "def " not in before:
        print(t[j:k])
        print("---")
    i = k

p.write_text(t, encoding="utf-8")
try:
    ast.parse(t)
    print("AST OK")
except SyntaxError as e:
    print("AST FAIL", e)
    lines = t.splitlines()
    ln = e.lineno or 1
    for i in range(ln - 6, ln + 6):
        if 0 < i <= len(lines):
            print(f"{i}: {lines[i-1]}")
