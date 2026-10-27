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


def test_mcp_server_url_strips_trailing_slash_and_defaults_to_empty(monkeypatch):
    from m8flow_backend.config import mcp_server_url

    monkeypatch.delenv("M8FLOW_MCP_SERVER_INTERNAL_URL", raising=False)
    monkeypatch.delenv("M8FLOW_MCP_SERVER_URL", raising=False)
    assert mcp_server_url() == ""
    monkeypatch.setenv("M8FLOW_MCP_SERVER_URL", " http://localhost:8000/mcp/ ")
    assert mcp_server_url() == "http://localhost:8000/mcp"


def test_mcp_server_internal_url_wins_for_the_backend(monkeypatch):
    from m8flow_backend.config import mcp_server_url

    monkeypatch.setenv("M8FLOW_MCP_SERVER_URL", "http://localhost:8000/mcp")
    monkeypatch.setenv("M8FLOW_MCP_SERVER_INTERNAL_URL", "http://host.docker.internal:8000/mcp/")
    assert mcp_server_url() == "http://host.docker.internal:8000/mcp"


def test_vault_verify_defaults_to_system_trust(monkeypatch):
    from m8flow_backend.config import vault_verify

    for name in ("M8FLOW_VAULT_CACERT", "VAULT_CACERT", "M8FLOW_VAULT_SKIP_VERIFY", "VAULT_SKIP_VERIFY"):
        monkeypatch.delenv(name, raising=False)
    assert vault_verify() is True


def test_vault_skip_verify_still_works_and_warns(monkeypatch, caplog):
    from m8flow_backend.config import vault_verify

    for name in ("M8FLOW_VAULT_CACERT", "VAULT_CACERT", "M8FLOW_VAULT_SKIP_VERIFY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VAULT_SKIP_VERIFY", "true")
    assert vault_verify() is False
    assert "verification is DISABLED" in caplog.text


def test_vault_ca_bundle_wins_over_skip_verify(monkeypatch, tmp_path):
    from m8flow_backend.config import vault_verify

    monkeypatch.setenv("M8FLOW_VAULT_CACERT", str(tmp_path / "ca.pem"))
    monkeypatch.setenv("M8FLOW_VAULT_SKIP_VERIFY", "true")
    assert vault_verify() == str(tmp_path / "ca.pem")
