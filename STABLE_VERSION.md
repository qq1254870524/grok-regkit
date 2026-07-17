# STABLE_VERSION — known-good restore point

## Tag

- **Tag / Release**: `stable-2026-07-18`
- **Marked at**: 2026-07-18
- **Purpose**: 当前较完美可还原快照。后续改坏可回此版本对照或硬还原。

## grok-regkit

| 项 | 值 |
|----|----|
| Repo | https://github.com/qq1254870524/grok-regkit |
| Commit | `6f75dbd` |
| Release | https://github.com/qq1254870524/grok-regkit/releases/tag/stable-2026-07-18 |
| Local | `C:\Users\zhang\grok-regkit` |

### 本快照关键能力

- hybrid 协议优先 SignUp，关闭 UI fallback
- CreateEmail 不狂发，验证码过多邮箱实时出池
- next-action 仅 SSO 成功时固化
- CPA mint consent 不再默认死哈希 `401b73e...`；无 live 候选直接扫 JS；404 拉黑
- Sub2API 号池状态 / pending SSO 落盘 / CPA 导入配套

### 还原命令

```bash
git fetch mygithub --tags
git checkout stable-2026-07-18
# 或硬回到该提交（会丢未提交改动，慎用）
# git reset --hard stable-2026-07-18
```

## 配套仓库（同一标记）

| 项目 | Repo | Commit | Release |
|------|------|--------|---------|
| sub2api | https://github.com/qq1254870524/sub2api | `957b075` | https://github.com/qq1254870524/sub2api/releases/tag/stable-2026-07-18 |
| grok-regkit-services | https://github.com/qq1254870524/grok-regkit-services | `a6e5189` | https://github.com/qq1254870524/grok-regkit-services/releases/tag/stable-2026-07-18 |
| mumu-clipboard-isolation | https://github.com/qq1254870524/mumu-clipboard-isolation | `0edfacf` | https://github.com/qq1254870524/mumu-clipboard-isolation/releases/tag/stable-2026-07-18 |

## 运行面（本机，不含密钥）

| 服务 | 端口 | 说明 |
|------|------|------|
| grok-regkit Web UI | 8092 | 注册控制台 |
| Sub2API | 8080 | 号池 |
| grok2api / 相关 | 8010 | API |
| CLIProxy / CPA 相关 | 8317 / 8318 | 代理与网关 |

停止注册只停 8092 任务；不要停 8010/8080/8317/8318。

## 本地注意

- `C:\Users\zhang\grok-regkit-services1` 是本机服务运行/管理目录，**不是** git 工作树；公开 companion 在 GitHub `grok-regkit-services`（已脱敏）。
- 本机 `sub2api` 源码目录若缺失，以 GitHub `qq1254870524/sub2api@stable-2026-07-18` 为准克隆。
- 账号、SSO、cookie、代理密码、admin 密码、OAuth JSON **不进公开仓库**。

## 如何再打新的完美点

1. 确认主链路实跑正常
2. 三个关联仓都 push 到 GitHub
3. 新建 tag，例如 `stable-YYYY-MM-DD`
4. 更新本文件表格中的 commit / release 链接
