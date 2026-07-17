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
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


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
        ], logs)
        result = client.import_grok_sso('very-secret-sso', email='mail@example.com', group_ids='3,4')
        self.assertTrue(result['ok'])
        self.assertEqual(result['account_id'], 12)
        self.assertEqual(client.session.calls[1][2]['json']['group_ids'], [3, 4])
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
        ], logs)
        self.assertEqual(client.import_grok_sso('sso', email='a@example.com')['account_id'], 13)
        self.assertEqual(len(client.session.calls), 4)
        self.assertTrue(any('重新登录' in line for line in logs))

    def test_failed_conversion_raises(self):
        client = build_client([
            FakeResponse(200, {'code': 0, 'data': {'access_token': 'token.value.test'}}),
            FakeResponse(200, {'code': 0, 'data': {'created': [], 'failed': [{'error': 'invalid sso'}]}}),
        ], [])
        with self.assertRaisesRegex(RuntimeError, 'invalid sso'):
            client.import_grok_sso('bad-sso', email='bad@example.com')

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

    def test_aol_pool_accepts_source_file(self):
        import aol_mail
        pool = aol_mail.AolAccountPool([], source_file='aol_accounts.txt')
        self.assertEqual(pool.source_file, 'aol_accounts.txt')

    def test_ui_sub2api_defaults_and_password_masking_schema(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        server = (ROOT / 'web' / 'server.py').read_text(encoding='utf-8')
        self.assertIn('id="sub2api_auto_add" type="checkbox" checked', html)
        self.assertIn('c.sub2api_auto_add !== false', html)
        self.assertIn("'sub2api_admin_password'", html)
        self.assertIn('"sub2api_admin_password"', server)
        self.assertIn('sub2api_group_ids: Optional[List[int]]', server)

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
