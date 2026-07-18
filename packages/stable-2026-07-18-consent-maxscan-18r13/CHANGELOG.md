# stable-2026-07-18-consent-maxscan-18r13

Date: 2026-07-18

## Why
CPA consent 日志显示两阶段扫描：fast 12 → expand max 40。用户要求默认直接扫满 max，不要先快速路径再扩扫。此前 Packages 用户侧感觉未更新成功，本包单独打 18r13 还原点（不覆盖旧包）。

## Change
1. `sso_to_auth_json.py` consent JS discovery：去掉 `fast_limit=12` + expand 两阶段。
2. 默认单阶段 `total_limit=40` / `total_budget=28s`，phase=`max`。
3. 日志：`consent JS max-scan start limit=40 ...` + `max扫 fetched/40`。
4. 仍保留 strong createServerReference/callServer id 早停（≥3 个脚本且 strong_ids>0）。
5. 回归测试改为断言无 `expand scan` / `fast phase`，且能扫到脚本 19 的 action id。

## Files
- sources/sso_to_auth_json.py
- sources/tests/test_18r11_regressions.py

## Verification
- py_compile sso_to_auth_json.py OK
- unittest tests.test_18r11_regressions：6 tests OK
- 源码内无 `expand scan` / `fast_limit`；含 `max-scan start` 与 18r13 changelog

## Do not overwrite
Previous packages kept intact:
- stable-2026-07-18-noreissue-18r9
- stable-2026-07-18-matrix-18r10
- stable-2026-07-18-cpa-consent-18r11
- stable-2026-07-18-protocol-restore-18r12
- stable-2026-07-18-pending-18r3
