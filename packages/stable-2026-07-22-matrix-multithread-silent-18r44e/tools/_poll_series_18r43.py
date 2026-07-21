import json, urllib.request, time, pathlib
out = pathlib.Path("matrix_runs/_CODEX_18r43_POLL_SERIES.jsonl")
for i in range(40):
    try:
        st = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/status", timeout=5))
        row = {
            "ts": time.strftime("%H:%M:%S"),
            "ok": st.get("success"),
            "fail": st.get("fail"),
            "pend": st.get("pending_sso"),
            "await": st.get("awaiting_pool"),
            "phase": st.get("phase"),
            "run": st.get("running"),
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(row["ts"], row["ok"], row["fail"], row["pend"], row["await"], flush=True)
    except Exception as e:
        print("err", e, flush=True)
    time.sleep(30)
print("DONE", flush=True)
