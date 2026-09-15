"""Open-redirect guard for post-login / post-logout destinations."""

from __future__ import annotations

import pytest

from m8flow_backend.errors import ApiError
from m8flow_backend.routes.safe_redirect import (
    allowed_redirect_origins,
    is_safe_redirect_url,
    require_safe_redirect_url,
    safe_redirect_or_fallback,
)


def test_relative_application_paths_are_allowed():
    assert is_safe_redirect_url("/") is True
    assert is_safe_redirect_url("/app") is True
    assert is_safe_redirect_url("/processes?x=1") is True


def test_protocol_relative_and_schemes_are_rejected():
    assert is_safe_redirect_url("//evil.example/") is False
    assert is_safe_redirect_url("javascript:alert(1)") is False
    assert is_safe_redirect_url("data:text/html,hi") is False


def test_backslash_and_crlf_are_rejected():
    assert is_safe_redirect_url("/\\evil.example") is False
    assert is_safe_redirect_url("http://localhost:6853/\r\n") is False


def test_allowlisted_absolute_origins_are_allowed():
    assert is_safe_redirect_url("http://localhost:6853/") is True
    assert is_safe_redirect_url("http://localhost:6841/tasks") is True
    assert is_safe_redirect_url("http://evil.example/") is False


def test_cors_env_extends_allowlist(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_CORS_ALLOW_ORIGINS", "https://app.example.com")
    origins = allowed_redirect_origins()
    assert "https://app.example.com" in origins
    assert is_safe_redirect_url("https://app.example.com/home", allowed_origins=origins) is True


def test_require_safe_redirect_url_raises_on_attacker_host():
    with pytest.raises(ApiError) as excinfo:
        require_safe_redirect_url("https://attacker.example/phish")
    assert excinfo.value.error_code == "invalid_redirect_url"
    assert excinfo.value.status_code == 400


def test_safe_redirect_or_fallback_defaults_to_root():
    assert safe_redirect_or_fallback("https://attacker.example/") == "/"
    assert safe_redirect_or_fallback("http://localhost:6853/ok") == "http://localhost:6853/ok"


def test_login_rejects_unallowlisted_redirect(client):
    response = client.get(
        "/v1.0/login",
        query_string={"redirect_url": "https://attacker.example/steal"},
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_redirect_url"


def test_login_accepts_relative_redirect(client):
    response = client.get("/v1.0/login", query_string={"redirect_url": "/designer"})
    assert response.status_code == 302
