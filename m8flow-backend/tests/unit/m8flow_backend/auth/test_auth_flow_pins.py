"""Characterization pins for the host-side auth flows (authProvider-analysis
redesign, Phase 0).

Recorded against the code *before* the flows moved behind
``integrations.auth.core.AuthService``. They pin, at the request/route level:

- when thin-token group enrichment consults the directory (and how often),
- what happens when the directory fails,
- master/platform-session detection in ``auth.bind``,
- the default-tenant fallback for a first request with no tenant cookie,
- the organization-memberships endpoint's token fallback.

Providers here are duck-typed on purpose: production call sites have always
accepted any object with the original port methods, and existing route tests
rely on that. Do not "fix" an expectation to make a refactor pass.
"""
from __future__ import annotations

import base64
import json

import pytest
from flask import g

from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user
from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.base.models import Membership, TenantRef, VerifiedClaims

_ISSUER = "https://example.test/realms/m8flow"


class _CountingDirectoryProvider:
    def __init__(self, memberships=None, *, error: Exception | None = None):
        self._memberships = list(memberships or [])
        self._error = error
        self.list_memberships_calls: list[str] = []

    def list_memberships(self, *, username: str):
        self.list_memberships_calls.append(username)
        if self._error is not None:
            raise self._error
        return list(self._memberships)

    def default_tenant_ref(self):
        return TenantRef(alias="m8flow", name="m8flow")


def _install(monkeypatch, provider):
    monkeypatch.setattr("m8flow_backend.integrations.auth.get_auth_provider", lambda: provider)


def _user(db_session, *, username: str, tenant_id: str = "t1"):
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(db_session, username=username, service=_ISSUER, service_id=f"{username}-sub")
    ensure_membership(db_session, user, tenant)
    db_session.flush()
    return user


def _identifiers(db_session, user) -> set[str]:
    db_session.expire(user, ["groups"])
    return {getattr(group, "identifier", "") for group in user.groups}


@pytest.fixture
def _no_yaml_import(monkeypatch):
    monkeypatch.setattr("m8flow_backend.identity.tenant_permission_seed_current", lambda *_a, **_k: True)
    # raising=False: the lifecycle-grant gate only exists once refactor/next-gen is merged in.
    monkeypatch.setattr(
        "m8flow_backend.identity.missing_lifecycle_execute_grants", lambda *_a, **_k: (), raising=False
    )
    monkeypatch.setattr(
        "m8flow_backend.workflow.reconcile_pending_tasks_for_user", lambda *_a, **_k: []
    )


def test_thin_active_membership_consults_directory_on_every_sync(app, db_session, monkeypatch, _no_yaml_import):
    """Pins finding A8: a token whose active membership has roles but no
    groups triggers a directory lookup on *every* sync (once per request in
    the middleware) -- no caching by default."""
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="editor")
    provider = _CountingDirectoryProvider(
        [Membership(tenant_ref=TenantRef(id="t1", alias="t1"), roles=["editor"], groups=["Designers"])]
    )
    _install(monkeypatch, provider)
    claims = VerifiedClaims(
        subject="editor-sub",
        issuer=_ISSUER,
        username="editor",
        memberships=[Membership(tenant_ref=TenantRef(id="t1"), roles=["editor"])],
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert provider.list_memberships_calls == ["editor", "editor"]
    assert "t1:editor" in _identifiers(db_session, user)


def test_membership_with_groups_does_not_consult_directory(app, db_session, monkeypatch, _no_yaml_import):
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="reviewer")
    provider = _CountingDirectoryProvider()
    _install(monkeypatch, provider)
    claims = VerifiedClaims(
        subject="reviewer-sub",
        issuer=_ISSUER,
        username="reviewer",
        memberships=[Membership(tenant_ref=TenantRef(id="t1"), roles=["reviewer"], groups=["Reviewers"])],
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert provider.list_memberships_calls == []
    assert "t1:reviewer" in _identifiers(db_session, user)


def test_no_token_memberships_skips_directory(app, db_session, monkeypatch, _no_yaml_import):
    """An empty membership list is *not* enriched (resolve's rule): only the
    top-level super-admin role can still sync."""
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="plain")
    provider = _CountingDirectoryProvider([Membership(tenant_ref=TenantRef(id="t1"), roles=["editor"])])
    _install(monkeypatch, provider)
    claims = VerifiedClaims(subject="plain-sub", issuer=_ISSUER, username="plain", memberships=[])
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert provider.list_memberships_calls == []
    assert "t1:editor" not in _identifiers(db_session, user)


