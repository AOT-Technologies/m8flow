from __future__ import annotations

from typing import Any

import pytest
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.integrations.auth.keycloak import provisioning
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings


BASE = "http://keycloak.internal"


class _FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        status_code: int = 200,
        *,
        reason: str = "OK",
        url: str = "",
        text: str = "",
    ):
        self._payload = payload
        self.status_code = status_code
        self.reason = reason
        self.url = url
        self.text = text
        self.ok = status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"http {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _provision_http(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", BASE)
    monkeypatch.setattr(provisioning, "fetch_master_admin_token", lambda: "admin-token")
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
        lambda: "admin-token",
    )
    monkeypatch.setattr(
        provisioning,
        "load_realm_template",
        lambda: {"realm": "template", "loginTheme": "m8flow"},
    )
    monkeypatch.setattr(
        provisioning,
        "_fill_realm_template",
        lambda template, realm_id, display_name, template_name: {
            "realm": realm_id,
            "displayName": display_name or realm_id,
            "loginTheme": "m8flow",
        },
    )
    monkeypatch.setattr(
        provisioning,
        "_minimal_realm_creation_payload",
        lambda full: {
            "realm": full["realm"],
            "displayName": full["displayName"],
            "enabled": True,
            "loginTheme": full.get("loginTheme"),
        },
    )
    monkeypatch.setattr(
        provisioning,
        "_partial_import_payload",
        lambda full: {"ifResourceExists": "SKIP", "clients": [], "roles": {}, "users": []},
    )
    monkeypatch.setattr(provisioning, "ensure_backend_redirect_uri_in_keycloak_client", lambda realm_id: None)
    reset_keycloak_settings()
    yield
    reset_keycloak_settings()


def test_create_tenant_realm_posts_minimal_realm_partial_import_and_login_theme(monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(("POST", url, json))
        return _FakeResponse({}, status_code=201, url=url)

    def fake_put(url, json=None, headers=None, timeout=None):
        calls.append(("PUT", url, json))
        return _FakeResponse({}, status_code=204, url=url)

    def fake_get(url, headers=None, timeout=None, params=None):
        calls.append(("GET", url, None))
        return _FakeResponse({"id": "kc-uuid-1", "realm": "acme", "displayName": "Acme"}, url=url)

    monkeypatch.setattr(provisioning.requests, "post", fake_post)
    monkeypatch.setattr(provisioning.requests, "put", fake_put)
    monkeypatch.setattr(provisioning.requests, "get", fake_get)

    tenant = KeycloakAuthProvider().provisioning.create_tenant_realm(
        TenantRef(alias="acme"),
        display_name="Acme",
    )
    assert tenant == Tenant(
        ref=TenantRef(id="kc-uuid-1", alias="acme", name="Acme"),
        display_name="Acme",
    )
    methods_urls = [(method, url) for method, url, _payload in calls]
    assert methods_urls[0] == ("POST", f"{BASE}/admin/realms")
    assert methods_urls[1] == ("POST", f"{BASE}/admin/realms/acme/partialImport")
    assert ("PUT", f"{BASE}/admin/realms/acme") in methods_urls
    theme_put = next(payload for method, url, payload in calls if method == "PUT" and url.endswith("/acme"))
    assert theme_put == {"loginTheme": "m8flow"}
    assert ("GET", f"{BASE}/admin/realms/acme") in methods_urls


def test_create_tenant_realm_wraps_http_errors(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(provisioning.requests, "post", fake_post)
    with pytest.raises(ProviderUnavailable, match="acme"):
        KeycloakAuthProvider().provisioning.create_tenant_realm(TenantRef(alias="acme"))


def test_delete_tenant_realm_treats_404_as_success(monkeypatch):
    def fake_delete(url, headers=None, timeout=None):
        assert url == f"{BASE}/admin/realms/acme"
        return _FakeResponse(status_code=404)

    monkeypatch.setattr(provisioning.requests, "delete", fake_delete)
    KeycloakAuthProvider().provisioning.delete_tenant_realm(TenantRef(alias="acme"))


def test_realm_exists_treats_403_as_present(monkeypatch):
    def fake_get(url, timeout=None, headers=None, params=None):
        assert url == f"{BASE}/realms/acme/.well-known/openid-configuration"
        return _FakeResponse(status_code=403)

    monkeypatch.setattr(provisioning.requests, "get", fake_get)
    assert provisioning.realm_exists("acme") is True


def test_ensure_client_redirect_uri_adds_explicit_uri(monkeypatch):
    stored: dict[str, Any] = {
        "id": "client-1",
        "redirectUris": ["https://app.example/api/*"],
    }

    def fake_get(url, headers=None, timeout=None, params=None):
        if "clientId=" in url or url.endswith("/clients"):
            return _FakeResponse([{"id": "client-1", "clientId": "m8flow-backend"}])
        return _FakeResponse(stored)

    def fake_put(url, json=None, headers=None, timeout=None):
        stored.update(dict(json))
        return _FakeResponse(status_code=204)

    monkeypatch.setattr(provisioning, "ensure_backend_redirect_uri_in_keycloak_client", lambda realm_id: None)
    monkeypatch.setattr(provisioning.requests, "get", fake_get)
    monkeypatch.setattr(provisioning.requests, "put", fake_put)

    KeycloakAuthProvider().provisioning.ensure_client_redirect_uri(
        TenantRef(alias="acme"),
        redirect_uri="https://app.example/callback",
    )
    assert "https://app.example/callback" in stored["redirectUris"]
