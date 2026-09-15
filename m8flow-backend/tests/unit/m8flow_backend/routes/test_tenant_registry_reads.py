"""Tenant registry GETs are YAML-super-admin-only (`/m8flow/tenants*`).

Route checks use `allow_uri(..., group_fallback=False)` so the editor /
tenant-admin identifier fallback cannot leak the platform list.
"""
from __future__ import annotations

from types import SimpleNamespace

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.authorization import allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

_SERVICE = "https://example.test/realms/m8flow"
_REGISTRY = "/v1.0/m8flow/tenants"


def _provision(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service=_SERVICE,
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _headers(client, user, *, tenant_id: str = "t1"):
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


def test_unauthenticated_registry_reads_are_401(client):
    for path in (_REGISTRY, f"{_REGISTRY}/t1", f"{_REGISTRY}/slug/t1"):
        response = client.get(path)
        assert response.status_code == 401, path


def test_super_admin_can_list_and_fetch_tenants(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    headers = _headers(client, user)
    listed = client.get(_REGISTRY, headers=headers)
    assert listed.status_code == 200
    rows = listed.get_json()
    assert isinstance(rows, list)
    assert any(row["id"] == "t1" for row in rows)

    by_id = client.get(f"{_REGISTRY}/t1", headers=headers)
    assert by_id.status_code == 200
    assert by_id.get_json()["id"] == "t1"

    by_slug = client.get(f"{_REGISTRY}/slug/t1", headers=headers)
    assert by_slug.status_code == 200
    assert by_slug.get_json()["slug"] == "t1"


def test_editor_cannot_read_tenant_registry(client, db_session):
    user = _provision(db_session, username="editor", groups=["t1:editor"])
    headers = _headers(client, user)
    for path in (_REGISTRY, f"{_REGISTRY}/t1", f"{_REGISTRY}/slug/t1"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.get_json()["error_code"] == "permission_denied"


def test_reviewer_cannot_read_tenant_registry(client, db_session):
    user = _provision(db_session, username="reviewer", groups=["t1:reviewer"])
    headers = _headers(client, user)
    response = client.get(_REGISTRY, headers=headers)
    assert response.status_code == 403
    assert response.get_json()["error_code"] == "permission_denied"


def test_tenant_admin_cannot_list_or_get_tenant_registry(client, db_session):
    user = _provision(db_session, username="tadmin", groups=["t1:tenant-admin"])
    headers = _headers(client, user)
    for path in (_REGISTRY, f"{_REGISTRY}/t1", f"{_REGISTRY}/slug/t1"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.get_json()["error_code"] == "permission_denied"


def test_allow_uri_yaml_grant_without_fallback_denies_editor(db_session):
    editor = _provision(db_session, username="editor-yaml", groups=["t1:editor"])
    assert allow_uri(editor, "GET", _REGISTRY, session=db_session) is True
    assert allow_uri(editor, "GET", _REGISTRY, session=db_session, group_fallback=False) is False

    root = _provision(db_session, username="root-yaml", groups=["super-admin"])
    assert allow_uri(root, "GET", _REGISTRY, session=db_session, group_fallback=False) is True


class _FakeDirectoryAdmin:
    def create_tenant(self, *, alias: str, name: str | None = None):
        return Tenant(
            ref=TenantRef(id="org-created", alias=alias, name=name),
            display_name=name,
        )

    def update_tenant(self, tenant_ref: TenantRef, *, name: str):
        return Tenant(
            ref=TenantRef(id=tenant_ref.id, alias=tenant_ref.alias, name=name),
            display_name=name,
        )


def _patch_directory_admin(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: SimpleNamespace(directory_admin=_FakeDirectoryAdmin()),
    )


def test_super_admin_creates_and_renames_tenant(client, db_session, monkeypatch):
    user = _provision(db_session, username="root", groups=["super-admin"])
    headers = _headers(client, user)
    _patch_directory_admin(monkeypatch)

    created = client.post(
        "/v1.0/m8flow/tenant-realms",
        json={"slug": "acme-corp", "name": "Acme Corp"},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["id"] == "org-created"
    assert body["alias"] == "acme-corp"
    assert body["name"] == "Acme Corp"

    listed = client.get(_REGISTRY, headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == "org-created" and row["name"] == "Acme Corp" for row in listed.get_json())

    renamed = client.put(
        "/v1.0/m8flow/tenants/org-created",
        json={"name": "Acme Incorporated"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["name"] == "Acme Incorporated"

    fetched = client.get(f"{_REGISTRY}/org-created", headers=headers)
    assert fetched.status_code == 200
    assert fetched.get_json()["name"] == "Acme Incorporated"
    assert fetched.get_json()["slug"] == "acme-corp"


def test_editor_cannot_create_or_rename_tenants(client, db_session, monkeypatch):
    user = _provision(db_session, username="editor", groups=["t1:editor"])
    headers = _headers(client, user)
    _patch_directory_admin(monkeypatch)

    created = client.post(
        "/v1.0/m8flow/tenant-realms",
        json={"slug": "should-not-exist", "name": "Should Not Exist"},
        headers=headers,
    )
    assert created.status_code == 403

    renamed = client.put(
        "/v1.0/m8flow/tenants/t1",
        json={"name": "Hijacked"},
        headers=headers,
    )
    assert renamed.status_code == 403

    root = _provision(db_session, username="root2", groups=["super-admin"])
    listed = client.get(f"{_REGISTRY}/t1", headers=_headers(client, root))
    assert listed.status_code == 200
    assert listed.get_json()["name"] != "Hijacked"
