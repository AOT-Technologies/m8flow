"""Session cookie Secure flag: QA/prod require it; local HTTP may omit it."""

from __future__ import annotations

from m8flow_backend.routes.session_cookies import (
    session_cookie_kwargs,
    session_cookies_are_secure,
    set_token_cookies,
)


def test_session_cookies_secure_by_default_outside_local_http(monkeypatch):
    monkeypatch.delenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "production")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "production")
    assert session_cookies_are_secure() is True


def test_session_cookies_insecure_for_local_development(monkeypatch):
    monkeypatch.delenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    assert session_cookies_are_secure() is False


def test_session_cookies_insecure_for_unit_testing(monkeypatch):
    monkeypatch.delenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")
    assert session_cookies_are_secure() is False


def test_session_cookie_secure_override_true_on_local(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", "true")
    assert session_cookies_are_secure() is True


def test_session_cookie_secure_override_false_on_production(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "production")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "production")
    monkeypatch.setenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", "false")
    assert session_cookies_are_secure() is False


def test_session_cookie_kwargs_include_secure_and_samesite(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", "true")
    kwargs = session_cookie_kwargs(max_age=60, httponly=True)
    assert kwargs == {
        "max_age": 60,
        "path": "/",
        "samesite": "Lax",
        "secure": True,
        "httponly": True,
    }


def test_set_token_cookies_emit_secure_when_enabled(app, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_SESSION_COOKIE_SECURE", "true")
    with app.test_request_context("/"):
        response = app.response_class()
        set_token_cookies(
            response,
            {
                "access_token": "a",
                "id_token": "i",
                "refresh_token": "r",
                "expires_in": 1800,
                "refresh_expires_in": 86400,
            },
            identifier="m8flow",
        )
        headers = response.headers.getlist("Set-Cookie")
        assert any(h.startswith("access_token=a") and "Secure" in h for h in headers)
        assert any(h.startswith("id_token=i") and "Secure" in h for h in headers)
        assert any(h.startswith("refresh_token=r") and "Secure" in h and "HttpOnly" in h for h in headers)
        assert any(h.startswith("authentication_identifier=m8flow") and "Secure" in h for h in headers)
