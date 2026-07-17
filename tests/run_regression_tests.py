from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAL = Path(r'C:\Users\zhang\grok-regkit')
sys.path.insert(0, str(ROOT))
sys.path.append(str(FORMAL))

from sub2api_client import Sub2APIClient, _parse_group_ids


class FakeResponse:
    def __init__(self, status_code, payload, lines=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self._lines = list(lines or [])
        self.closed = False

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            if decode_unicode:
                yield line
            else:
                yield line.encode('utf-8') if isinstance(line, str) else line

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError('unexpected request')
        return self.responses.pop(0)


def build_client(responses, logs):
    return Sub2APIClient(
        base_url='http://127.0.0.1:8080',
        admin_email='admin@example.com',
        admin_password='private-password',
        timeout_sec=60,
        session=FakeSession(responses),
        log_callback=logs.append,
    )


class RegressionTests(unittest.TestCase):
    def test_group_ids_normalize(self):
        self.assertEqual(_parse_group_ids('3, 4,3,bad'), [3, 4])
        self.assertEqual(_parse_group_ids([]), [3])

    def test_login_and_import_created_without_secret_logs(self):
        logs = []
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'header.payload.signature'}}),
            FakeResponse(200, {'code': 0, 'data': {'created': [{'account': {'id': 12, 'name': 'mail@example.com'}}], 'failed': []}}),
            FakeResponse(200, {}, lines=[
                'data: {"type":"test_start","model":"grok-4.5"}',
                'data: {"type":"content","text":"OK"}',
                'data: {"type":"test_complete","success":true}',
            ]),
        ], logs)
        result = client.import_grok_sso(
            'very-secret-sso', email='mail@example.com', group_ids='3,4',
            verify_retry_delay_sec=0,
        )
        self.assertTrue(result['ok'])
        self.assertTrue(result['usable'])
        self.assertEqual(result['account_id'], 12)
        request_json = client.session.calls[1][2]['json']
        self.assertEqual(request_json['group_ids'], [3, 4])
        self.assertEqual(request_json['sso_tokens'], ['very-secret-sso'])
        self.assertNotIn('sso_token', request_json)
        self.assertTrue(client.session.calls[2][2]['stream'])
        joined = '\n'.join(logs)
        self.assertNotIn('private-password', joined)
        self.assertNotIn('very-secret-sso', joined)
        self.assertNotIn('header.payload.signature', joined)

    def test_401_relogin_once_then_success(self):
        logs = []
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'first.token.value'}}),
            FakeResponse(401, {'code': 401, 'message': 'expired'}),
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'second.token.value'}}),
            FakeResponse(200, {'code': 0, 'data': {'created': [{'account': {'id': 13}}], 'failed': []}}),
            FakeResponse(200, {}, lines=[
                'data: {"type":"test_start","model":"grok-4.5"}',
                'data: {"type":"test_complete","success":true}',
            ]),
        ], logs)
        self.assertEqual(client.import_grok_sso(
            'sso', email='a@example.com', verify_retry_delay_sec=0
        )['account_id'], 13)
        self.assertEqual(len(client.session.calls), 5)
        self.assertTrue(any('重新登录' in line for line in logs))

    def test_failed_conversion_raises(self):
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'token.value.test'}}),
            FakeResponse(200, {'code': 0, 'data': {'created': [], 'failed': [{'error': 'invalid sso'}]}}),
        ], [])
        with self.assertRaisesRegex(RuntimeError, 'invalid sso'):
            client.import_grok_sso('bad-sso', email='bad@example.com')

    def test_unwrapped_import_response_is_supported(self):
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'token.value.test'}}),
            FakeResponse(200, {'created': [{'id': 21, 'name': 'unwrapped'}], 'failed': []}),
        ], [])
        result = client.import_grok_sso(
            'sso', email='unwrapped@example.com', verify_after_import=False
        )
        self.assertTrue(result['ok'])
        self.assertIsNone(result['usable'])
        self.assertEqual(result['account_id'], 21)

    def test_created_but_unusable_is_not_reported_as_success(self):
        logs = []
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'token.value.test'}}),
            FakeResponse(200, {'code': 0, 'data': {'created': [{'account': {'id': 22}}], 'failed': []}}),
            FakeResponse(200, {}, lines=[
                'data: {"type":"test_start","model":"grok-4.5"}',
                'data: {"type":"error","error":"upstream unavailable"}',
            ]),
        ], logs)
        with self.assertRaisesRegex(RuntimeError, '已创建 account_id=22.*可用性验证失败'):
            client.import_grok_sso(
                'sso', email='bad@example.com', verify_attempts=1,
                verify_retry_delay_sec=0,
            )
        self.assertFalse(any('入池可用' in line for line in logs))

    def test_stop_race_does_not_call_new_tab(self):
        import grok_register_ttk as engine

        class FakePage:
            def get(self, _url):
                raise RuntimeError('page disconnected')

        class FakeBrowser:
            def __init__(self):
                self.new_tab_called = False
            def get_tab(self, _index):
                return FakePage()
            def new_tab(self, _url):
                self.new_tab_called = True
                raise AssertionError('new_tab must not run after stop')

        old_browser = engine.browser
        old_proxy = engine.browser_started_with_proxy
        fake = FakeBrowser()
        engine.browser = fake
        engine.browser_started_with_proxy = False
        states = iter([False, False, True])
        try:
            with self.assertRaises(engine.RegistrationCancelled):
                engine.open_signup_page(cancel_callback=lambda: next(states, True))
            self.assertFalse(fake.new_tab_called)
        finally:
            engine.browser = old_browser
            engine.browser_started_with_proxy = old_proxy

    def test_web_stop_only_stops_registration_controller(self):
        import asyncio
        import web.server as server

        class FakeController:
            def __init__(self):
                self.calls = []
            def stop(self, force_cleanup=False):
                self.calls.append(force_cleanup)

        original_controller = server._controller
        original_running = server._job_state.get("running")
        fake = FakeController()
        try:
            server._controller = fake
            server._job_state["running"] = True
            result = asyncio.run(server.api_stop(x_access_key=None))
            self.assertTrue(result["ok"])
            self.assertEqual(fake.calls, [True])
            stop_source = (ROOT / "web" / "server.py").read_text(encoding="utf-8")
            stop_block = stop_source.split('@app.post("/api/stop")', 1)[1].split('@app.', 1)[0]
            for service_name in ("grok2api", "sub2api", "cliproxyapi", "cpa_gateway", "service_manager"):
                self.assertNotIn(service_name, stop_block.lower())
        finally:
            server._controller = original_controller
            server._job_state["running"] = original_running

    def test_aol_pool_accepts_source_file(self):
        import aol_mail
        pool = aol_mail.AolAccountPool([], source_file='aol_accounts.txt')
        self.assertEqual(pool.source_file, 'aol_accounts.txt')

    def test_ui_sub2api_defaults_and_password_masking_schema(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        server = (ROOT / 'web' / 'server.py').read_text(encoding='utf-8')
        self.assertIn('id="sub2api_auto_add" type="checkbox" checked', html)
        self.assertIn('id="sub2api_verify_after_add" type="checkbox" checked', html)
        self.assertIn('id="sub2api_verify_timeout_sec" type="number" min="15" value="105"', html)
        self.assertIn('id="sub2api_verify_attempts" type="number" min="1" max="5" value="2"', html)
        self.assertIn('id="stopBtn" class="btn btn-danger" type="button">停止注册</button>', html)
        self.assertIn('不会停止 grok2api、Sub2API、CLIProxyAPI 或 CPA Gateway', html)
        self.assertIn('c.sub2api_auto_add !== false', html)
        self.assertIn("'sub2api_admin_password'", html)
        self.assertIn('"sub2api_admin_password"', server)
        self.assertIn('sub2api_group_ids: Optional[List[int]]', server)
        self.assertIn('sub2api_verify_after_add: Optional[bool]', server)
        self.assertIn('sub2api_verify_timeout_sec: Optional[int]', server)

    def test_masked_sub2api_password_is_preserved_on_config_save(self):
        import asyncio
        import web.server as server

        original_config = dict(server.engine.config)
        original_load = server.engine.load_config
        original_save = server.engine.save_config
        original_access = server.ACCESS_PASSWORD
        try:
            server.ACCESS_PASSWORD = ""
            server.engine.config.clear()
            server.engine.config.update({
                "sub2api_admin_password": "original-private-password",
                "sub2api_auto_add": True,
                "proxy_mode": "direct",
            })
            server.engine.load_config = lambda: server.engine.config
            server.engine.save_config = lambda: None
            body = server.ConfigBody(sub2api_admin_password="or*******************rd")
            result = asyncio.run(server.api_put_config(body, x_access_key=None))
            self.assertTrue(result["ok"])
            self.assertEqual(server.engine.config["sub2api_admin_password"], "original-private-password")
            self.assertNotEqual(result["config"]["sub2api_admin_password"], "original-private-password")
            self.assertIn("*", result["config"]["sub2api_admin_password"])
        finally:
            server.engine.load_config = original_load
            server.engine.save_config = original_save
            server.ACCESS_PASSWORD = original_access
            server.engine.config.clear()
            server.engine.config.update(original_config)


if __name__ == '__main__':
    unittest.main(verbosity=2)
