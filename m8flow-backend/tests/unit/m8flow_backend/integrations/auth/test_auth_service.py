"""Unit tests for ``integrations.auth.core.AuthService`` -- the orchestrator
that owns the auth flows on top of any provider (authProvider-analysis
redesign). Equivalence with the pre-refactor host flows is pinned separately
in ``tests/unit/m8flow_backend/auth/test_auth_flow_pins.py``.
"""
from __future__ import annotations

import pytest

from m8flow_backend.integrations.auth.base.errors import CapabilityNotSupported, ProviderUnavailable, TokenInvalid
from m8flow_backend.integrations.auth.base.models import (
    IssuerRef,
    Membership,
    TenantRef,
    TokenSet,
    TrustDomain,
    VerifiedClaims,
)
from m8flow_backend.integrations.auth.core import AuthService, SwitchMode
from m8flow_backend.integrations.auth.core.cache import MEMBERSHIP_CACHE_TTL_ENV, MembershipCache, membership_cache
from m8flow_backend.integrations.auth.testing.fake import FakeAuthSettings, InMemoryAuthProvider


@pytest.fixture(autouse=True)
def _fresh_cache():
    membership_cache.invalidate()
    yield
    membership_cache.invalidate()


class _LegacyProvider:
    """Only the pre-redesign port methods -- like the duck-typed doubles the
    route tests use. AuthService must behave exactly as the old host code."""

    def __init__(self, *, refresh_result=None, refresh_error=None, memberships=None, master=False):
        self.refresh_result = refresh_result
        self.refresh_error = refresh_error
        self.memberships = list(memberships or [])
        self.master = master
        self.calls: list[tuple] = []

    def set_active_tenant(self, *, username, tenant_id):
        self.calls.append(("set_active_tenant", username, tenant_id))

    def clear_active_tenant(self, *, username):
        self.calls.append(("clear_active_tenant", username))

    def refresh(self, *, refresh_token, issuer):
        self.calls.append(("refresh", refresh_token, issuer.value))
        if self.refresh_error is not None:
            raise self.refresh_error
        return self.refresh_result

    def list_memberships(self, *, username):
        self.calls.append(("list_memberships", username))
        return list(self.memberships)

    def is_master_issuer(self, claims):
        return self.master


_ISSUER = "https://idp.example/realms/m8flow"


def _claims(**overrides) -> VerifiedClaims:
    values = {"subject": "s", "issuer": _ISSUER, "username": "editor"}
    values.update(overrides)
    return VerifiedClaims(**values)


# --- switch -----------------------------------------------------------------


def test_switch_defaults_to_remint_for_legacy_providers():
    tokens = TokenSet(access_token="new")
    provider = _LegacyProvider(refresh_result=tokens)
    outcome = AuthService(provider).switch_tenant(
        username="editor", tenant_id="t2", refresh_token="rt", issuer=IssuerRef(value="m8flow")
    )
    assert outcome.mode is SwitchMode.REMINT
    assert outcome.tokens is tokens and outcome.reminted
    assert provider.calls == [("set_active_tenant", "editor", "t2"), ("refresh", "rt", "m8flow")]


def test_switch_without_refresh_token_never_touches_the_provider():
    provider = _LegacyProvider(refresh_result=TokenSet(access_token="x"))
    outcome = AuthService(provider).switch_tenant(
        username="editor", tenant_id="t2", refresh_token=None, issuer=IssuerRef(value="m8flow")
    )
    assert outcome.tokens is None
    assert provider.calls == []


@pytest.mark.parametrize("error", [ProviderUnavailable("down"), TokenInvalid("bad"), CapabilityNotSupported("x")])
def test_switch_degrades_to_cookie_only_on_provider_errors(error, caplog):
    provider = _LegacyProvider(refresh_error=error)
    outcome = AuthService(provider).switch_tenant(
        username="editor", tenant_id="t2", refresh_token="rt", issuer=IssuerRef(value="m8flow")
    )
    assert outcome.tokens is None
    assert "active-tenant re-mint failed" in caplog.text


