# stable-2026-07-18-protocol-restore-18r12

协议路径还原点（18R12）。CreateEmail 恢复 observe-only，修复 18r10 起协议/SSO 变差的问题。

## 内容
- `CHANGELOG.md` — 变更说明
- `RESTORE.txt` — 还原步骤
- `sources/hybrid_register.py`
- `sources/browser/token_harvester.py`
- `sources/pending_sso_recovery.py`
- `sources/protocol/grpc_client.py`
- `sources/web/server.py`

## 下载
- 仓库路径：`packages/stable-2026-07-18-protocol-restore-18r12/`
- Tag：`stable-2026-07-18-protocol-restore-18r12`
- Release 资源：同名 zip

## 不要覆盖
保留 18r9 / 18r10 / 18r11 / pending-18r3 等旧还原点。
