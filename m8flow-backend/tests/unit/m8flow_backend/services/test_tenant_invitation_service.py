"""Regression coverage for architecture review finding S2: create_invitation
and resend_invitation committed the invitation row (or the invitation's
rotated token) *before* attempting to send the email. email_service.send_email
raises on a genuine configured-SMTP failure (it only returns False, no raise,
in dev mode when SMTP isn't configured at all) -- so a transient SMTP outage
left a dangling, un-retryable invitation row behind (create), or silently
invalidated the invitation's still-usable existing link while never
delivering the new one (resend). Both now send before persisting.
"""

from __future__ import annotations

import time

import pytest
from flask import g

from m8flow_backend.integrations.auth.base.errors import UserNotFound
from m8flow_backend.integrations.auth.base.models import IssuerRef
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.models.tenant_invitation import M8flowTenantInvitationModel, TenantInvitationStatus
from m8flow_backend.services import tenant_invitation_service


class _FakeResponse:
    """Minimal requests.Response stand-in for the Keycloak-shaped HTTP mocks
    used by test_accept_invitation_creates_user_and_grants_tenant_role_via_capability
    below -- same shape as test_tenant_role_service.py's own copy."""

    def __init__(self, payload=None, status_code: int = 200, headers: dict[str, str] | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            error = requests.HTTPError(f"http {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _bind_request_scoped_session(app, db_session):
    with app.test_request_context("/"):
        g.db_session = db_session
        yield


@pytest.fixture(autouse=True)
def _fake_auth_provider(monkeypatch):
    """create_invitation/resend_invitation both check the shared-realm
    directory for an existing user with this email; a not-found result is
    the only path these tests need."""

    class _FakeProvider:
        def get_user(self, **_kwargs):
            raise UserNotFound("no such user")

        def default_issuer(self) -> IssuerRef:
            return IssuerRef(value="m8flow")

    monkeypatch.setattr(tenant_invitation_service, "get_auth_provider", lambda: _FakeProvider())


def _seed_tenant(db_session, *, tenant_id: str = "t1") -> M8flowTenantModel:
    now = int(time.time())
    tenant = M8flowTenantModel(
        id=tenant_id,
        slug=tenant_id,
        name="Tenant One",
        status=TenantStatus.ACTIVE.value,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_create_invitation_sends_before_persisting_the_row(db_session, monkeypatch):
    _seed_tenant(db_session)
    monkeypatch.setattr(tenant_invitation_service, "send_email", lambda *a, **k: True)

    result = tenant_invitation_service.create_invitation(
        "t1", "invitee@example.com", ["editor"], None, "admin"
    )

    assert result["status"] == "PENDING"
    row = db_session.query(M8flowTenantInvitationModel).filter_by(email="invitee@example.com").first()
    assert row is not None
    assert row.status == TenantInvitationStatus.PENDING


def test_create_invitation_does_not_persist_a_dangling_row_on_smtp_failure(db_session, monkeypatch):
    def _raise(*_a, **_k):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(tenant_invitation_service, "send_email", _raise)
    _seed_tenant(db_session)

    with pytest.raises(ConnectionRefusedError):
        tenant_invitation_service.create_invitation(
            "t1", "invitee@example.com", ["editor"], None, "admin"
        )

    assert db_session.query(M8flowTenantInvitationModel).filter_by(email="invitee@example.com").count() == 0


def test_resend_invitation_does_not_rotate_the_token_on_smtp_failure(db_session, monkeypatch):
    tenant = _seed_tenant(db_session)
    monkeypatch.setattr(tenant_invitation_service, "send_email", lambda *a, **k: True)
    created = tenant_invitation_service.create_invitation(
        "t1", "invitee@example.com", ["editor"], None, "admin"
    )
    row = db_session.query(M8flowTenantInvitationModel).filter_by(id=created["id"]).one()
    original_token_hash = row.token_hash

    def _raise(*_a, **_k):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(tenant_invitation_service, "send_email", _raise)

    with pytest.raises(ConnectionRefusedError):
        tenant_invitation_service.resend_invitation(tenant.id, row.id, "admin")

    db_session.expire_all()
    unchanged = db_session.query(M8flowTenantInvitationModel).filter_by(id=row.id).one()
    assert unchanged.token_hash == original_token_hash
    assert unchanged.status == TenantInvitationStatus.PENDING


def test_create_invitation_email_and_dev_link_use_designer_accept_url(db_session, monkeypatch):
    captured: dict[str, str] = {}

    def _capture(_email, _subject, html_body, text_body=None):
        captured["html"] = html_body
        captured["text"] = text_body or ""
        return False

    monkeypatch.setattr(tenant_invitation_service, "send_email", _capture)
    monkeypatch.delenv("M8FLOW_FRONTEND_BASE_URL", raising=False)
    monkeypatch.delenv("M8FLOW_APP_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("KEYCLOAK_HOSTNAME", "http://localhost:6842")
    _seed_tenant(db_session)

    result = tenant_invitation_service.create_invitation(
        "t1", "invitee@example.com", ["editor"], None, "admin"
    )

    link = result["invitation_link"]
    assert link.startswith("http://localhost:6853/accept-invitation?token=")
    assert link in captured["html"]
    assert link in captured["text"]
    assert "http://localhost:6841" not in captured["html"]
    assert "http://localhost:6842" not in captured["html"]


def test_accept_invitation_creates_user_and_grants_tenant_role_via_capability(monkeypatch, db_session):
    """accept_invitation had zero test coverage at any level before the
    auth-provider-seam wayfinder map's ticket 16 (which drained its last
    tenant_group_mapping.py usage). This exercises it end to end: directory
    user creation, tenant membership, and role grant all go through the real
    AuthProvider capability surface -- Keycloak-shaped HTTP mocked at the
    admin_client boundary, the same standard test_tenant_role_service.py
    already holds add_tenant_member to, rather than mocking add_tenant_member
    (the seam this ticket touched) away."""
    from m8flow_backend.integrations.auth import get_auth_provider as real_get_auth_provider
    from m8flow_backend.integrations.auth.keycloak.client_auth import reset_master_admin_token_cache
    from m8flow_backend.integrations.auth.keycloak.settings import reset_keycloak_settings

    _seed_tenant(db_session, tenant_id="org-1")
    monkeypatch.setattr(tenant_invitation_service, "send_email", lambda *a, **k: False)

    created = tenant_invitation_service.create_invitation(
        "org-1", "invitee@example.com", ["editor"], None, "admin"
    )
    raw_token = created["invitation_link"].split("token=")[1]

    # From here on, exercise the real Keycloak-shaped capability path -- the
    # module's autouse _fake_auth_provider fixture only covers the narrower
    # get_user/default_issuer needs of the create/resend tests above.
    monkeypatch.setattr(tenant_invitation_service, "get_auth_provider", real_get_auth_provider)
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak.internal")
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.keycloak.admin_client.fetch_master_admin_token",
        lambda: "admin-token",
    )
    reset_keycloak_settings()
    reset_master_admin_token_cache()

    realm_url = "http://keycloak.internal/admin/realms/m8flow"
    org_url = f"{realm_url}/organizations/org-1"
    groups_url = f"{org_url}/groups"
    members_url = f"{org_url}/members"
    users_url = f"{realm_url}/users"

    state = {"user_created": False, "member_added": False}

    def _invitee_repr():
        return {
            "id": "u-invitee",
            "username": "invitee@example.com",
            "email": "invitee@example.com",
            "firstName": "invitee@example.com",
            "lastName": "User",
        }

    def fake_get(url, params=None, headers=None, timeout=None):
        if url == org_url:
            return _FakeResponse({"id": "org-1", "alias": "org-1", "name": "Acme"})
        if url == f"{users_url}/u-invitee":
            return _FakeResponse(_invitee_repr())
        if url == users_url:
            return _FakeResponse([_invitee_repr()] if state["user_created"] else [])
        if url == members_url:
            return _FakeResponse([_invitee_repr()] if state["member_added"] else [])
        if url == f"{org_url}/members/u-invitee/groups" or url == groups_url:
            return _FakeResponse([{"id": "g-designers", "name": "Designers", "path": "/Designers"}])
        raise AssertionError(("GET", url, params))

    def fake_post(url, json=None, headers=None, timeout=None):
        if url == users_url:
            state["user_created"] = True
            return _FakeResponse({}, status_code=201, headers={"Location": f"{users_url}/u-invitee"})
        if url == members_url:
            state["member_added"] = True
            return _FakeResponse({}, status_code=204)
        raise AssertionError(("POST", url, json))

    put_urls: list[str] = []

    def fake_put(url, json=None, headers=None, timeout=None):
        put_urls.append(url)
        return _FakeResponse({}, status_code=204)

    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.get", fake_get)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.post", fake_post)
    monkeypatch.setattr("m8flow_backend.integrations.auth.keycloak.admin_client.requests.put", fake_put)

    result = tenant_invitation_service.accept_invitation(raw_token, "correct horse battery staple")

    assert result["email"] == "invitee@example.com"
    assert result["tenant_id"] == "org-1"
    assert result["roles"] == ["editor"]
    assert state["user_created"] is True
    assert state["member_added"] is True
    assert f"{groups_url}/g-designers/members/u-invitee" in put_urls

    row = db_session.query(M8flowTenantInvitationModel).filter_by(id=created["id"]).one()
    assert row.status == TenantInvitationStatus.ACCEPTED
