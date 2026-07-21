# stable-2026-07-22-matrix-multithread-silent-18r44e

## 版本定位

多线程**静默稳定**版本 **18r44e**（追加发行，**不覆盖** 18r44d/18r44c）。

构建时间: 2026-07-22T04:30:18

## 本版关键（二次补 SSO 全链路实测 + 修复）

### 实跑结果 `matrix_runs/pending_sso_full_20260722_040327`
| r | class | success | fail | ΔG2A | ΔSub2 | ΔCPA |
|---:|---|---:|---:|---:|---:|---:|
| 1 | success | 5 | 0 | 5 | 5 | 5 |
| 2 | success | 7 | 0 | 7 | 7 | 7 |

- **合计成功 12**，号池与 CPA 全对齐（base g2a 3786→3798 / sub2 3897→3909 / cpa 2529→2541）
- **无 pool_gap**，无真·入池失败，无 CPA 导出失败（authcode mint 成功）
- **停止注册实测 ok=True**：`running_before=true` → `running_after=false`，面板 8092 仍存活，网关 8010/8011/8080 保留

### 代码修复
1. **Sub2 可用性验证**
   - 网络 Read timeout / ConnectionError 自动延长超时并额外重试
   - 文案改为「可用性验证未通过(账号已入池,仅观察)」，避免误判为入池失败
   - `require_verify_success=false` 时 create 成功即入池成功
2. **监控 FAIL 误报**
   - 排除 `fail=0`、`ok=2 fail=0`、`非入池失败` 等假 FAILHIT
3. **继承 18r44d**
   - SOCKS5 LIVE 预检后再开浏览器
   - G2A 双写 8010 primary + 8011 mirror→8020

## 工具
- `tools/_pending_sso_full_monitor_18r44e.py` — 二次补 SSO 多轮 + 入池/CPA + stop 监控
- `tools/_backfill_8010_to_8011_18r44d.py` — 8010→8011 回填

## 校验
- pending_sso 2 轮 success，入池 1:1
- `/api/stop` stop_ok
- py_compile 通过
