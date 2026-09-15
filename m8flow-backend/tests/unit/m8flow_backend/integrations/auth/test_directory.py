from __future__ import annotations

from typing import Any

import pytest
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, UserNotFound
from m8flow_backend.integrations.auth.base.models import IssuerRef, User
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.routes.keycloak_controller import create_user_in_realm
from m8flow_backend.integrations.auth.keycloak import directory
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings


USERS_URL = "http://keycloak.internal/admin/realms/m8flow/users"


class _FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"http {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _directory_http(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
        lambda: "admin-token",
    )
    reset_keycloak_settings()
    yield
    reset_keycloak_settings()


def _ada() -> dict[str, Any]:
    return {
        "id": "u1",
        "username": "ada",
        "email": "ada@example.com",
        "firstName": "Ada",
        "lastName": "Lovelace",
    }


def test_get_user_returns_neutral_user(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == USERS_URL
        assert params["username"] == "ada"
        assert params["exact"] == "true"
        assert headers["Authorization"] == "Bearer admin-token"
        return _FakeResponse([_ada()])

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    user = KeycloakAuthProvider().get_user(username="ada", issuer=IssuerRef(value="m8flow"))
    assert user == User(
        subject="u1",
        username="ada",
        email="ada@example.com",
        display_name="Ada Lovelace",
    )


def test_get_user_raises_user_not_found(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *args, **kwargs: _FakeResponse([]),
    )
    with pytest.raises(UserNotFound):
        KeycloakAuthProvider().get_user(username="missing", issuer=IssuerRef(value="m8flow"))


def test_search_users_returns_neutral_users(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == USERS_URL
        assert params["search"] == "ada"
        assert params["max"] == 50
        return _FakeResponse([_ada(), {"id": "u2", "username": "ada-admin"}])

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    users = KeycloakAuthProvider().search_users(query="ada", issuer=IssuerRef(value="m8flow"))
    assert [user.subject for user in users] == ["u1", "u2"]
    assert users[0].username == "ada"


def test_create_user_posts_then_returns_neutral_user(monkeypatch):
    calls: list[str] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append("POST")
        assert url == USERS_URL
        assert json["username"] == "ada"
        assert json["credentials"][0]["value"] == "secret"
        return _FakeResponse({}, status_code=201, headers={"Location": f"{USERS_URL}/u1"})

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append("GET")
        assert url == f"{USERS_URL}/u1"
        return _FakeResponse(_ada())

    def fake_put(url, json=None, headers=None, timeout=None):
        calls.append("PUT")
        assert url == f"{USERS_URL}/u1"
        assert json["requiredActions"] == []
        return _FakeResponse({}, status_code=204)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.post", fake_post)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.put", fake_put)

    user = KeycloakAuthProvider().directory_admin.create_user(
        username="ada",
        authentication_identifier="m8flow",
        email="ada@example.com",
        password="secret",
    )
    assert calls == ["POST", "GET", "PUT"]
    assert user.subject == "u1"
    assert user.username == "ada"


def test_create_user_conflict_is_provider_unavailable(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.post",
        lambda *args, **kwargs: _FakeResponse({"error": "exists"}, status_code=409),
    )
    with pytest.raises(ProviderUnavailable, match="already exists"):
        KeycloakAuthProvider().directory_admin.create_user(
            username="ada",
            authentication_identifier="m8flow",
            password="secret",
        )


def test_delete_user_by_username(monkeypatch):
    deleted: list[str] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse([_ada()])

    def fake_delete(url, headers=None, timeout=None):
        deleted.append(url)
        return _FakeResponse({}, status_code=204)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.delete",
        fake_delete,
    )
    KeycloakAuthProvider().directory_admin.delete_user(
        username="ada",
        authentication_identifier="m8flow",
    )
    assert deleted == [f"{USERS_URL}/u1"]


def test_delete_user_missing_username_raises_user_not_found(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *args, **kwargs: _FakeResponse([]),
    )
    with pytest.raises(UserNotFound):
        KeycloakAuthProvider().directory_admin.delete_user(
            username="missing",
            authentication_identifier="m8flow",
        )


def test_delete_user_by_id_treats_404_as_success(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.delete",
        lambda *args, **kwargs: _FakeResponse({}, status_code=404),
    )
    directory.delete_user_by_id("m8flow", "u1")


def test_create_user_in_realm_controller_returns_existing_http_shape(monkeypatch):
    class _Admin:
        def create_user(self, **kwargs):
            return User(subject="u1", username=kwargs["username"], email=kwargs.get("email"))

    class _Provider:
        @property
        def directory_admin(self):
            return _Admin()

    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: _Provider(),
    )
    body, status = create_user_in_realm(
        "m8flow",
        {"username": "ada", "password": "secret", "email": "ada@example.com"},
    )
    assert status == 201
    assert body == {"user_id": "u1", "location": "/admin/realms/m8flow/users/u1"}


def test_create_user_in_realm_controller_maps_conflict_to_409(monkeypatch):
    class _Admin:
        def create_user(self, **kwargs):
            raise ProviderUnavailable("User already exists")

    class _Provider:
        @property
        def directory_admin(self):
            return _Admin()

    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: _Provider(),
    )
    body, status = create_user_in_realm("m8flow", {"username": "ada", "password": "secret"})
    assert status == 409
    assert body == {"detail": "User already exists or conflict"}
