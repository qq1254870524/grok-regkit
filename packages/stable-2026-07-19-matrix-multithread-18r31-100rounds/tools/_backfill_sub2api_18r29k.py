import json, sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\zhang\grok-regkit")
from sub2api_client import backfill_missing_sub2api_from_cpa_and_sso, log_pool_counts

cfg = json.loads(Path(r"C:\Users\zhang\grok-regkit\config.json").read_text(encoding="utf-8"))
cfg = dict(cfg)
cfg["sub2api_backfill_gap_sec"] = 1.5
cfg["sub2api_backfill_fail_gap_sec"] = 4
cfg["sub2api_verify_after_add"] = False

out = Path(r"C:\Users\zhang\grok-regkit\matrix_runs\_sub2api_backfill_18r29k.log")

def log(m: str) -> None:
    line = str(m)
    print(line, flush=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

out.write_text("", encoding="utf-8")
log("=== before ===")
log_pool_counts(config=cfg, log_callback=log)
summary = backfill_missing_sub2api_from_cpa_and_sso(
    config=cfg, log_callback=log, limit=0, prefer_cpa=True
)
log("SUMMARY " + json.dumps({k: v for k, v in summary.items() if k != "errors"}, ensure_ascii=False))
if summary.get("errors"):
    log("ERR " + json.dumps(summary["errors"][:15], ensure_ascii=False))
log("=== after ===")
log_pool_counts(config=cfg, log_callback=log)
log("DONE")
