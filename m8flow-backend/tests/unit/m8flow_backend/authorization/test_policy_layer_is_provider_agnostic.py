"""Regression test for the auth-provider-seam wayfinder map's locked decision
2 and ticket 11 ("Pin the policy layer's provider-agnosticism"): authorization
decisions must derive ONLY from ``VerifiedClaims`` + DB state, never a raw
token payload or a Keycloak import.

If you are about to add a ``decoded_token``/``jwt_claims`` read, or an
``integrations.auth.keycloak`` import, to anything under ``authorization/``
-- stop. The provider supplies authorization *facts* (subject, roles, tenant
memberships); it never becomes the decision engine, and m8flow's own
permission model (``permission_*`` tables, ``m8flow.yml``) must not vary by
IdP. This file is what makes that boundary durable instead of accidental.
"""
from __future__ import annotations

from pathlib import Path

from flask import g

from m8flow_backend.authorization import (
    actor_is_super_admin,
    allow_uri,
    require_authorized_user,
    user_has_permission,
)
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.integrations.auth.base.models import VerifiedClaims
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE
from m8flow_backend.integrations.auth.testing.fake import FakeAuthSettings, InMemoryAuthProvider

_SERVICE = "https://example.test/realms/m8flow"
_MASTER_SERVICE = "https://example.test/realms/master"


def _assert_no_raw_payload_present() -> None:
    """The property under test: no raw token dict anywhere on `g`, for any
    of the names the pre-ticket-10 code used to read."""
    assert getattr(g, "decoded_token", None) is None
    assert getattr(g, "_m8flow_decoded_token", None) is None


def test_super_admin_resolves_from_verified_claims_role_alone(app, db_session):
    """Before local group sync has persisted "super-admin" (the just-logged-
    in case): a verified JWT role claim bound to this specific user is
    enough on its own -- no DB group needed."""
    user = ensure_user(db_session, username="root", service=_MASTER_SERVICE, service_id="root-1")
    db_session.commit()
    assert not any(getattr(group, "identifier", None) == SUPER_ADMIN_ROLE for group in user.groups)

    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = VerifiedClaims(subject="root-1", issuer=_MASTER_SERVICE, roles=[SUPER_ADMIN_ROLE])
        _assert_no_raw_payload_present()
        assert actor_is_super_admin(user) is True


def test_super_admin_resolves_from_db_group_alone(app, db_session):
    """No verified_claims at all (request context has none) -- the
    persisted "super-admin" group is enough on its own."""
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(db_session, username="root2", service=_SERVICE, service_id="root2")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["super-admin"], tenant_id="t1")
    db_session.commit()

    with app.test_request_context("/v1.0/onboarding"):
        assert getattr(g, "verified_claims", None) is None
        _assert_no_raw_payload_present()
        assert actor_is_super_admin(user) is True


def test_policy_decisions_work_with_verified_claims_and_no_raw_payload(app, db_session):
    """allow_uri / user_has_permission / require_authorized_user /
    actor_is_super_admin all produce the correct decision from
    g.verified_claims alone, with no g.decoded_token / g._m8flow_decoded_token
    present anywhere in the request."""
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(db_session, username="editor", service=_SERVICE, service_id="editor")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["t1:editor"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.refresh(user)

    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = VerifiedClaims(subject="editor", issuer=_SERVICE, username="editor")
        g.db_session = db_session
        g.user = user
        _assert_no_raw_payload_present()

        assert allow_uri(user, "GET", "/v1.0/onboarding", session=db_session) is True
        assert user_has_permission(user, "read", "/v1.0/onboarding", session=db_session) is True
        assert actor_is_super_admin(user) is False
        assert require_authorized_user("GET", forbidden_message="nope", path="/v1.0/onboarding") is user


def test_fake_provider_verified_claims_drive_identical_policy_decisions(app, db_session):
    """The same neutral VerifiedClaims shape must yield the same policy
    decision no matter which AuthProvider produced it. Driving this end-to-
    end from the ticket-02 conformance fake (InMemoryAuthProvider) both
    proves the boundary and proves the fake's VerifiedClaims are realistic
    enough to exercise the real policy layer, not just the conformance
    suite it was built for."""
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(db_session, username="fake-editor", service="fake", service_id="fake-editor-1")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=["t1:editor"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.refresh(user)

    provider = InMemoryAuthProvider(FakeAuthSettings())
    provider.register_user(username="fake-editor", subject="fake-editor-1")
    code = provider.issue_authorization_code(username="fake-editor")
    tokens = provider.exchange_code(
        code=code, redirect_uri="https://app.example/cb", issuer=provider.default_issuer()
    )
    claims = provider.verify_token(tokens.access_token)
    assert claims.subject == "fake-editor-1"  # sanity: this is a real fake-provider VerifiedClaims

    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        g.db_session = db_session
        _assert_no_raw_payload_present()
        assert allow_uri(user, "GET", "/v1.0/onboarding", session=db_session) is True


def test_authorization_package_never_imports_keycloak_or_reads_raw_payload():
    """Structural guard, cheap and immediate -- catches what ruff's TID251
    won't (authorization/ has never been on its allowlist, so TID251 already
    bans a Keycloak import here; this additionally pins the raw-payload-read
    half, which no import rule can catch)."""
    import m8flow_backend.authorization as pkg

    package_dir = Path(pkg.__file__).parent
    banned_import = "integrations.auth.keycloak"
    banned_reads = ("decoded_token", "_m8flow_decoded_token", "jwt_claims")
    checked = 0
    for path in sorted(package_dir.glob("*.py")):
        source = path.read_text()
        checked += 1
        assert banned_import not in source, f"{path} imports a Keycloak adapter internal"
        for needle in banned_reads:
            assert needle not in source, f"{path} reads a raw token payload ({needle!r})"
    assert checked >= 2, "expected to scan __init__.py and decorators.py at least"
