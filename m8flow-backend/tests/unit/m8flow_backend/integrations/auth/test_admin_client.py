from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.keycloak import client_auth
from m8flow_backend.integrations.auth.keycloak.admin_client import KeycloakAdminClient
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = ""
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"http {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _base_url(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    reset_keycloak_settings()
    yield
    reset_keycloak_settings()


@pytest.fixture
def master_token_endpoint(monkeypatch):
    """Real fetch_master_admin_token() against a fake Keycloak token endpoint
    that mints token-1, token-2, ... (60s lifetime) on each call."""
    minted: list[str] = []

    def fake_post(url, data=None, headers=None, timeout=None):
        minted.append(f"token-{len(minted) + 1}")
        return _FakeResponse(payload={"access_token": minted[-1], "expires_in": 60})

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.client_auth.requests.post", fake_post)
    monkeypatch.setattr(client_auth, "keycloak_admin_password", lambda: "admin-pw")
    monkeypatch.setattr(client_auth, "keycloak_admin_user", lambda: "admin")
    client_auth.reset_master_admin_token_cache()
    yield minted
    client_auth.reset_master_admin_token_cache()


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


def test_master_token_cache_expires_by_wall_clock_even_if_monotonic_clock_paused(
    monkeypatch, master_token_endpoint
):
    # M8F-544: a Docker Desktop VM is paused while the host sleeps, so the
    # monotonic clock stops but Keycloak judges `exp` by wall clock on wake.
    clock = SimpleNamespace(time=lambda: 1_000.0, monotonic=lambda: 5.0)
    monkeypatch.setattr(client_auth, "time", clock)
    assert client_auth.fetch_master_admin_token() == "token-1"

    clock.time = lambda: 1_000.0 + 3_600  # an hour of host sleep; monotonic unchanged
    assert client_auth.fetch_master_admin_token() == "token-2"


def test_rejected_cached_master_token_is_refetched_and_request_retried_once(monkeypatch, master_token_endpoint):
    seen_auth: list[str] = []

    def fake_get(url, headers=None, timeout=None, params=None):
        seen_auth.append(headers["Authorization"])
        return _FakeResponse(status_code=401 if headers["Authorization"] == "Bearer token-1" else 200)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    client_auth.fetch_master_admin_token()  # warm the cache with token-1, which Keycloak now rejects

    response = KeycloakAdminClient().get("m8flow", "users", context="x")

    assert response.status_code == 200
    assert seen_auth == ["Bearer token-1", "Bearer token-2"]
    assert client_auth.fetch_master_admin_token() == "token-2"  # the dead token is gone for every caller


def test_master_token_still_rejected_after_refetch_raises_without_looping(monkeypatch, master_token_endpoint):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _FakeResponse(status_code=401)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    with pytest.raises(ProviderUnavailable):
        KeycloakAdminClient().get("m8flow", "users", context="x")
    assert calls["n"] == 2


def test_rejected_explicit_token_is_not_swapped_for_master_token(monkeypatch):
    def boom():
        raise AssertionError("a caller-supplied token must never be replaced with master admin credentials")

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token", boom)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *a, **k: _FakeResponse(status_code=401),
    )
    with pytest.raises(ProviderUnavailable):
        KeycloakAdminClient(admin_token="tok").get("m8flow", "users", context="x")
