# -*- coding: utf-8 -*-
"""Smoke-test public/temp email providers without full registration."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path(r"C:\Users\zhang\grok-regkit")
sys.path.insert(0, str(ROOT))
import temp_email_public_providers as pub

# also try named providers used by UI
EXTRA = ["duckmail", "yyds", "cloudflare"]  # may need keys

results = []
for key in sorted(pub.PUBLIC_PROVIDERS.keys()):
    t0 = time.time()
    try:
        r = pub.smoke_test_provider(key, proxies=None)
        r["elapsed"] = round(time.time() - t0, 2)
        results.append(r)
        print(f"OK/INFO {key}: {r}", flush=True)
    except Exception as e:
        results.append({"provider": key, "ok": False, "error": str(e), "elapsed": round(time.time()-t0,2)})
        print(f"FAIL {key}: {e}", flush=True)

# duckmail/yyds/cloudflare create via get_email if possible
try:
    import grok_register_ttk as g
    for prov in EXTRA:
        t0 = time.time()
        try:
            g.config["email_provider"] = prov
            email, token = g.get_email_and_token(log_callback=lambda m: print(m, flush=True))
            results.append({"provider": prov, "ok": True, "email": email, "token_len": len(str(token or "")), "elapsed": round(time.time()-t0,2)})
            print(f"OK {prov}: {email}", flush=True)
        except Exception as e:
            results.append({"provider": prov, "ok": False, "error": str(e), "elapsed": round(time.time()-t0,2)})
            print(f"FAIL {prov}: {e}", flush=True)
except Exception as e:
    results.append({"provider": "import_grok", "ok": False, "error": str(e)})

out = ROOT / "matrix_runs" / f"temp_email_smoke_{time.strftime('%Y%m%d_%H%M%S')}.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("WROTE", out)
ok = sum(1 for r in results if r.get("ok"))
print(f"SUMMARY ok={ok}/{len(results)}")
