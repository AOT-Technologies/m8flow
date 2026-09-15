"""Regression coverage for architecture review finding C5: the primary
DB-grant (m8flow.yml permission) path was silently broken for every caller,
multi-org or not, for two independent reasons now fixed:

1. Ordinary login (auth.sync_groups_from_token) synced a user's tenant-
   qualified group (e.g. "org-a:reviewer") but never called
   identity.import_yaml(tenant_id=...), so that tenant's YAML permissions
   were never materialized as PermissionAssignmentModel rows. Only the
   Keycloak-organization-member-sync path did this.
2. Even when the DB rows existed, authorization.allow_uri compared the real,
   /v1.0-prefixed route path (e.g. "/v1.0/tasks") against m8flow.yml's
   unprefixed uris (e.g. "/tasks") and never matched.

Both bugs meant every route fell through to _group_identifier_fallback,
which grants reviewer only on a couple of hardcoded path substrings and
grants editor/tenant-admin *unconditionally on every path* -- so a test
that only exercises `allow_uri` can't tell the real grant from the escape
hatch. Where that ambiguity matters (editor), these tests assert against
authorization._uri_permitted directly, the primary mechanism the review
flagged as unverified.
"""

from __future__ import annotations

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.authorization import _uri_permitted, allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME


def _provision_tenant_role(db_session, *, username: str, service: str, group_identifier: str, tenant_id: str):
    """Mirrors what a real login now does end-to-end for a shared-realm tenant
    role: create the membership, sync the tenant-qualified group, then seed
    that tenant's m8flow.yml permissions into the DB -- the step ordinary
    login was missing before auth.sync_groups_from_token started calling
    identity.import_yaml itself."""
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(db_session, username=username, service=service, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[group_identifier], tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def test_multi_org_reviewer_route_access_granted_via_real_db_permission_rows(client, db_session):
    """Route-level: a reviewer in one org of a multi-org account gets GET
    /v1.0/tasks -- and GET /v1.0/users/search, a path _group_identifier_fallback
    never special-cases, so this can only pass via the real DB grant -- while
    correctly staying denied on a uri m8flow.yml never grants reviewer."""
    user = _provision_tenant_role(
        db_session,
        username="reviewer",
        service="https://example.test/realms/m8flow",
        group_identifier="org-a:reviewer",
        tenant_id="org-a",
    )
    token = encode_auth_token(user=user)
    headers = {"Authorization": f"Bearer {token}"}
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "org-a")

    tasks = client.get("/v1.0/tasks", headers=headers)
    assert tasks.status_code == 200

    assert allow_uri(user, "GET", "/v1.0/users/search", session=db_session) is True
    assert allow_uri(user, "GET", "/v1.0/process-instances", session=db_session) is False


def test_multi_org_editor_granted_via_real_db_permission_rows(db_session):
    """A second org, a different role: editor is also covered unconditionally
    by _group_identifier_fallback (any path, any action), so assert against
    _uri_permitted directly -- the only way to prove the real DB grant (not
    the fallback) is what's actually working, including that it correctly
    denies what editor was never granted."""
    user = _provision_tenant_role(
        db_session,
        username="editor",
        service="https://example.test/realms/m8flow",
        group_identifier="org-b:editor",
        tenant_id="org-b",
    )

    assert _uri_permitted(db_session, user, "read", "/process-instances") is True
    assert _uri_permitted(db_session, user, "create", "/process-instances") is True
    assert _uri_permitted(db_session, user, "read", "/secrets") is False
