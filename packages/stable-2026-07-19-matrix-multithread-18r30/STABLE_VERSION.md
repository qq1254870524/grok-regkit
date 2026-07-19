# STABLE_VERSION

## Current target
- **stable-2026-07-19-matrix-multithread-18r30** (multi-thread; workers UI)
- Previous single-thread baseline (do not overwrite): **stable-2026-07-19-matrix-singlethread-18r29**

## Notes
- workers=1 serial path preserved
- mail top=5 all folders
- email preflight limited sample
- open_signup PageDisconnected retry (18r30b)



# Stable Version

## Current (multi-thread)

- **Tag / Package**: `stable-2026-07-19-matrix-multithread-18r30`
- **Workers**: Web `regWorkers` / API `workers` (1=serial = 18r29 behavior)
- **Baseline single-thread (do not overwrite)**: `stable-2026-07-19-matrix-singlethread-18r29`

## Notes

- Primary path: register → immediate SSO → NSFW → G2A → CPA → Sub2API
- pending_sso is recovery only
- Stop registration does not stop companion services (8010/8080/8317/8318)