def test_switch_does_not_swallow_unexpected_errors():
    provider = _LegacyProvider(refresh_error=RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        AuthService(provider).switch_tenant(
            username="editor", tenant_id="t2", refresh_token="rt", issuer=IssuerRef(value="m8flow")
        )


def test_cookie_only_providers_skip_the_remint():
    provider = _LegacyProvider(refresh_result=TokenSet(access_token="x"))
    provider.switch_mode = SwitchMode.COOKIE_ONLY
    outcome = AuthService(provider).switch_tenant(
        username="editor", tenant_id="t2", refresh_token="rt", issuer=IssuerRef(value="m8flow")
    )
    assert outcome.mode is SwitchMode.COOKIE_ONLY and outcome.tokens is None
    assert provider.calls == []


@pytest.mark.parametrize("mode", [SwitchMode.REAUTHORIZE, SwitchMode.REAUTHENTICATE])
def test_redirect_switch_modes_fail_loudly_until_wired(mode):
    provider = _LegacyProvider()
    provider.switch_mode = mode
    with pytest.raises(CapabilityNotSupported):
        AuthService(provider).switch_tenant(
            username="editor", tenant_id="t2", refresh_token="rt", issuer=IssuerRef(value="m8flow")
        )


def test_switch_reflects_new_tenant_on_the_reference_fake():
    provider = InMemoryAuthProvider(FakeAuthSettings())
    tokens = provider.exchange_code(
        code=provider.issue_authorization_code(username="editor"),
        redirect_uri="https://app/cb",
        issuer=provider.default_issuer(),
    )
    outcome = AuthService(provider).switch_tenant(
        username="editor", tenant_id="tenant-b", refresh_token=tokens.refresh_token, issuer=provider.default_issuer()
    )
    assert outcome.tokens is not None
    assert provider.verify_token(outcome.tokens.access_token).active_tenant_ref.id == "tenant-b"


def test_end_session_clears_active_tenant():
    provider = _LegacyProvider()
    AuthService(provider).end_session(username="editor")
    assert provider.calls == [("clear_active_tenant", "editor")]


def test_end_session_is_a_noop_for_cookie_only_providers():
    provider = _LegacyProvider()
    provider.switch_mode = SwitchMode.COOKIE_ONLY
    AuthService(provider).end_session(username="editor")
    assert provider.calls == []


# --- trust domain -----------------------------------------------------------


def test_trust_domain_prefers_the_value_stamped_at_verification():
    service = AuthService(_LegacyProvider(master=True))
    assert service.trust_domain(_claims(trust_domain=TrustDomain.TENANT)) is TrustDomain.TENANT


def test_trust_domain_falls_back_to_is_master_issuer_for_legacy_providers():
    assert AuthService(_LegacyProvider(master=True)).is_platform_session(_claims()) is True
    assert AuthService(_LegacyProvider(master=False)).trust_domain(_claims()) is TrustDomain.SHARED


def test_trust_domain_uses_the_provider_classifier_when_present():
    provider = _LegacyProvider(master=True)
    provider.trust_domain = lambda claims: TrustDomain.TENANT
    assert AuthService(provider).trust_domain(_claims()) is TrustDomain.TENANT


def test_base_provider_default_trust_domain_follows_is_master_issuer():
    provider = InMemoryAuthProvider(FakeAuthSettings())
    assert provider.trust_domain(_claims()) is TrustDomain.SHARED
    assert provider.switch_mode is SwitchMode.REMINT


# --- memberships ------------------------------------------------------------


def test_switcher_uses_directory_when_token_is_not_complete():
    directory = [Membership(tenant_ref=TenantRef(id="t1")), Membership(tenant_ref=TenantRef(id="t2"))]
    provider = _LegacyProvider(memberships=directory)
    claims = _claims(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    assert AuthService(provider).memberships_for_switcher(claims) == directory


def test_switcher_trusts_a_token_that_declares_itself_complete():
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="other"))])
    token_memberships = [Membership(tenant_ref=TenantRef(id="t1"))]
    claims = _claims(memberships=token_memberships, memberships_complete=True)
    assert AuthService(provider).memberships_for_switcher(claims) == token_memberships
    assert provider.calls == []