def test_token_for_other_tenant_is_enriched_from_directory(app, db_session, monkeypatch, _no_yaml_import):
    """The AGENTS.md multi-org case: token names org A, cookie selects org B
    -> the directory supplies B's groups."""
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="multi", tenant_id="t2")
    provider = _CountingDirectoryProvider(
        [
            Membership(tenant_ref=TenantRef(id="t1", alias="t1"), roles=["reviewer"], groups=["Reviewers"]),
            Membership(tenant_ref=TenantRef(id="t2", alias="t2"), roles=["editor"], groups=["Designers"]),
        ]
    )
    _install(monkeypatch, provider)
    claims = VerifiedClaims(
        subject="multi-sub",
        issuer=_ISSUER,
        username="multi",
        memberships=[Membership(tenant_ref=TenantRef(id="t1"), roles=["reviewer"], groups=["Reviewers"])],
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t2")

    assert provider.list_memberships_calls == ["multi"]
    identifiers = _identifiers(db_session, user)
    assert "t2:editor" in identifiers
    assert "t2:reviewer" not in identifiers


def test_directory_failure_falls_back_to_token_membership(app, db_session, monkeypatch, _no_yaml_import):
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="degraded")
    provider = _CountingDirectoryProvider(error=ProviderUnavailable("down"))
    _install(monkeypatch, provider)
    claims = VerifiedClaims(
        subject="degraded-sub",
        issuer=_ISSUER,
        username="degraded",
        memberships=[Membership(tenant_ref=TenantRef(id="t1"), roles=["editor"])],
    )
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert provider.list_memberships_calls == ["degraded"]
    assert "t1:editor" in _identifiers(db_session, user)


def test_top_level_super_admin_role_syncs_without_membership(app, db_session, monkeypatch, _no_yaml_import):
    from m8flow_backend.auth import sync_groups_from_token

    user = _user(db_session, username="root")
    _install(monkeypatch, _CountingDirectoryProvider())
    claims = VerifiedClaims(subject="root-sub", issuer=_ISSUER, username="root", roles=["super-admin"])
    with app.test_request_context("/v1.0/onboarding"):
        g.verified_claims = claims
        sync_groups_from_token(db_session, user=user, decoded={}, tenant_id="t1")

    assert "super-admin" in _identifiers(db_session, user)


# --- master/platform session detection (auth.bind) -------------------------


class _MasterProvider:
    def __init__(self):
        self.seen: list[VerifiedClaims] = []

    def is_master_issuer(self, claims: VerifiedClaims) -> bool:
        self.seen.append(claims)
        return claims.issuer.endswith("/realms/master")


def test_master_detection_uses_verified_claims_when_present(app, monkeypatch):
    from m8flow_backend.auth.bind import _request_uses_master_realm_without_tenant_context

    provider = _MasterProvider()
    _install(monkeypatch, provider)
    claims = VerifiedClaims(subject="s", issuer="http://kc/realms/master")
    with app.test_request_context("/v1.0/onboarding"):
        g.decoded_token = {"iss": "http://kc/realms/m8flow"}
        g.verified_claims = claims
        assert _request_uses_master_realm_without_tenant_context() is True
    assert provider.seen == [claims]


def test_master_detection_wraps_raw_payload_for_local_tokens(app, monkeypatch):
    from m8flow_backend.auth.bind import _request_uses_master_realm_without_tenant_context

    provider = _MasterProvider()
    _install(monkeypatch, provider)
    with app.test_request_context("/v1.0/onboarding"):
        g.decoded_token = {"sub": "local-sub", "iss": "http://kc/realms/master"}
        assert _request_uses_master_realm_without_tenant_context() is True
    assert provider.seen[0].issuer == "http://kc/realms/master"
    assert provider.seen[0].subject == "local-sub"
    assert provider.seen[0].jwt_claims == {"sub": "local-sub", "iss": "http://kc/realms/master"}


def test_master_detection_false_without_any_token(app, monkeypatch):
    from m8flow_backend.auth.bind import _request_uses_master_realm_without_tenant_context

    provider = _MasterProvider()
    _install(monkeypatch, provider)
    with app.test_request_context("/v1.0/onboarding"):
        assert _request_uses_master_realm_without_tenant_context() is False
    assert provider.seen == []


# --- middleware: first request with no tenant cookie ------------------------


def _unsigned_rs256_shaped_token() -> str:
    def _b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{_b64({'alg': 'RS256', 'typ': 'JWT'})}.{_b64({})}.sig"


class _NewcomerProvider(_CountingDirectoryProvider):
    def verify_token(self, token: str) -> VerifiedClaims:
        del token
        return VerifiedClaims(
            subject="newcomer-sub",
            issuer=_ISSUER,
            username="newcomer",
            email="newcomer@example.test",
            jwt_claims={"sub": "newcomer-sub", "iss": _ISSUER},
        )


