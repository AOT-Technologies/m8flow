"""HTTP isolation for tenant-admin members/groups/roles and invitation management.

YAML `_uri_permitted` coverage lives in test_tenant_admin_yaml_grants. This
suite hits Flask routes: tenant-admin own tenant 2xx, editor/reviewer 403,
super-admin any tenant, tenant-admin cannot reach another tenant's members, and
invitation management is super-admin 2xx / tenant-admin 403. Directory calls
are stubbed so a 200 is authorization, not Keycloak.
"""

from __future__ import annotations

import time

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

_SERVICE = "https://example.test/realms/m8flow"
_MEMBERS = "/v1.0/m8flow/tenants/{tid}/members"
_GROUPS = "/v1.0/m8flow/tenants/{tid}/groups"
_INVITES = "/v1.0/m8flow/tenants/{tid}/invitations"

_SAMPLE_MEMBER = {
    "id": "u1",
    "username": "alice",
    "email": None,
    "display_name": None,
    "roles": ["editor"],
    "groups": [],
}
_SAMPLE_GROUP = {
    "id": "g1",
    "name": "Designers",
    "path": "/Designers",
    "mapped_roles": ["editor"],
    "member_count": 0,
    "members": [],
}
_SAMPLE_INVITE = {
    "id": "inv-1",
    "tenant_id": "t1",
    "email": "invitee@example.test",
    "roles": ["editor"],
    "status": "PENDING",
    "expires_at_in_seconds": 1,
    "created_by": "root",
    "created_at_in_seconds": 1,
}

# method, path template, json body or None, success status
_MEMBER_GROUP_OPS = (
    ("GET", _MEMBERS, None, 200),
    ("POST", _MEMBERS, {"username": "alice"}, 201),
    ("DELETE", _MEMBERS + "/alice", None, 200),
    ("GET", _GROUPS, None, 200),
    ("POST", _GROUPS, {"name": "Designers"}, 201),
    ("PUT", _GROUPS + "/Designers", {"name": "Leads"}, 200),
    ("DELETE", _GROUPS + "/Designers", None, 200),
    ("PUT", _GROUPS + "/Designers/roles/editor", None, 200),
)

_INVITE_OPS = (
    ("GET", _INVITES, None, 200),
    ("POST", _INVITES, {"email": "invitee@example.test", "roles": ["editor"], "validity_days": 7}, 201),
    ("POST", _INVITES + "/inv-1/resend", None, 200),
    ("DELETE", _INVITES + "/inv-1", None, 200),
)


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str):
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
    import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, token


def _call(client, method: str, path: str, token: str, json_body=None):
    kwargs = {"headers": {"Authorization": f"Bearer {token}"}}
    if json_body is not None:
        kwargs["json"] = json_body
    return getattr(client, method.lower())(path, **kwargs)


@pytest.fixture
def stub_directory(monkeypatch):
    import m8flow_backend.routes.tenant_invitation_controller as invitations
    import m8flow_backend.routes.tenant_role_controller as roles

    monkeypatch.setattr(roles, "list_tenant_members_with_roles", lambda *a, **k: [_SAMPLE_MEMBER])
    monkeypatch.setattr(roles, "add_tenant_member", lambda *a, **k: _SAMPLE_MEMBER)
    monkeypatch.setattr(roles, "remove_tenant_member", lambda *a, **k: "alice")
    monkeypatch.setattr(roles, "list_tenant_groups_with_members", lambda *a, **k: [_SAMPLE_GROUP])
    monkeypatch.setattr(roles, "create_tenant_group", lambda *a, **k: _SAMPLE_GROUP)
    monkeypatch.setattr(roles, "rename_tenant_group", lambda *a, **k: {**_SAMPLE_GROUP, "name": "Leads"})
    monkeypatch.setattr(roles, "delete_tenant_group", lambda *a, **k: "Designers")
    monkeypatch.setattr(roles, "assign_tenant_group_role", lambda *a, **k: _SAMPLE_GROUP)
    monkeypatch.setattr(
        invitations,
        "list_invitations",
        lambda *a, **k: {"results": [], "total": 0, "offset": 0, "limit": 10},
    )
    monkeypatch.setattr(invitations, "create_invitation", lambda *a, **k: _SAMPLE_INVITE)
    monkeypatch.setattr(invitations, "resend_invitation", lambda *a, **k: _SAMPLE_INVITE)
    monkeypatch.setattr(
        invitations,
        "revoke_invitation",
        lambda *a, **k: {**_SAMPLE_INVITE, "status": "REVOKED"},
    )


