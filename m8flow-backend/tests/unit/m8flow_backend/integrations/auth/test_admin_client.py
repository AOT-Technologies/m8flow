from __future__ import annotations

import pytest
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.keycloak.admin_client import KeycloakAdminClient
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"http {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return {}


@pytest.fixture(autouse=True)
def _base_url(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    reset_keycloak_settings()
    yield
    reset_keycloak_settings()


def test_url_is_admin_realms_prefixed_and_segment_quoted(monkeypatch):
    seen: dict[str, str] = {}

    def fake_get(url, headers=None, timeout=None, params=None):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        return _FakeResponse()

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    KeycloakAdminClient(admin_token="tok").get("m8flow", "users", "id/with slash", context="x")
    assert seen["url"] == "http://keycloak.internal/admin/realms/m8flow/users/id%2Fwith%20slash"
    assert seen["auth"] == "Bearer tok"


def test_explicit_token_is_reused_without_fetching_master(monkeypatch):
    def boom():
        raise AssertionError("master token should not be fetched when one is supplied")

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token", boom)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *a, **k: _FakeResponse(),
    )
    KeycloakAdminClient(admin_token="tok").get("m8flow", "users", context="x")


def test_master_token_fetched_once_and_memoized(monkeypatch):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return "master"

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token", fetch)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *a, **k: _FakeResponse(),
    )
    client = KeycloakAdminClient()
    client.get("m8flow", "users", context="x")
    client.get("m8flow", "groups", context="x")
    assert calls["n"] == 1


def test_tolerated_status_is_returned_not_raised(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.delete",
        lambda *a, **k: _FakeResponse(status_code=404),
    )
    response = KeycloakAdminClient(admin_token="tok").delete("m8flow", "users", "u1", tolerate=(404,), context="x")
    assert response.status_code == 404


def test_untolerated_http_error_maps_to_provider_unavailable(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *a, **k: _FakeResponse(status_code=500),
    )
    with pytest.raises(ProviderUnavailable, match="Could not do the thing"):
        KeycloakAdminClient(admin_token="tok").get("m8flow", "users", context="do the thing")


def test_transport_error_maps_to_provider_unavailable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", boom)
    with pytest.raises(ProviderUnavailable, match="Could not reach it"):
        KeycloakAdminClient(admin_token="tok").get("m8flow", "users", context="reach it")