def test_switcher_falls_back_to_token_without_username():
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="other"))])
    token_memberships = [Membership(tenant_ref=TenantRef(id="t1"))]
    claims = _claims(username=None, memberships=token_memberships)
    assert AuthService(provider).memberships_for_switcher(claims) == token_memberships


def test_switcher_propagates_directory_errors():
    class _Down(_LegacyProvider):
        def list_memberships(self, *, username):
            raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        AuthService(_Down()).memberships_for_switcher(_claims())


def test_best_effort_lookup_returns_empty_on_failure_and_blank_usernames(caplog):
    class _Down(_LegacyProvider):
        def list_memberships(self, *, username):
            raise ProviderUnavailable("down")

    assert AuthService(_Down()).directory_memberships_best_effort("editor") == []
    assert "directory membership enrichment failed" in caplog.text
    assert AuthService(_LegacyProvider()).directory_memberships_best_effort("  ") == []
    assert AuthService(_LegacyProvider()).directory_memberships_best_effort(None) == []


@pytest.mark.parametrize("username", [None, "", "   ", 42])
def test_directory_lookup_of_an_invalid_username_is_empty_and_skips_the_provider(username):
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    assert AuthService(provider).directory_memberships(username) == []
    assert provider.calls == []


def test_directory_lookups_are_uncached_by_default(monkeypatch):
    monkeypatch.delenv(MEMBERSHIP_CACHE_TTL_ENV, raising=False)
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor")
    service.directory_memberships("editor")
    assert provider.calls.count(("list_memberships", "editor")) == 2