@pytest.mark.parametrize("method,path_tpl,body,status", _MEMBER_GROUP_OPS)
def test_tenant_admin_manages_own_tenant_members_and_groups(
    client, db_session, stub_directory, method, path_tpl, body, status
):
    _user, token = _login_user(
        client, db_session, username="tadmin", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    response = _call(client, method, path_tpl.format(tid="t1"), token, body)
    assert response.status_code == status, (method, path_tpl, response.get_json())


@pytest.mark.parametrize("username,groups", (("editor", ["t1:editor"]), ("reviewer", ["t1:reviewer"])))
@pytest.mark.parametrize("method,path_tpl,body,_status", _MEMBER_GROUP_OPS)
def test_editor_and_reviewer_are_forbidden_on_members_and_groups(
    client, db_session, stub_directory, username, groups, method, path_tpl, body, _status
):
    _user, token = _login_user(client, db_session, username=username, groups=groups, tenant_id="t1")
    response = _call(client, method, path_tpl.format(tid="t1"), token, body)
    assert response.status_code == 403, (username, method, path_tpl, response.get_json())


@pytest.mark.parametrize("method,path_tpl,body,status", _MEMBER_GROUP_OPS)
def test_super_admin_can_manage_another_tenant(
    client, db_session, stub_directory, method, path_tpl, body, status
):
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    db_session.commit()
    _user, token = _login_user(
        client, db_session, username="root", groups=["super-admin"], tenant_id="t1"
    )
    response = _call(client, method, path_tpl.format(tid="t2"), token, body)
    assert response.status_code == status, (method, path_tpl, response.get_json())


def test_tenant_admin_cannot_list_another_tenant_members(client, db_session, stub_directory):
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    import_yaml(db_session, tenant_id="t2")
    db_session.commit()
    _user, token = _login_user(
        client, db_session, username="tadmin-cross", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    response = _call(client, "GET", _MEMBERS.format(tid="t2"), token)
    assert response.status_code == 403
    assert response.get_json()["message"] == "Not authorized to manage another tenant."


@pytest.mark.parametrize("method,path_tpl,body,status", _INVITE_OPS)
def test_super_admin_can_manage_invitations(client, db_session, stub_directory, method, path_tpl, body, status):
    _user, token = _login_user(
        client, db_session, username="root-invites", groups=["super-admin"], tenant_id="t1"
    )
    response = _call(client, method, path_tpl.format(tid="t1"), token, body)
    assert response.status_code == status, (method, path_tpl, response.get_json())


@pytest.mark.parametrize("method,path_tpl,body,_status", _INVITE_OPS)
def test_tenant_admin_cannot_manage_invitations(
    client, db_session, stub_directory, method, path_tpl, body, _status
):
    _user, token = _login_user(
        client, db_session, username="tadmin-invites", groups=["t1:tenant-admin"], tenant_id="t1"
    )
    response = _call(client, method, path_tpl.format(tid="t1"), token, body)
    assert response.status_code == 403, (method, path_tpl, response.get_json())
    assert response.get_json()["message"] == "Only super admins can manage tenant invitations."


class _ThinTenantAdminProvider:
    issuer = _SERVICE

    def verify_token(self, token: str) -> VerifiedClaims:
        # "Thin" on purpose: this session's own token only asserts the one
        # organization it was scoped to (t1) -- not every tenant Keycloak's
        # directory happens to know about. ensure_request_can_access_tenant
        # reads VerifiedClaims.memberships (auth-provider-seam wayfinder map,
        # ticket 10), so this is the request-scoping boundary: it must NOT
        # include t2, or a thin t1 session could reach t2 data. The fuller
        # t1+t2 list in list_memberships() below is the separate directory
        # lookup group-sync enrichment uses -- that gap between "what this
        # token asserts" and "what the directory actually knows" is the
        # whole "thin token enrichment" this test is about.
        del token
        return VerifiedClaims(
            subject="kc-tadmin-1",
            issuer=self.issuer,
            username="stale-tadmin",
            roles=[],
            memberships=[Membership(tenant_ref=TenantRef(id="t1", alias="t1"), roles=[], groups=[])],
            jwt_claims={
                "sub": "kc-tadmin-1",
                "iss": self.issuer,
                "preferred_username": "stale-tadmin",
            },
        )

    def list_memberships(self, *, username: str) -> list[Membership]:
        del username
        return [
            Membership(
                tenant_ref=TenantRef(id="t1", alias="t1"),
                roles=["tenant-admin"],
                groups=["tenant-admin"],
            ),
            Membership(
                tenant_ref=TenantRef(id="t2", alias="t2"),
                roles=["editor"],
                groups=["editor"],
            ),
        ]


def test_stale_shared_realm_user_thin_token_enriches_before_member_apis(
    client, db_session, monkeypatch, stub_directory
):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    issuer = _ThinTenantAdminProvider.issuer
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    ensure_tenant(db_session, tenant_id="t2", slug="t2")
    user = ensure_user(
        db_session,
        username="stale-tadmin",
        service=issuer,
        service_id="kc-tadmin-1",
    )
    ensure_membership(db_session, user, tenant)
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    identifiers_before = {getattr(group, "identifier", "") for group in user.groups}
    assert "t1:tenant-admin" not in identifiers_before

    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.get_auth_provider",
        lambda: _ThinTenantAdminProvider(),
    )
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {
            "sub": "kc-tadmin-1",
            "iss": issuer,
            "preferred_username": "stale-tadmin",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    headers = {"Authorization": f"Bearer {token}"}

    listed = client.get(_MEMBERS.format(tid="t1"), headers=headers)
    assert listed.status_code == 200
    other = client.get(_MEMBERS.format(tid="t2"), headers=headers)
    assert other.status_code == 403

    db_session.expire_all()
    db_session.refresh(user)
    identifiers = {getattr(group, "identifier", "") for group in user.groups}
    assert "t1:tenant-admin" in identifiers
    assert "t2:editor" not in identifiers


def test_editor_onboarding_and_tasks_still_pass(client, db_session):
    _user, token = _login_user(client, db_session, username="editor-rbac", groups=["t1:editor"], tenant_id="t1")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200


def test_reviewer_onboarding_and_tasks_multi_org_still_pass(client, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    user, token = _login_user(
        client, db_session, username="reviewer-rbac", groups=["org-a:reviewer"], tenant_id="org-a"
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1.0/onboarding", headers=headers).status_code == 200
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200

    tenant_b = ensure_tenant(db_session, tenant_id="org-b", slug="org-b")
    ensure_membership(db_session, user, tenant_b)
    sync_groups(db_session, user=user, group_identifiers=["org-b:reviewer"], tenant_id="org-b")
    ensure_v1_role(db_session, tenant_id="org-b", role_name="user", user_ids=(user.id,))
    db_session.commit()
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "org-b")
    second = client.get("/v1.0/onboarding", headers=headers)
    assert second.status_code == 200
    assert second.get_json()["tenant_id"] == "org-b"
    assert client.get("/v1.0/tasks", headers=headers).status_code == 200
