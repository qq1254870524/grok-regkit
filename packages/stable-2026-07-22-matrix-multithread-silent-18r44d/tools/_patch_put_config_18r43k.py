from pathlib import Path
p = Path(r"C:\Users\zhang\grok-regkit\web\server.py")
txt = p.read_text(encoding="utf-8")
start = txt.find("@app.put(\"/api/config\")")
if start < 0:
    raise SystemExit("start not found")
# find engine.load_config() after start
idx = txt.find("engine.load_config()", start)
if idx < 0:
    raise SystemExit("load_config not found")
# replace from function start through the blocked log block end
marker_end = 'f"(preserve active job cell settings)"\n            )\n'
end = txt.find(marker_end, start)
if end < 0:
    # try CRLF
    marker_end = 'f"(preserve active job cell settings)"\r\n            )\r\n'
    end = txt.find(marker_end, start)
if end < 0:
    raise SystemExit("end marker not found")
end = end + len(marker_end)
old = txt[start:end]
print("OLD_HEAD=")
print(old[:400])
print("---")
new = '''@app.put("/api/config")
async def api_put_config(body: ConfigBody, x_access_key: Optional[str] = Header(None)):
    _require_auth(x_access_key)
    # 18r43k: while job running, snapshot locked cell keys BEFORE load_config so a dirty
    # config.json (UI/other tools writing duckmail/airport/etc) cannot thrash the active matrix cell.
    JOB_LOCKED_CONFIG_KEYS = (
        "register_mode", "proxy_mode", "email_provider", "workers", "thread_count",
        "register_count", "proxy", "proxy_list",
    )
    with _job_lock:
        job_running = bool(_job_state.get("running"))
    locked_snapshot = {}
    if job_running:
        for k in JOB_LOCKED_CONFIG_KEYS:
            try:
                if k in engine.config:
                    locked_snapshot[k] = engine.config.get(k)
            except Exception:
                pass
    engine.load_config()
    if job_running and locked_snapshot:
        restored = []
        for k, v in locked_snapshot.items():
            if engine.config.get(k) != v:
                engine.config[k] = v
                restored.append(k)
        if restored:
            _append_log(
                f"[!] put_config restored locked keys after load_config while job running: {','.join(restored)}"
            )
    updates = body.model_dump(exclude_unset=True)
    # 18r33c: while job running, ignore critical keys so UI/other tools cannot thrash matrix cell
    if job_running:
        blocked = [k for k in list(updates.keys()) if k in JOB_LOCKED_CONFIG_KEYS]
        for k in blocked:
            updates.pop(k, None)
        if blocked:
            _append_log(
                f"[!] put_config ignored locked keys while job running: {','.join(blocked)} "
                f"(preserve active job cell settings)"
            )
'''
# keep original newline style for remainder continuity - write LF
txt2 = txt[:start] + new + txt[end:]
p.write_text(txt2, encoding="utf-8")
print("patched_ok")
# verify
assert "locked_snapshot" in p.read_text(encoding="utf-8")
print("verify_ok")
