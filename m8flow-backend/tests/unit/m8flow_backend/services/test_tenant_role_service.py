"""Regression coverage for tenant_role_service.py's own internals.

Ticket 07's audit (auth-provider-seam wayfinder map) found zero existing test
exercised this file's actual Keycloak-calling logic -- the only other test
file (test_tenant_role_controller.py) mocks these functions away entirely to
test route-level RBAC. This file closes that gap: it mocks Keycloak at the
HTTP/admin-client boundary, the way test_groups.py/test_tenants.py/
test_directory.py already do for the adapter itself, and exercises the three
top-level read entry points end to end -- including the pagination loop and
the ThreadPoolExecutor fan-out with more than one item, both called out by
the audit as needing coverage before the drain (tickets 08/09) touches them.
"""
from __future__ import annotations

import time
from typing import Any

import pytest
import requests

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings
from m8flow_backend.services import tenant_role_service as roles

REALM_URL = "http://keycloak.internal/admin/realms/m8flow"
ORGS_URL = f"{REALM_URL}/organizations"
ORG_URL = f"{ORGS_URL}/org-1"
GROUPS_URL = f"{ORG_URL}/groups"
MEMBERS_URL = f"{ORG_URL}/members"
USERS_URL = f"{REALM_URL}/users"


class _FakeResponse:
    def __init__(self, payload: Any = None, status_code: int = 200, headers: dict[str, str] | None = None):
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
def _tenant_role_service_http(monkeypatch):
    from m8flow_backend.integrations.auth.keycloak.client_auth import reset_master_admin_token_cache

    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
        lambda: "admin-token",
    )
    # tenant_role_service.py no longer imports fetch_master_admin_token at all
    # (auth-provider-seam wayfinder map, ticket 15 drained the admin_token
    # threading entirely) -- the admin_client patch above is the only one
    # needed now; every Keycloak call goes through the cached capability
    # surface instead of a raw admin token passed by hand.
    reset_keycloak_settings()
    reset_master_admin_token_cache()
    yield
    reset_keycloak_settings()
    reset_master_admin_token_cache()


def _seed_tenant(db_session, *, tenant_id: str = "org-1", slug: str = "acme") -> M8flowTenantModel:
    now = int(time.time())
    tenant = M8flowTenantModel(
        id=tenant_id,
        slug=slug,
        name="Acme",
        status=TenantStatus.ACTIVE.value,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _org() -> dict[str, Any]:
    return {"id": "org-1", "alias": "acme", "name": "Acme"}


def _administrators() -> dict[str, Any]:
    # No explicit role-mapping attributes -- relies on the same Keycloak-name
    # fallback test_groups.py's test_tenant_roles_for_organization_group_hides_keycloak_names
    # already pins ("Administrators" -> tenant-admin), so this fixture doesn't
    # need to hand-construct attribute payloads.
    return {"id": "g-admin", "name": "Administrators", "path": "/Administrators"}


def _designers() -> dict[str, Any]:
    return {"id": "g-designers", "name": "Designers", "path": "/Designers"}


def _ada() -> dict[str, Any]:
    return {"id": "u-ada", "username": "ada", "email": "ada@example.com", "firstName": "Ada", "lastName": "L"}


def _bob() -> dict[str, Any]:
    return {"id": "u-bob", "username": "bob", "email": "bob@example.com", "firstName": "Bob", "lastName": "R"}


def _carol() -> dict[str, Any]:
    return {"id": "u-carol", "username": "carol", "email": "carol@example.com"}


def test_list_tenant_members_with_roles_maps_group_membership_to_roles(monkeypatch, db_session):
    """End-to-end: org lookup, member search, full-representation group list,
    and the per-member group-lookup fan-out (>1 member -> ThreadPoolExecutor),
    landing on the correct neutral role per member."""
    _seed_tenant(db_session)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == ORG_URL:
            return _FakeResponse(_org())
        if url == MEMBERS_URL:
            return _FakeResponse([_ada(), _bob()])
        if url == GROUPS_URL:
            return _FakeResponse([_administrators(), _designers()])
        if url == USERS_URL:
            # list_member_groups (the neutral capability, ticket 15) resolves
            # username -> Keycloak user id itself before listing that user's
            # groups -- a lookup the old raw member_id-keyed helpers never
            # needed to make.
            username = (params or {}).get("username")
            by_username = {"ada": _ada(), "bob": _bob()}
            match = by_username.get(username)
            return _FakeResponse([match] if match else [])
        if url == f"{ORG_URL}/members/u-ada/groups":
            return _FakeResponse([_administrators()])
        if url == f"{ORG_URL}/members/u-bob/groups":
            return _FakeResponse([_designers()])
        if url == f"{GROUPS_URL}/g-admin":
            return _FakeResponse(_administrators())
        if url == f"{GROUPS_URL}/g-designers":
            return _FakeResponse(_designers())
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)

    members = roles.list_tenant_members_with_roles("org-1")

    by_username = {member["username"]: member for member in members}
    assert by_username["ada"]["roles"] == ["tenant-admin"]
    assert by_username["bob"]["roles"] == ["editor"]
    assert {g["name"] for g in by_username["ada"]["groups"]} == {"Administrators"}


