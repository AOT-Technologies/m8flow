"""Host config accessors that are not boot/startup wiring."""

from __future__ import annotations

from m8flow_backend.config import app_frontend_base_url


def test_app_frontend_base_url_defaults_to_designer_not_keycloak(monkeypatch):
    monkeypatch.delenv("M8FLOW_FRONTEND_BASE_URL", raising=False)
    monkeypatch.delenv("M8FLOW_APP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("KEYCLOAK_HOSTNAME", "http://localhost:6842")

    assert app_frontend_base_url() == "http://localhost:6853"


def test_app_frontend_base_url_honors_explicit_frontend_override(monkeypatch):
    monkeypatch.setenv("M8FLOW_FRONTEND_BASE_URL", "https://flow.example.com/")
    monkeypatch.setenv("M8FLOW_APP_PUBLIC_BASE_URL", "https://ignored.example.com")
    monkeypatch.setenv("KEYCLOAK_HOSTNAME", "http://localhost:6842")

    assert app_frontend_base_url() == "https://flow.example.com"


def test_app_frontend_base_url_uses_app_public_origin_when_frontend_unset(monkeypatch):
    monkeypatch.delenv("M8FLOW_FRONTEND_BASE_URL", raising=False)
    monkeypatch.setenv("M8FLOW_APP_PUBLIC_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("KEYCLOAK_HOSTNAME", "http://localhost:6842")

    assert app_frontend_base_url() == "https://app.example.com"
