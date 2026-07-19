# 18r30 live
time: 2026-07-19T14:13:44
matrix_alive: True
api: ok=0/10 fail=8 pend=0 phase=finished jobs=10/9
event: [w2] [*] turnstile sitekey=0x4AAAAAAAhr9JGVDZbr...

## cells jsonl
```
{"cell": "hybrid__direct__aol", "mode": "hybrid", "proxy": "direct", "email": "aol", "workers": 2, "count": 10, "success": 10, "fail": 0, "pending_sso": 0, "skipped": 0, "error": "", "last_event": "[*] 混合任务结束。成功 10 | 失败 0 | pending_sso 0 | 跳过(池空) 0 | workers=2", "finished_at": 1784436294.031831, "ts": "2026-07-19T12:44:57"}
{"cell": "hybrid__direct__outlook", "mode": "hybrid", "proxy": "direct", "email": "outlook", "workers": 2, "count": 10, "success": 7, "fail": 0, "pending_sso": 3, "skipped": 0, "error": "", "last_event": "[*] 混合任务结束。成功 7 | 失败 0 | pending_sso 3 | 跳过(池空) 0 | workers=2", "finished_at": 1784437115.494249, "ts": "2026-07-19T12:58:38"}
{"cell": "hybrid__socks5_list__aol", "mode": "hybrid", "proxy": "socks5_list", "email": "aol", "workers": 2, "count": 10, "success": 7, "fail": 0, "pending_sso": 3, "skipped": 0, "error": "", "last_event": "[*] 混合任务结束。成功 7 | 失败 0 | pending_sso 3 | 跳过(池空) 0 | workers=2", "finished_at": 1784438014.9793055, "ts": "2026-07-19T13:13:36"}
{"cell": "hybrid__socks5_list__outlook", "mode": "hybrid", "proxy": "socks5_list", "email": "outlook", "workers": 2, "count": 10, "success": 2, "fail": 0, "pending_sso": 8, "skipped": 0, "error": "", "last_event": "[*] 混合任务结束。成功 2 | 失败 0 | pending_sso 8 | 跳过(池空) 0 | workers=2", "finished_at": 1784439130.6479354, "ts": "2026-07-19T13:32:10"}
{"cell": "browser__direct__aol", "mode": "browser", "proxy": "direct", "email": "aol", "workers": 2, "count": 10, "success": 5, "fail": 5, "pending_sso": 0, "skipped": 0, "error": "", "last_event": "[*] 多线程任务结束。成功 5 | 失败 5 | pending_sso 0", "finished_at": 1784439662.9374952, "ts": "2026-07-19T13:41:07"}
{"cell": "browser__direct__outlook", "mode": "browser", "proxy": "direct", "email": "outlook", "workers": 2, "count": 10, "success": 3, "fail": 5, "pending_sso": 0, "skipped": 0, "error": "", "last_event": "[*] 多线程任务结束。成功 3 | 失败 5 | pending_sso 0", "finished_at": 1784440401.3352616, "ts": "2026-07-19T13:53:22"}
{"cell": "browser__socks5_list__aol", "mode": "browser", "proxy": "socks5_list", "email": "aol", "workers": 2, "count": 10, "success": 3, "fail": 6, "pending_sso": 1, "skipped": 0, "error": "", "last_event": "[*] 多线程任务结束。成功 3 | 失败 6 | pending_sso 1", "finished_at": 1784441090.3249738, "ts": "2026-07-19T14:04:55"}
{"cell": "browser__socks5_list__outlook", "mode": "browser", "proxy": "socks5_list", "email": "outlook", "workers": 2, "count": 10, "success": 0, "fail": 10, "pending_sso": 0, "skipped": 0, "error": "", "last_event": "[*] 多线程任务结束。成功 0 | 失败 10 | pending_sso 0", "finished_at": 1784441450.2104943, "ts": "2026-07-19T14:10:51"}

```

