# 18r35 实时进度汇报

更新时间见文件 mtime

## 矩阵参数
- workers=10, warm_ahead=40, rounds/cell=40
- 8 格: hybrid|browser × direct|socks5_list × aol|outlook + pending_sso_recovery

## 已完成格（jsonl）
1. hybrid × direct × aol → success=39 fail=1 pending=0  ✅ 主路径优秀
2. hybrid × direct × outlook → success=5 fail=0 pending=35  ⚠️ Outlook 直连大量 early_no_new_mail/bad_castle/desync → 进 pending_sso（二次补）
3. hybrid × socks5 × aol → success=35 fail=2 pending=3  ✅ 代理下 AOL 可用

## 进行中
4. hybrid × socks5 × outlook（workers=10）

## 待跑
5-8 browser 四格 + pending_sso_recovery

## 临时邮箱冒烟（不注册）
- 14/16 OK；yyds/cloudflare 缺配置

## 服务
8092/8010/8080/8317/8318 保持运行；停止注册不杀网关

## 发版
矩阵 DONE 后由 `_auto_publish_18r35.py` 打新 tag/Package，不覆盖 18r30/18r31