def test_opt_in_cache_serves_repeat_lookups_and_invalidates(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor", issuer=_ISSUER)
    service.directory_memberships("editor", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 1
    service.invalidate("editor")
    service.directory_memberships("editor", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 2


def test_invalidate_clears_only_that_user(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor", issuer=_ISSUER)
    service.directory_memberships("reviewer", issuer=_ISSUER)
    service.invalidate("editor")
    service.directory_memberships("editor", issuer=_ISSUER)
    service.directory_memberships("reviewer", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 2
    assert provider.calls.count(("list_memberships", "reviewer")) == 1


def test_finalization_and_switch_bypass_the_cache(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))], refresh_result=None)
    service = AuthService(provider)
    service.directory_memberships("editor", issuer=_ISSUER)
    service.directory_memberships_best_effort("editor")
    assert provider.calls.count(("list_memberships", "editor")) == 2
    # A switch invalidates the user's cached memberships.
    service.switch_tenant(username="editor", tenant_id="t2", refresh_token=None, issuer=IssuerRef(value="m8flow"))
    service.directory_memberships("editor", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 3


def test_cache_is_isolated_per_issuer(monkeypatch):
    """Realm-per-tenant: the same username in two directories must never be
    served the other directory's memberships from the process-wide cache."""
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")

    class _PerRealm(_LegacyProvider):
        realm = "a"

        def list_memberships(self, *, username):
            self.calls.append(("list_memberships", username))
            return [Membership(tenant_ref=TenantRef(id=f"{self.realm}-tenant"))]

    provider = _PerRealm()
    service = AuthService(provider)
    realm_a = service.directory_memberships("editor", issuer="https://idp.example/realms/a")
    provider.realm = "b"
    realm_b = service.directory_memberships("editor", issuer="https://idp.example/realms/b")
    assert realm_a[0].tenant_ref.id == "a-tenant"
    assert realm_b[0].tenant_ref.id == "b-tenant"
    assert service.directory_memberships("editor", issuer="https://idp.example/realms/a")[0].tenant_ref.id == "a-tenant"
    assert provider.calls.count(("list_memberships", "editor")) == 2


def test_cache_is_bypassed_without_an_issuer(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")

    class _UntouchableCache:
        def get_or_load(self, *_args, **_kwargs):
            raise AssertionError("a lookup without a cache scope must not reach the cache")

    monkeypatch.setattr("m8flow_backend.integrations.auth.core.service.membership_cache", _UntouchableCache())
    provider = _LegacyProvider(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor")
    service.directory_memberships("editor", issuer="  ")
    service.directory_memberships("editor", issuer=_ISSUER, use_cache=False)
    assert provider.calls.count(("list_memberships", "editor")) == 3


def test_provider_supplied_cache_scope_wins(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")

    class _OneDirectory(_LegacyProvider):
        def membership_cache_scope(self, issuer):
            return "shared-directory"

    class _Uncacheable(_LegacyProvider):
        def membership_cache_scope(self, issuer):
            return None

    one = _OneDirectory(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    AuthService(one).directory_memberships("editor", issuer="https://idp.example/realms/a")
    AuthService(one).directory_memberships("editor", issuer="https://idp.example/realms/b")
    assert one.calls.count(("list_memberships", "editor")) == 1

    membership_cache.invalidate()
    never = _Uncacheable(memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    AuthService(never).directory_memberships("editor", issuer=_ISSUER)
    AuthService(never).directory_memberships("editor", issuer=_ISSUER)
    assert never.calls.count(("list_memberships", "editor")) == 2


def test_invalidate_clears_the_user_in_every_scope():
    cache = MembershipCache()
    cache.get_or_load("a", "editor", lambda: [], ttl=30)
    cache.get_or_load("b", "editor", lambda: [], ttl=30)
    cache.get_or_load("a", "reviewer", lambda: [], ttl=30)
    cache.invalidate("editor")
    assert set(cache._entries) == {("a", "reviewer")}


def test_cache_drops_a_load_that_raced_an_invalidate():
    cache = MembershipCache()
    stale = [Membership(tenant_ref=TenantRef(id="old"))]
    fresh = [Membership(tenant_ref=TenantRef(id="new"))]

    def _loader_racing_invalidate():
        cache.invalidate("u")  # e.g. switch_tenant lands while the load is in flight
        return stale

    assert cache.get_or_load("realm", "u", _loader_racing_invalidate, ttl=30) == stale
    assert cache.get_or_load("realm", "u", lambda: fresh, ttl=30) == fresh


def test_cache_prunes_expired_entries_on_write():
    now = [0.0]
    cache = MembershipCache(clock=lambda: now[0])
    cache.get_or_load("realm", "a", lambda: [], ttl=10)
    now[0] = 11
    cache.get_or_load("realm", "b", lambda: [], ttl=10)
    assert set(cache._entries) == {("realm", "b")}


def test_cache_expires_and_never_caches_errors():
    now = [0.0]
    cache = MembershipCache(clock=lambda: now[0])
    loads: list[int] = []

    def _loader():
        loads.append(1)
        return [Membership(tenant_ref=TenantRef(id="t1"))]

    cache.get_or_load("realm", "u", _loader, ttl=10)
    cache.get_or_load("realm", "u", _loader, ttl=10)
    now[0] = 11
    cache.get_or_load("realm", "u", _loader, ttl=10)
    assert len(loads) == 2

    def _failing():
        raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        cache.get_or_load("realm", "v", _failing, ttl=10)
    assert cache.get_or_load("realm", "v", _loader, ttl=10)[0].tenant_ref.id == "t1"


@pytest.mark.parametrize(("raw", "expected"), [("", 0.0), ("abc", 0.0), ("-5", 0.0), ("45", 45.0), ("9999", 60.0)])
def test_cache_ttl_parsing(monkeypatch, raw, expected):
    from m8flow_backend.integrations.auth.core.cache import membership_cache_ttl_seconds

    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, raw)
    assert membership_cache_ttl_seconds() == expected


# --- capabilities / session view -------------------------------------------


def test_capabilities_reflect_accessors():
    fake = AuthService(InMemoryAuthProvider(FakeAuthSettings())).capabilities()
    assert fake == {name: False for name in fake} and len(fake) == 6
    assert AuthService(_LegacyProvider()).capabilities()["directory_admin"] is False


def test_capability_object_not_implementing_its_interface_is_unsupported():
    class _StubAdminProvider(_LegacyProvider):
        directory_admin = object()
        provisioning = None

    capabilities = AuthService(_StubAdminProvider()).capabilities()
    assert capabilities["directory_admin"] is False
    assert capabilities["provisioning"] is False


def test_session_view_is_provider_neutral():
    provider = _LegacyProvider(master=False)
    claims = _claims(email="e@x", active_tenant_ref=TenantRef(id="t1", alias="acme", name="Acme"))
    view = AuthService(provider).session_view(claims, selected_tenant="t1")
    assert view == {
        "subject": "s",
        "username": "editor",
        "email": "e@x",
        "trust_domain": "shared",
        "is_platform_session": False,
        "selected_tenant": "t1",
        "token_active_tenant": {"id": "t1", "alias": "acme", "name": "Acme"},
        "switch_mode": "remint",
        "capabilities": AuthService(provider).capabilities(),
    }


# --- host membership writes invalidate the cache ---------------------------


class _FakeAdmin:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def add_member(self, *, username, tenant_ref):
        if self.fail:
            raise ProviderUnavailable("down")

    def set_group_roles(self, group, *, roles):
        pass

    def get_tenant(self, tenant_ref):
        return tenant_ref


class _AdminProvider(_LegacyProvider):
    def __init__(self, admin, **kwargs):
        super().__init__(**kwargs)
        self.directory_admin = admin


def _cache_two_users(service):
    service.directory_memberships("editor", issuer=_ISSUER)
    service.directory_memberships("reviewer", issuer=_ISSUER)


def test_user_scoped_write_invalidates_only_that_user(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _AdminProvider(_FakeAdmin(), memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    _cache_two_users(service)
    service.directory_admin.add_member(username="editor", tenant_ref=TenantRef(id="t1"))
    _cache_two_users(service)
    assert provider.calls.count(("list_memberships", "editor")) == 2
    assert provider.calls.count(("list_memberships", "reviewer")) == 1


def test_group_wide_write_invalidates_everyone(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _AdminProvider(_FakeAdmin(), memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    _cache_two_users(service)
    service.directory_admin.set_group_roles(object(), roles=["editor"])
    _cache_two_users(service)
    assert provider.calls.count(("list_memberships", "editor")) == 2
    assert provider.calls.count(("list_memberships", "reviewer")) == 2


def test_failed_write_still_invalidates(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _AdminProvider(_FakeAdmin(fail=True), memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor", issuer=_ISSUER)
    with pytest.raises(ProviderUnavailable):
        service.directory_admin.add_member(username="editor", tenant_ref=TenantRef(id="t1"))
    service.directory_memberships("editor", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 2


def test_reads_through_directory_admin_do_not_invalidate(monkeypatch):
    monkeypatch.setenv(MEMBERSHIP_CACHE_TTL_ENV, "30")
    provider = _AdminProvider(_FakeAdmin(), memberships=[Membership(tenant_ref=TenantRef(id="t1"))])
    service = AuthService(provider)
    service.directory_memberships("editor", issuer=_ISSUER)
    assert service.directory_admin.get_tenant(TenantRef(id="t1")) == TenantRef(id="t1")
    service.directory_memberships("editor", issuer=_ISSUER)
    assert provider.calls.count(("list_memberships", "editor")) == 1
