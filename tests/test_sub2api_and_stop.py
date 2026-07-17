from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
                yield line.encode("utf-8") if isinstance(line, str) else line

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


def build_client(responses, logs):
    return Sub2APIClient(
        base_url="http://127.0.0.1:8080",
        admin_email="admin@example.com",
        admin_password="private-password",
        timeout_sec=60,
        session=FakeSession(responses),
        log_callback=logs.append,
    )


def _success_test_lines():
    return [
        'data: {"type":"test_start","model":"grok-4.5"}',
        'data: {"type":"content","text":"OK"}',
        'data: {"type":"test_complete","success":true}',
    ]


def test_group_ids_normalize():
    assert _parse_group_ids("3, 4,3,bad") == [3, 4]
    assert _parse_group_ids([]) == [3]


def test_login_and_import_created_without_secret_logs():
    logs = []
    session_responses = [
        FakeResponse(200, {"code": 0, "data": {"access_token": "header.payload.signature"}}),
        FakeResponse(
            200,
            {
                "code": 0,
                "data": {
                    "created": [{"account": {"id": 12, "name": "mail@example.com"}}],
                    "failed": [],
                },
            },
        ),
        FakeResponse(200, {}, lines=_success_test_lines()),
    ]
    client = build_client(session_responses, logs)
    result = client.import_grok_sso(
        "very-secret-sso",
        email="mail@example.com",
        group_ids="3,4",
        verify_retry_delay_sec=0,
    )
    assert result["ok"] is True
    assert result["usable"] is True
    assert result["account_id"] == 12
    request_json = client.session.calls[1][2]["json"]
    assert request_json["group_ids"] == [3, 4]
    assert request_json["sso_tokens"] == ["very-secret-sso"]
    assert "sso_token" not in request_json
    assert client.session.calls[2][2]["stream"] is True
    joined = "\n".join(logs)
    assert "private-password" not in joined
    assert "very-secret-sso" not in joined
    assert "header.payload.signature" not in joined
    assert any("入池可用" in line for line in logs)


def test_401_relogin_once_then_success():
    logs = []
    client = build_client(
        [
            FakeResponse(200, {"code": 0, "data": {"access_token": "first.token.value"}}),
            FakeResponse(401, {"code": 401, "message": "expired"}),
            FakeResponse(200, {"code": 0, "data": {"access_token": "second.token.value"}}),
            FakeResponse(200, {"code": 0, "data": {"created": [{"account": {"id": 13}}], "failed": []}}),
            FakeResponse(200, {}, lines=_success_test_lines()),
        ],
        logs,
    )
    assert (
        client.import_grok_sso("sso", email="a@example.com", verify_retry_delay_sec=0)["account_id"]
        == 13
    )
    assert len(client.session.calls) == 5
    assert any("重新登录" in line for line in logs)


def test_failed_conversion_raises():
    client = build_client(
        [
            FakeResponse(200, {"code": 0, "data": {"access_token": "token.value.test"}}),
            FakeResponse(200, {"code": 0, "data": {"created": [], "failed": [{"error": "invalid sso"}]}}),
        ],
        [],
    )
    with pytest.raises(RuntimeError, match="invalid sso"):
        client.import_grok_sso("bad-sso", email="bad@example.com")


def test_unwrapped_import_response_is_supported():
    client = build_client(
        [
            FakeResponse(200, {"code": 0, "data": {"access_token": "token.value.test"}}),
            FakeResponse(200, {"created": [{"id": 21, "name": "unwrapped"}], "failed": []}),
        ],
        [],
    )
    result = client.import_grok_sso(
        "sso",
        email="unwrapped@example.com",
        verify_after_import=False,
    )
    assert result["ok"] is True
    assert result["usable"] is None
    assert result["account_id"] == 21


def test_created_but_unusable_is_not_reported_as_success():
    logs = []
    client = build_client(
        [
            FakeResponse(200, {"code": 0, "data": {"access_token": "token.value.test"}}),
            FakeResponse(200, {"code": 0, "data": {"created": [{"account": {"id": 22}}], "failed": []}}),
            FakeResponse(
                200,
                {},
                lines=[
                    'data: {"type":"test_start","model":"grok-4.5"}',
                    'data: {"type":"error","error":"upstream unavailable"}',
                ],
            ),
        ],
        logs,
    )
    import sub2api_client as s2
    old_sleep = s2.time.sleep
    s2.time.sleep = lambda sec: None
    try:
        result = client.import_grok_sso(
            "sso",
            email="bad@example.com",
            verify_attempts=1,
            verify_retry_delay_sec=0,
        )
    finally:
        s2.time.sleep = old_sleep
    assert result["ok"] is True
    assert result["usable"] is False
    joined = "\n".join(logs)
    assert "账号已创建但可用性验证失败" in joined


def test_stop_race_does_not_call_new_tab(monkeypatch):
    import grok_register_ttk as engine

    class FakePage:
        def get(self, _url):
            raise RuntimeError("page disconnected")

    class FakeBrowser:
        def __init__(self):
            self.new_tab_called = False

        def get_tab(self, _index):
            return FakePage()

        def new_tab(self, _url):
            self.new_tab_called = True
            raise AssertionError("new_tab must not run after stop")

    fake = FakeBrowser()
    monkeypatch.setattr(engine, "browser", fake)
    monkeypatch.setattr(engine, "browser_started_with_proxy", False)
    states = iter([False, False, True])

    def cancelled():
        return next(states, True)

    with pytest.raises(engine.RegistrationCancelled):
        engine.open_signup_page(cancel_callback=cancelled)
    assert fake.new_tab_called is False


def test_ui_sub2api_defaults_and_password_masking_schema():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    server = (ROOT / "web" / "server.py").read_text(encoding="utf-8")
    assert 'id="sub2api_auto_add" type="checkbox" checked' in html
    assert 'id="sub2api_verify_after_add" type="checkbox" checked' in html
    assert 'id="sub2api_verify_timeout_sec" type="number" min="15" value="105"' in html
    assert 'id="sub2api_verify_attempts" type="number" min="1" max="5" value="2"' in html
    assert "c.sub2api_auto_add !== false" in html
    assert "'sub2api_admin_password'" in html
    assert '"sub2api_admin_password"' in server
    assert "sub2api_group_ids: Optional[List[int]]" in server
    assert "sub2api_verify_after_add: Optional[bool]" in server
    assert "sub2api_verify_timeout_sec: Optional[int]" in server
