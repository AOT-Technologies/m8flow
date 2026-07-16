"""Tests for ROPC token acquisition, focused on graceful organization-scope fallback."""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest

from src.auth.token_service import TokenService


def _jwt(claims: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "http://kc/token"),
                response=httpx.Response(self.status_code, json=self._body),
            )


class _FakeSyncClient:
    """Records the scopes of each POST and replies per a scripted sequence."""

    def __init__(self, responses: list[_FakeResponse], scopes_seen: list[str], **_kwargs):
        self._responses = responses
        self._scopes_seen = scopes_seen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, data=None, headers=None):
        self._scopes_seen.append(data["scope"])
        return self._responses.pop(0)


@pytest.fixture
def ropc_settings(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "keycloak_username", "svc")
    monkeypatch.setattr(settings, "keycloak_password", "pw")
    monkeypatch.setattr(settings, "client_secret", None)
    return settings


def _install_fake_client(monkeypatch, responses: list[_FakeResponse], scopes_seen: list[str]) -> None:
    """Patch httpx.Client so every ``with httpx.Client()`` shares one response queue.

    Each token attempt opens its own client context, so the scripted responses must
    persist across instantiations (a fresh list per call would replay from the start).
    """
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeSyncClient(responses, scopes_seen, **kw))


def test_get_token_sync_retries_without_org_scope_on_invalid_scope(monkeypatch, ropc_settings):
    scopes_seen: list[str] = []
    ok = _FakeResponse(200, {"access_token": _jwt({"exp": int(time.time()) + 300}), "expires_in": 300})
    rejected = _FakeResponse(400, {"error": "invalid_scope"})
    _install_fake_client(monkeypatch, [rejected, ok], scopes_seen)

    svc = TokenService()
    token = svc.get_token_sync()

    assert token  # succeeded on the retry
    assert len(scopes_seen) == 2
    assert "organization:*" in scopes_seen[0]  # first attempt requested org scope
    assert "organization:*" not in scopes_seen[1]  # retry dropped it


def test_get_token_sync_no_retry_when_first_succeeds(monkeypatch, ropc_settings):
    scopes_seen: list[str] = []
    ok = _FakeResponse(200, {"access_token": _jwt({"exp": int(time.time()) + 300}), "expires_in": 300})
    _install_fake_client(monkeypatch, [ok], scopes_seen)

    svc = TokenService()
    assert svc.get_token_sync()
    assert len(scopes_seen) == 1  # exactly one attempt
    assert "organization:*" in scopes_seen[0]


def test_get_token_sync_non_scope_400_raises(monkeypatch, ropc_settings):
    scopes_seen: list[str] = []
    bad = _FakeResponse(400, {"error": "invalid_grant"})
    _install_fake_client(monkeypatch, [bad], scopes_seen)

    svc = TokenService()
    with pytest.raises(RuntimeError):
        svc.get_token_sync()
    assert len(scopes_seen) == 1  # no retry for a non-scope failure
