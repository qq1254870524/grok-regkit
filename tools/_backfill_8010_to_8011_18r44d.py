# -*- coding: utf-8 -*-
"""Backfill 8010 primary pool -> 8011 bridge (8020 v3). No secrets printed."""
import json, sys, time, traceback, urllib.request, urllib.parse, urllib.error
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(r"C:\Users\zhang\grok-regkit")
LOG = ROOT / "matrix_runs" / "_backfill_8010_to_8011_18r44d.log"
BATCH = 40
SLEEP = 0.05


def log(m):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + str(m)
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def http_json(method, url, body=None, timeout=60):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(raw) if raw.strip() else {}
        except Exception:
            j = {"raw_len": len(raw)}
        return e.code, j


def extract_tokens(payload):
    out = []
    if not isinstance(payload, dict):
        return out
    arr = payload.get("tokens")
    if arr is None and isinstance(payload.get("data"), dict):
        arr = payload["data"].get("tokens")
    if arr is None and isinstance(payload.get("data"), list):
        arr = payload["data"]
    if not isinstance(arr, list):
        return out
    for t in arr:
        if isinstance(t, str):
            v = t.strip()
            if v:
                out.append(v)
            continue
        if not isinstance(t, dict):
            continue
        v = str(t.get("token") or t.get("sso") or t.get("value") or "").strip()
        if v and v != "***":
            out.append(v)
    return out


def total_of(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("total") is not None:
        try:
            return int(payload["total"])
        except Exception:
            pass
    toks = extract_tokens(payload)
    if toks:
        return len(toks)
    if isinstance(payload.get("tokens"), list):
        return len(payload["tokens"])
    return None


def main():
    if LOG.exists():
        LOG.write_text("", encoding="utf-8")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    src_base = str(cfg.get("grok2api_remote_base") or "http://127.0.0.1:8010").rstrip("/")
    src_key = str(cfg.get("grok2api_remote_app_key") or "").strip()
    dst_base = str(cfg.get("grok2api_mirror_remote_base") or "http://127.0.0.1:8011").rstrip("/")
    dst_key = str(
        cfg.get("grok2api_mirror_remote_app_key")
        or cfg.get("grok2api_extra_remote_app_key")
        or ""
    ).strip()
    pool = str(cfg.get("grok2api_remote_pool") or cfg.get("grok2api_pool_name") or "basic").strip()
    if pool.lower() in ("ssobasic", "sso_basic"):
        pool = "basic"
    log("SRC=%s DST=%s pool=%s src_key_len=%s dst_key_len=%s" % (
        src_base, dst_base, pool, len(src_key), len(dst_key)))
    if len(src_key) < 8 or len(dst_key) < 8:
        log("BAD_KEYS"); return 2

    src_url = src_base + "/admin/api/tokens?" + urllib.parse.urlencode({"app_key": src_key})
    dst_list_url = dst_base + "/admin/api/tokens?" + urllib.parse.urlencode({"app_key": dst_key})
    dst_add_url = dst_base + "/admin/api/tokens/add?" + urllib.parse.urlencode({"app_key": dst_key})

    sc, src = http_json("GET", src_url, timeout=90)
    log("SRC status=%s total=%s keys=%s" % (sc, total_of(src), list(src.keys()) if isinstance(src, dict) else type(src)))
    tokens = extract_tokens(src)
    # unique preserve order
    seen = set()
    uniq = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    log("SRC real_tokens=%s unique=%s" % (len(tokens), len(uniq)))
    if not uniq:
        log("NO_SOURCE_TOKENS"); return 3

    dc0, dst0 = http_json("GET", dst_list_url, timeout=60)
    before = total_of(dst0)
    log("DST BEFORE status=%s total=%s" % (dc0, before))

    # Bridge may mask tokens as ***; always full POST and rely on server dedupe.
    added_batches = 0
    ok_batches = 0
    fail_batches = 0
    for i in range(0, len(uniq), BATCH):
        chunk = uniq[i : i + BATCH]
        body = {"tokens": chunk, "pool": pool}
        code, resp = http_json("POST", dst_add_url, body=body, timeout=90)
        added_batches += 1
        # parse counts without logging tokens
        info = {}
        if isinstance(resp, dict):
            for k in ("ok", "added", "success", "failed", "skipped", "duplicated", "duplicate", "total", "message", "error", "msg"):
                if k in resp:
                    info[k] = resp[k]
            if isinstance(resp.get("data"), dict):
                for k in ("added", "success", "failed", "skipped", "duplicated", "total"):
                    if k in resp["data"]:
                        info["data_" + k] = resp["data"][k]
        if code in (200, 201) and (resp.get("ok") is not False):
            ok_batches += 1
        else:
            fail_batches += 1
        if added_batches <= 3 or added_batches % 10 == 0 or fail_batches:
            log("batch#%s i=%s n=%s http=%s info=%s" % (added_batches, i, len(chunk), code, info))
        time.sleep(SLEEP)

    dc1, dst1 = http_json("GET", dst_list_url, timeout=60)
    after = total_of(dst1)
    log("DST AFTER status=%s total=%s delta=%s" % (
        dc1, after, (after - before) if (after is not None and before is not None) else None))
    log("BATCHES total=%s ok=%s fail=%s SRC_unique=%s" % (added_batches, ok_batches, fail_batches, len(uniq)))
    gap = None
    if after is not None:
        gap = len(uniq) - after
    log("GAP_vs_SRC_unique=%s" % gap)
    log("DONE")
    return 0 if fail_batches == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log("FATAL " + traceback.format_exc())
        raise
