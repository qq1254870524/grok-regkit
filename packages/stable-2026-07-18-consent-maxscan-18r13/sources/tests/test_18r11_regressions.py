import importlib.util
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

class Resp:
    def __init__(self, text='', status=200):
        self.text=text; self.status_code=status

class Session:
    def __init__(self, chunks): self.chunks=chunks; self.calls=[]
    def get(self, url, **kwargs):
        self.calls.append(url)
        return Resp(self.chunks.get(url.rsplit('/',1)[-1], ''))

class ConsentDiscoveryTests(unittest.TestCase):
    def test_max_scan_finds_action_without_two_phase_expand(self):
        m=load_file('sso18r13', ROOT/'sso_to_auth_json.py')
        action='a'*40
        html=''.join(f'<script src="/_next/static/chunks/{i:02}.js"></script>' for i in range(25))
        chunks={f'{i:02}.js': ('oauth consent allow but no server action' if i < 19 else '') for i in range(25)}
        chunks['19.js']=f'const x=createServerReference ( "{action}", callServer); oauth consent allow'
        logs=[]
        session=Session(chunks)
        ids=m._discover_action_ids_from_js(session, html, log=logs.append)
        self.assertIn(action, ids)
        # 18r13: single max scan; must not use fast-12 expand path
        self.assertFalse(any('expand scan' in x for x in logs))
        self.assertFalse(any('fast phase' in x for x in logs))
        self.assertTrue(any('max-scan start' in x for x in logs) or any('max扫' in x for x in logs))
        # action lives at script 19; max scan must reach beyond old fast_limit=12
        self.assertGreaterEqual(len(session.calls), 20)

    def test_dead_hardcoded_action_not_extracted(self):
        m=load_file('sso18r11b', ROOT/'sso_to_auth_json.py')
        self.assertNotIn(m.NEXT_ACTION_ID, m._extract_next_action_ids('', include_hardcoded_fallback=False))
        source=(ROOT/'sso_to_auth_json.py').read_text(encoding='utf-8')
        self.assertNotIn('使用 hardcoded fallback', source)
        self.assertNotIn('JS 扫描仍无候选，fallback', source)

class DeviceCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        from cpa_xai import oauth_device
        cls.m=oauth_device

    def test_transient_twice_then_success(self):
        body={'device_code':'d','user_code':'u','verification_uri':'https://accounts.x.ai/oauth2/device','expires_in':100,'interval':5}
        calls=[]; logs=[]
        def post(*a, **k):
            calls.append(1)
            if len(calls) < 3: raise urllib.error.URLError('Remote end closed connection without response')
            return 200, body
        with patch.object(self.m, '_post_form', side_effect=post), patch.object(self.m.time, 'sleep'):
            got=self.m.request_device_code(log=logs.append, network_attempts=4)
        self.assertEqual(got.device_code, 'd')
        self.assertEqual(len(calls), 3)
        self.assertTrue(any('transient=True' in x for x in logs))

    def test_http_400_is_not_network_retried(self):
        calls=[]
        def post(*a, **k): calls.append(1); return 400, {'error':'invalid_client'}
        with patch.object(self.m, '_post_form', side_effect=post):
            with self.assertRaises(self.m.OAuthDeviceError): self.m.request_device_code(network_attempts=4)
        self.assertEqual(len(calls), 1)

    def test_proxy_credentials_not_logged(self):
        logs=[]
        with patch.object(self.m, '_post_form', side_effect=urllib.error.URLError('Remote end closed connection')), patch.object(self.m.time, 'sleep'):
            with self.assertRaises(self.m.OAuthDeviceError):
                self.m.request_device_code(proxy='socks5h://user:secret@127.0.0.1:9999', log=logs.append, network_attempts=2)
        joined='\n'.join(logs)
        self.assertNotIn('user', joined); self.assertNotIn('secret', joined)
        self.assertIn('socks5h://127.0.0.1:9999', joined)

class PendingSourceTests(unittest.TestCase):
    def test_pending_bootstrap_does_not_open_signup(self):
        src=(ROOT/'pending_sso_recovery.py').read_text(encoding='utf-8')
        segment=src[src.index('def recover_one_pending_sso'):src.index('def run_pending_sso_recovery_job')]
        self.assertIn('direct-to-sign-in (no sign-up navigation)', segment)
        self.assertNotIn('start_browser(log_callback=log', segment)
        self.assertNotIn('open_signup_page(log_callback=log', segment)
        self.assertIn('page.get(signin_url)', segment)

if __name__ == '__main__': unittest.main()
