from __future__ import annotations

from typing import Any

import pytest
import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TenantNotFound, UserNotFound
from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings


ORGS_URL = "http://keycloak.internal/admin/realms/m8flow/organizations"
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
def _tenant_http(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
        lambda: "admin-token",
    )
    reset_keycloak_settings()
    yield
    reset_keycloak_settings()


def _acme() -> dict[str, Any]:
    return {"id": "org-1", "alias": "acme", "name": "Acme"}


def _ada() -> dict[str, Any]:
    return {
        "id": "u1",
        "username": "ada",
        "email": "ada@example.com",
        "firstName": "Ada",
        "lastName": "Lovelace",
    }


def test_get_tenant_by_id_returns_neutral_tenant(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == f"{ORGS_URL}/org-1"
        assert headers["Authorization"] == "Bearer admin-token"
        return _FakeResponse(_acme())

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    tenant = KeycloakAuthProvider().directory_admin.get_tenant(TenantRef(id="org-1"))
    assert tenant == Tenant(ref=TenantRef(id="org-1", alias="acme", name="Acme"), display_name="Acme")


def test_get_tenant_by_alias_returns_neutral_tenant(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == ORGS_URL
        return _FakeResponse([_acme()])

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    tenant = KeycloakAuthProvider().directory_admin.get_tenant(TenantRef(alias="acme"))
    assert tenant.ref.id == "org-1"
    assert tenant.ref.alias == "acme"


def test_get_tenant_raises_tenant_not_found(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.get",
        lambda *args, **kwargs: _FakeResponse([], status_code=200),
    )
    with pytest.raises(TenantNotFound):
        KeycloakAuthProvider().directory_admin.get_tenant(TenantRef(alias="missing"))


def test_create_tenant_posts_then_returns_neutral_tenant(monkeypatch):
    calls: list[str] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append("POST")
        assert url == ORGS_URL
        assert json["alias"] == "acme"
        return _FakeResponse({}, status_code=201, headers={"Location": f"{ORGS_URL}/org-1"})

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append("GET")
        assert url == f"{ORGS_URL}/org-1"
        return _FakeResponse(_acme())

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.post", fake_post)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.groups.ensure_default_groups",
        lambda *args, **kwargs: [],
    )
    tenant = KeycloakAuthProvider().directory_admin.create_tenant(alias="acme", name="Acme")
    assert calls == ["POST", "GET"]
    assert tenant.ref.id == "org-1"


def test_create_tenant_conflict_is_provider_unavailable(monkeypatch):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.requests.post",
        lambda *args, **kwargs: _FakeResponse({"error": "exists"}, status_code=409),
    )
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.groups.ensure_default_groups",
        lambda *args, **kwargs: [],
    )
    with pytest.raises(ProviderUnavailable, match="already exists"):
        KeycloakAuthProvider().directory_admin.create_tenant(alias="acme")


def test_add_member_by_username(monkeypatch):
    posted: list[Any] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == USERS_URL:
            return _FakeResponse([_ada()])
        if url == f"{ORGS_URL}/org-1":
            return _FakeResponse(_acme())
        raise AssertionError(url)

    def fake_post(url, json=None, headers=None, timeout=None):
        posted.append((url, json))
        return _FakeResponse({}, status_code=204)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.post", fake_post)
    membership = KeycloakAuthProvider().directory_admin.add_member(
        username="ada",
        tenant_ref=TenantRef(id="org-1"),
    )
    assert membership.tenant_ref.id == "org-1"
    assert posted == [(f"{ORGS_URL}/org-1/members", "u1")]


def test_get_member_raises_user_not_found(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if url == f"{ORGS_URL}/org-1":
            return _FakeResponse(_acme())
        if url == f"{ORGS_URL}/org-1/members":
            return _FakeResponse([])
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    with pytest.raises(UserNotFound):
        KeycloakAuthProvider().directory_admin.get_member(
            username="missing",
            tenant_ref=TenantRef(id="org-1"),
        )


def test_list_memberships_for_username(monkeypatch):
    member_orgs_url = f"{ORGS_URL}/members/u1/organizations"
    member_groups_url = f"{ORGS_URL}/org-1/members/u1/groups"

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == USERS_URL:
            return _FakeResponse([_ada()])
        if url == member_orgs_url:
            return _FakeResponse([_acme()])
        if url == member_groups_url:
            return _FakeResponse([{"name": "Designers"}])
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    memberships = KeycloakAuthProvider().list_memberships(username="ada")
    assert len(memberships) == 1
    assert memberships[0].tenant_ref.alias == "acme"
    assert memberships[0].roles == ["editor"]
    assert memberships[0].groups == ["editor"]


def test_list_memberships_for_username_empty_when_directory_has_no_orgs(monkeypatch):
    member_orgs_url = f"{ORGS_URL}/members/u1/organizations"

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == USERS_URL:
            return _FakeResponse([_ada()])
        if url == member_orgs_url:
            return _FakeResponse([], status_code=404)
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    memberships = KeycloakAuthProvider().list_memberships(username="ada")
    assert memberships == []
