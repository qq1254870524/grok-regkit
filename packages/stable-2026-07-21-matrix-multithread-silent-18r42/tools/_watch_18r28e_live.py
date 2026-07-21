import json, time, urllib.request
from pathlib import Path
out = Path("matrix_runs/_watch_18r28e_live.txt")

def get(u):
    return urllib.request.urlopen(u, timeout=20).read().decode("utf-8", "replace")

st = json.loads(get("http://127.0.0.1:8092/api/status"))
print("initial", st.get("running"), st.get("last_event"), flush=True)
if not st.get("running"):
    req = urllib.request.Request(
        "http://127.0.0.1:8092/api/pending-sso/recover",
        data=b'{"count":2}',
        headers={"Content-Type": "application/json"},
    )
    print(urllib.request.urlopen(req, timeout=15).read().decode(), flush=True)
    time.sleep(2)

seen = set()
t0 = time.time()
buf = []

def w(s):
    buf.append(s)
    out.write_text("\n".join(buf[-700:]), encoding="utf-8")
    print(s[:300], flush=True)

while time.time() - t0 < 420:
    try:
        st = json.loads(get("http://127.0.0.1:8092/api/status"))
        snap = json.loads(get("http://127.0.0.1:8092/api/logs/snapshot?limit=300"))
        news = []
        keys = [
            "immediate", "preflight route", "closed sign-in", "stop further",
            "aol missing", "outlook pre-login", "auth_error", "re-register",
            "mail_token", "turnstile", "forced_email", "page_err",
            "navigate sign-in", "mailbox preflight", "signup", "hybrid]",
            "sso harvested", "verifyemail", "re-register result", "login failed",
            "after single", "block_refill",
        ]
        for ln in snap.get("lines") or []:
            low = ln.lower()
            if any(k in low for k in keys) and ln not in seen:
                seen.add(ln)
                news.append(ln)
        if news:
            w(
                "=== t+%ss run=%s s=%s f=%s last=%s"
                % (
                    int(time.time() - t0),
                    st.get("running"),
                    st.get("success"),
                    st.get("fail"),
                    st.get("last_event"),
                )
            )
            for ln in news:
                w(ln)
        if (not st.get("running")) and time.time() - t0 > 25:
            w("DONE " + json.dumps(st, ensure_ascii=False)[:700])
            for ln in (snap.get("lines") or [])[-90:]:
                w("F|" + ln)
            break
    except Exception as e:
        w("err " + str(e))
    time.sleep(12)
else:
    w("timeout")
print("watch_done", len(buf), flush=True)