def test_list_tenant_groups_with_members_lists_members_per_group(monkeypatch, db_session):
    """End-to-end: full-representation group list, then the per-group
    member-lookup fan-out (>1 group -> ThreadPoolExecutor)."""
    _seed_tenant(db_session)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == ORG_URL:
            return _FakeResponse(_org())
        if url == GROUPS_URL:
            return _FakeResponse([_administrators(), _designers()])
        if url == f"{GROUPS_URL}/g-admin/members":
            return _FakeResponse([_ada()])
        if url == f"{GROUPS_URL}/g-designers/members":
            return _FakeResponse([_bob()])
        if url == f"{GROUPS_URL}/g-admin":
            return _FakeResponse(_administrators())
        if url == f"{GROUPS_URL}/g-designers":
            return _FakeResponse(_designers())
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)

    groups = roles.list_tenant_groups_with_members("org-1")

    by_name = {group["name"]: group for group in groups}
    assert by_name["Administrators"]["mapped_roles"] == ["tenant-admin"]
    assert [m["username"] for m in by_name["Administrators"]["members"]] == ["ada"]
    assert by_name["Designers"]["mapped_roles"] == ["editor"]
    assert [m["username"] for m in by_name["Designers"]["members"]] == ["bob"]


def test_list_available_tenant_users_excludes_existing_members(monkeypatch, db_session):
    """End-to-end: the manual realm-wide pagination loop, and the per-username
    existing-membership fan-out (>1 candidate -> ThreadPoolExecutor), correctly
    excluding users who are already org members."""
    _seed_tenant(db_session)

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == ORG_URL:
            return _FakeResponse(_org())
        if url == USERS_URL:
            return _FakeResponse([_ada(), _bob(), _carol()])
        if url == MEMBERS_URL:
            search = (params or {}).get("search")
            if search == "ada":
                return _FakeResponse([_ada()])
            if search == "bob":
                return _FakeResponse([_bob()])
            if search == "carol":
                return _FakeResponse([])
            raise AssertionError(f"unexpected members search: {params}")
        raise AssertionError(url)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)

    available = roles.list_available_tenant_users("org-1")

    assert [user["username"] for user in available] == ["carol"]


def test_add_tenant_member_assigns_roles_via_capability(app, monkeypatch, db_session):
    """The `roles=` parameter added to add_tenant_member (auth-provider-seam
    wayfinder map, ticket 16) maps each neutral role to its group via the
    same assign_roles capability assign_tenant_role already uses, so a
    caller with roles in hand (tenant_invitation_service.accept_invitation)
    never builds Keycloak group names by hand."""
    from flask import g

    _seed_tenant(db_session)
    put_urls: list[str] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == ORG_URL:
            return _FakeResponse(_org())
        if url == MEMBERS_URL:
            return _FakeResponse([_ada()])
        if url == USERS_URL:
            return _FakeResponse([_ada()])
        if url == GROUPS_URL:
            return _FakeResponse([_designers()])
        if url == f"{ORG_URL}/members/u-ada/groups":
            return _FakeResponse([_designers()])
        raise AssertionError(url)

    def fake_put(url, json=None, headers=None, timeout=None):
        put_urls.append(url)
        return _FakeResponse({}, status_code=204)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.put", fake_put)

    with app.test_request_context("/"):
        g.db_session = db_session
        member = roles.add_tenant_member("org-1", username="ada", roles=["editor"])

    assert put_urls == [f"{GROUPS_URL}/g-designers/members/u-ada"]
    assert member["username"] == "ada"
    assert member["roles"] == ["editor"]


def test_master_admin_token_is_cached_across_calls(monkeypatch):
    """The audit's caching fix: fetch_master_admin_token() must not re-hit
    Keycloak on every call within its TTL -- this is what lets the drain route
    everything through capability calls without an admin-token-per-call
    performance regression."""
    from m8flow_backend.integrations.auth.keycloak import client_auth

    client_auth.reset_master_admin_token_cache()
    calls = {"count": 0}

    def fake_post(url, data=None, headers=None, timeout=None):
        calls["count"] += 1
        return _FakeResponse({"access_token": f"token-{calls['count']}", "expires_in": 60}, status_code=200)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.client_auth.requests.post", fake_post)
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.client_auth.keycloak_admin_password",
        lambda: "admin-pw",
    )
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.client_auth.keycloak_admin_user",
        lambda: "admin",
    )

    first = client_auth.fetch_master_admin_token()
    second = client_auth.fetch_master_admin_token()

    assert first == second == "token-1"
    assert calls["count"] == 1
    client_auth.reset_master_admin_token_cache()