class _NewcomerProviderCountingDefault(_NewcomerProvider):
    def __init__(self):
        super().__init__()
        self.default_tenant_ref_calls = 0

    def default_tenant_ref(self):
        self.default_tenant_ref_calls += 1
        return super().default_tenant_ref()


def _record_middleware_writes(monkeypatch):
    """Capture what the auth middleware decides (which identity, which
    tenant) at the provisioning/sync seam, independent of whether the
    request later fails tenant binding and rolls the transaction back."""
    calls: dict[str, list] = {"provision": [], "sync": []}

    def _provision(session, **kwargs):
        calls["provision"].append(kwargs)
        from m8flow_backend import identity

        return identity.ensure_user(
            session,
            username=kwargs["username"],
            service=kwargs["service"],
            service_id=kwargs["service_id"],
            email=kwargs["email"],
        )

    monkeypatch.setattr("m8flow_backend.auth.on_login_or_token_enrichment", _provision)
    monkeypatch.setattr(
        "m8flow_backend.auth.sync_groups_from_token",
        lambda session, *, user, decoded, tenant_id: calls["sync"].append(tenant_id),
    )
    return calls


def test_first_request_without_cookie_provisions_into_default_tenant(client, monkeypatch):
    provider = _NewcomerProviderCountingDefault()
    _install(monkeypatch, provider)
    calls = _record_middleware_writes(monkeypatch)
    client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {_unsigned_rs256_shaped_token()}"})

    assert provider.default_tenant_ref_calls == 1
    assert calls["provision"] == [
        {
            "username": "newcomer",
            "service": _ISSUER,
            "service_id": "newcomer-sub",
            "email": "newcomer@example.test",
            "active_tenant_id": "m8flow",
        }
    ]
    assert calls["sync"] == ["m8flow"]


def test_first_request_with_cookie_provisions_into_cookie_tenant(client, monkeypatch):
    provider = _NewcomerProviderCountingDefault()
    _install(monkeypatch, provider)
    calls = _record_middleware_writes(monkeypatch)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t9")
    client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {_unsigned_rs256_shaped_token()}"})

    assert provider.default_tenant_ref_calls == 0
    assert [call["active_tenant_id"] for call in calls["provision"]] == ["t9"]
    assert calls["sync"] == ["t9"]


def test_known_user_request_syncs_against_default_tenant_without_cookie(client, db_session, monkeypatch):
    """A local (HS256) token resolves the user directly; group sync still
    runs against cookie -> context -> provider default tenant."""
    from m8flow_backend.auth import encode_auth_token

    user = _user(db_session, username="known")
    db_session.commit()
    provider = _NewcomerProviderCountingDefault()
    _install(monkeypatch, provider)
    calls = _record_middleware_writes(monkeypatch)
    client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {encode_auth_token(user=user)}"})

    assert calls["provision"] == []
    assert calls["sync"] == ["m8flow"]
    assert provider.default_tenant_ref_calls == 1


def test_protected_route_without_cookie_fails_closed_for_new_user(client, monkeypatch):
    _install(monkeypatch, _NewcomerProvider())
    response = client.get("/v1.0/onboarding", headers={"Authorization": f"Bearer {_unsigned_rs256_shaped_token()}"})
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "tenant_required"


# --- organization-memberships endpoint --------------------------------------


class _UsernamelessProvider:
    def __init__(self):
        self.list_memberships_calls = 0

    def verify_token(self, token: str) -> VerifiedClaims:
        del token
        return VerifiedClaims(
            subject="svc",
            issuer=_ISSUER,
            username=None,
            memberships=[Membership(tenant_ref=TenantRef(id="t1", alias="m8flow", name="M8"))],
        )

    def list_memberships(self, *, username: str):
        self.list_memberships_calls += 1
        return []


def test_memberships_endpoint_falls_back_to_token_without_username(client, monkeypatch):
    provider = _UsernamelessProvider()
    monkeypatch.setattr("m8flow_backend.routes.keycloak_controller.get_auth_provider", lambda: provider)
    client.set_cookie("access_token", "service-token")
    response = client.get("/v1.0/m8flow/organization-memberships")
    assert response.status_code == 200
    assert response.get_json() == {"organizations": [{"alias": "m8flow", "id": "t1", "name": "M8"}]}
    assert provider.list_memberships_calls == 0


def test_memberships_endpoint_requires_a_token(client):
    response = client.get("/v1.0/m8flow/organization-memberships")
    assert response.status_code == 401
