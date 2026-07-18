# TEST RESULTS — 18r11

## 定向回归

1. live consent Action 位于第 12 个 chunk 之后：通过。
2. 失效 hardcoded Action 不再自动提取/提交：通过。
3. device-code 前两次 RemoteDisconnected、第三次 200：通过。
4. device-code HTTP 400 不做网络重试：通过。
5. SOCKS5 认证信息不进入日志：通过。
6. pending SSO 直接 sign-in、不调用 open_signup_page：通过。

## 全量测试

```text
python -B -m unittest discover -s tests -p test_*.py -v
13 tests passed

python -B -m pytest -q
24 passed in 6.36s
```

## 服务隔离

```text
8010 preserved
8080 preserved
8092 restarted once to load 18r11
8317 preserved
8318 preserved
```