## full out tail
```
18r30 matrix start cells=8 rounds=10 workers=2
report=C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r30_20260719_123545.jsonl

===== CELL hybrid__direct__aol workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'hybrid__direct__aol', 'mode': 'hybrid', 'proxy': 'direct', 'email': 'aol', 'workers': 2, 'count': 10, 'success': 10, 'fail': 0, 'pending_sso': 0, 'skipped': 0, 'error': '', 'last_event': '[*] �������������ɹ� 10 | ʧ�� 0 | pending_sso 0 | ����(�ؿ�) 0 | workers=2', 'finished_at': 1784436294.031831, 'ts': '2026-07-19T12:44:57'}

===== CELL hybrid__direct__outlook workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'hybrid__direct__outlook', 'mode': 'hybrid', 'proxy': 'direct', 'email': 'outlook', 'workers': 2, 'count': 10, 'success': 7, 'fail': 0, 'pending_sso': 3, 'skipped': 0, 'error': '', 'last_event': '[*] �������������ɹ� 7 | ʧ�� 0 | pending_sso 3 | ����(�ؿ�) 0 | workers=2', 'finished_at': 1784437115.494249, 'ts': '2026-07-19T12:58:38'}

===== CELL hybrid__socks5_list__aol workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'hybrid__socks5_list__aol', 'mode': 'hybrid', 'proxy': 'socks5_list', 'email': 'aol', 'workers': 2, 'count': 10, 'success': 7, 'fail': 0, 'pending_sso': 3, 'skipped': 0, 'error': '', 'last_event': '[*] �������������ɹ� 7 | ʧ�� 0 | pending_sso 3 | ����(�ؿ�) 0 | workers=2', 'finished_at': 1784438014.9793055, 'ts': '2026-07-19T13:13:36'}

===== CELL hybrid__socks5_list__outlook workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'hybrid__socks5_list__outlook', 'mode': 'hybrid', 'proxy': 'socks5_list', 'email': 'outlook', 'workers': 2, 'count': 10, 'success': 2, 'fail': 0, 'pending_sso': 8, 'skipped': 0, 'error': '', 'last_event': '[*] �������������ɹ� 2 | ʧ�� 0 | pending_sso 8 | ����(�ؿ�) 0 | workers=2', 'finished_at': 1784439130.6479354, 'ts': '2026-07-19T13:32:10'}

===== CELL browser__direct__aol workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'browser__direct__aol', 'mode': 'browser', 'proxy': 'direct', 'email': 'aol', 'workers': 2, 'count': 10, 'success': 5, 'fail': 5, 'pending_sso': 0, 'skipped': 0, 'error': '', 'last_event': '[*] ���߳�����������ɹ� 5 | ʧ�� 5 | pending_sso 0', 'finished_at': 1784439662.9374952, 'ts': '2026-07-19T13:41:07'}

===== CELL browser__direct__outlook workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'browser__direct__outlook', 'mode': 'browser', 'proxy': 'direct', 'email': 'outlook', 'workers': 2, 'count': 10, 'success': 3, 'fail': 5, 'pending_sso': 0, 'skipped': 0, 'error': '', 'last_event': '[*] ���߳�����������ɹ� 3 | ʧ�� 5 | pending_sso 0', 'finished_at': 1784440401.3352616, 'ts': '2026-07-19T13:53:22'}

===== CELL browser__socks5_list__aol workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'browser__socks5_list__aol', 'mode': 'browser', 'proxy': 'socks5_list', 'email': 'aol', 'workers': 2, 'count': 10, 'success': 3, 'fail': 6, 'pending_sso': 1, 'skipped': 0, 'error': '', 'last_event': '[*] ���߳�����������ɹ� 3 | ʧ�� 6 | pending_sso 1', 'finished_at': 1784441090.3249738, 'ts': '2026-07-19T14:04:55'}

===== CELL browser__socks5_list__outlook workers=2 count=10 =====
start {'ok': True, 'started': True, 'count': 10, 'workers': 2}
result {'cell': 'browser__socks5_list__outlook', 'mode': 'browser', 'proxy': 'socks5_list', 'email': 'outlook', 'workers': 2, 'count': 10, 'success': 0, 'fail': 10, 'pending_sso': 0, 'skipped': 0, 'error': '', 'last_event': '[*] ���߳�����������ɹ� 0 | ʧ�� 10 | pending_sso 0', 'finished_at': 1784441450.2104943, 'ts': '2026-07-19T14:10:51'}
pending start {'ok': True, 'started': True, 'count': 10, 'workers': 2, 'job_kind': 'pending_sso_recovery'}

```
