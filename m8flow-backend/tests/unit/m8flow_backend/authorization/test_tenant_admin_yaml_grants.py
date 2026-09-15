"""YAML grant boundary for tenant-admin members/groups/roles.

`_uri_permitted` is the seam (same as test_v1_permission_gaps): it reads DB
rows from m8flow.yml and never consults `_group_identifier_fallback`, which
would otherwise let tenant-admin (and editor) through on every path.
"""

from __future__ import annotations

from m8flow_backend import identity
from m8flow_backend.authorization import _uri_permitted
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_TENANT_ID = "t1"
_SERVICE = "https://example.test/realms/m8flow"

_MEMBER_PATHS = (
    f"/m8flow/tenants/{_TENANT_ID}/members",
    f"/m8flow/tenants/{_TENANT_ID}/members/alice",
    f"/m8flow/tenants/{_TENANT_ID}/members/alice/roles/submitter",
    f"/m8flow/tenants/{_TENANT_ID}/available-users",
    f"/m8flow/tenants/{_TENANT_ID}/groups",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers/members/alice",
    f"/m8flow/tenants/{_TENANT_ID}/groups/Designers/roles/submitter",
)

_INVITATION_PATHS = (
    f"/m8flow/tenants/{_TENANT_ID}/invitations",
    f"/m8flow/tenants/{_TENANT_ID}/invitations/inv-1",
    f"/m8flow/tenants/{_TENANT_ID}/invitations/inv-1/resend",
)


def _provision_tenant_role(db_session, *, username: str, group_name: str):
    tenant = ensure_tenant(db_session, tenant_id=_TENANT_ID, slug=_TENANT_ID)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"{_TENANT_ID}:{group_name}"], tenant_id=_TENANT_ID)
    identity.import_yaml(db_session, tenant_id=_TENANT_ID)
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def test_tenant_admin_yaml_grants_members_groups_and_roles(db_session):
    user = _provision_tenant_role(db_session, username="tadmin-yaml", group_name="tenant-admin")
    for path in _MEMBER_PATHS:
        for action in ("read", "create", "update", "delete"):
            if path.endswith("/available-users") and action != "read":
                continue
            assert _uri_permitted(db_session, user, action, path) is True, (action, path)


def test_tenant_admin_yaml_does_not_grant_invitation_management(db_session):
    """Invitation HTTP stays super-admin-only. Do not add read/create/delete
    YAML rows for invitations. `update /m8flow/tenants/*` (rename) already
    prefix-matches invitation paths; there is no PUT invitation route."""
    user = _provision_tenant_role(db_session, username="tadmin-invites", group_name="tenant-admin")
    for path in _INVITATION_PATHS:
        for action in ("read", "create", "delete"):
            assert _uri_permitted(db_session, user, action, path) is False, (action, path)


def test_editor_yaml_does_not_grant_members_or_groups(db_session):
    user = _provision_tenant_role(db_session, username="editor-yaml-members", group_name="editor")
    for path in _MEMBER_PATHS:
        assert _uri_permitted(db_session, user, "read", path) is False, path
        assert _uri_permitted(db_session, user, "create", path) is False, path


def test_tenant_admin_yaml_does_not_grant_tenant_registry_reads(db_session):
    """read on members/groups must not open super-admin registry GET by id."""
    user = _provision_tenant_role(db_session, username="tadmin-registry", group_name="tenant-admin")
    for path in ("/m8flow/tenants", f"/m8flow/tenants/{_TENANT_ID}", f"/m8flow/tenants/slug/{_TENANT_ID}"):
        assert _uri_permitted(db_session, user, "read", path) is False, path
