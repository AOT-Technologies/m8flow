"""Subclassable pytest suite asserting the ``AuthProvider`` *contract* --
never any one provider's internals. A reviewer should be able to read every
``test_*`` method below without knowing what a Keycloak realm is.

Built by the auth-provider-seam wayfinder map, ticket 02. Subclass
``AuthProviderConformance``, override the hooks in the first half of the
class body, and leave every ``test_*`` method untouched. Both
``InMemoryAuthProvider`` (``testing/fake.py``, via
``test_fake_conformance.py``) and ``KeycloakAuthProvider`` (via
``test_keycloak_conformance.py``) run the identical suite -- that's the
forcing function: an abstraction with one implementation has no way to
notice it's leaking, which is how the map's twelve original bypasses
accumulated unseen.

Where a provider's own shape genuinely can't exercise a clause (no
vendor-role-leaf translation to demonstrate, no network dependency capable
of being unavailable), its hook opts out with ``pytest.skip`` rather than
this file quietly weakening the assertion for every provider.
"""
from __future__ import annotations

import pytest

from m8flow_backend.integrations.auth.base.errors import CapabilityNotSupported, TokenInvalid, UserNotFound
from m8flow_backend.integrations.auth.base.models import IssuerRef, TenantRef
from m8flow_backend.integrations.auth.base.provider import AuthProvider

#: Every capability accessor AuthProvider exposes (auth-provider-seam
#: wayfinder map, ticket 13's split). A conforming provider either returns
#: something usable from each, or declines it with CapabilityNotSupported --
#: nothing else.
ALL_CAPABILITIES = ("user_admin", "tenant_admin", "group_admin", "role_admin", "directory_admin", "provisioning")

#: A username used throughout; conformance scenarios don't care about its
#: value, only that it's stable within one test.
_USERNAME = "conformance-user"


class AuthProviderConformance:
    """Override every method above the divider; leave every ``test_*``
    method below it alone -- those are the contract, not the harness."""

    #: Capability accessor names this provider declines (raises
    #: CapabilityNotSupported for). Empty by default -- a provider that
    #: supports everything (Keycloak) doesn't override this.
    declined_capabilities: frozenset[str] = frozenset()

    def build_provider(self) -> AuthProvider:
        """A fresh, ready-to-use provider instance, constructed with
        explicit settings (never bare env reads -- port surface decision 5)."""
        raise NotImplementedError

    def issuer(self) -> IssuerRef:
        """The issuer scenarios run against. Default: the provider's own
        default_issuer() -- override only if a provider's default issuer
        can't itself run the round trip."""
        return self.build_provider().default_issuer()

    def issue_authorization_code(self, *, username: str) -> str:
        """A one-time authorization code that ``exchange_code`` can redeem
        for ``username``, as if that user had just completed login at the
        real (or fake) IdP's hosted login page."""
        raise NotImplementedError

    def tampered_access_token(self, *, username: str) -> str:
        """A syntactically-plausible access token that must fail
        verification -- a bad signature for a real provider, an unrecognized
        opaque string for the fake. Either way, verify_token must reject it
        with TokenInvalid, never a vendor-specific exception."""
        raise NotImplementedError

    def expired_access_token(self, *, username: str) -> str:
        """A well-formed access token whose expiry has already passed."""
        raise NotImplementedError

    def wrong_issuer_access_token(self, *, username: str) -> str:
        """A well-formed, correctly-signed access token from an issuer this
        provider does not trust."""
        raise NotImplementedError

    def vendor_only_role_leaf(self) -> str | None:
        """A raw vendor role/group leaf name (e.g. Keycloak's
        "Administrators") this provider's claims-mapping code translates
        into a neutral role name -- or None if the provider has no such
        translation to demonstrate (the fake: it never ingests vendor-shaped
        role data in the first place, so there's nothing to mistranslate)."""
        return None

    def access_token_with_vendor_role_leaf(self, *, username: str, leaf: str) -> str:
        """An access token carrying ``leaf`` in whatever vendor-shaped claim
        this provider's claims-mapping code translates from. Only called
        when ``vendor_only_role_leaf`` returns non-None."""
        raise NotImplementedError

    def access_token_with_multiple_memberships(self, *, username: str, tenant_refs) -> str:
        """An access token for a user who belongs to every tenant in
        ``tenant_refs`` (each a ``TenantRef``), verifying to a
        ``VerifiedClaims.memberships`` entry per tenant."""
        raise NotImplementedError

    def trigger_provider_unavailable(self) -> None:
        """Exercise a codepath that should raise ProviderUnavailable, and
        assert it (e.g. ``with pytest.raises(ProviderUnavailable): ...``).
        Default: skip -- not every provider has a network dependency capable
        of being unavailable (the fake never does)."""
        pytest.skip("provider has no network dependency to simulate unavailability with")

    # ------------------------------------------------------------------
    # The contract. Do not override anything below this line.
    # ------------------------------------------------------------------

    def test_login_to_refresh_round_trip_uses_only_neutral_types(self):
        provider = self.build_provider()
        issuer = self.issuer()

        login_url = provider.build_login_url(redirect_uri="https://app.example/cb", state="s", issuer=issuer)
        assert isinstance(login_url, str) and login_url

        code = self.issue_authorization_code(username=_USERNAME)
        tokens = provider.exchange_code(code=code, redirect_uri="https://app.example/cb", issuer=issuer)
        assert tokens.access_token

        claims = provider.verify_token(tokens.access_token)
        assert claims.username == _USERNAME

        assert tokens.refresh_token, "exchange_code must return a refresh_token to continue the round trip"
        refreshed = provider.refresh(refresh_token=tokens.refresh_token, issuer=issuer)
        assert refreshed.access_token
        refreshed_claims = provider.verify_token(refreshed.access_token)
        assert refreshed_claims.username == _USERNAME

        logout_url = provider.build_logout_url(issuer=issuer, redirect_uri="https://app.example/")
        assert isinstance(logout_url, str) and logout_url

    def test_verify_token_rejects_bad_signature(self):
        provider = self.build_provider()
        token = self.tampered_access_token(username=_USERNAME)
        with pytest.raises(TokenInvalid):
            provider.verify_token(token)

    def test_verify_token_rejects_wrong_issuer(self):
        provider = self.build_provider()
        token = self.wrong_issuer_access_token(username=_USERNAME)
        with pytest.raises(TokenInvalid):
            provider.verify_token(token)

    def test_verify_token_rejects_expired_token(self):
        provider = self.build_provider()
        token = self.expired_access_token(username=_USERNAME)
        with pytest.raises(TokenInvalid):
            provider.verify_token(token)

    def test_get_user_raises_neutral_error_for_unknown_username(self):
        provider = self.build_provider()
        with pytest.raises(UserNotFound):
            provider.get_user(username="does-not-exist-anywhere", issuer=self.issuer())

    def test_provider_unavailable_is_neutral(self):
        self.trigger_provider_unavailable()

    def test_capability_accessors_match_declared_support(self):
        provider = self.build_provider()
        for name in ALL_CAPABILITIES:
            if name in self.declined_capabilities:
                with pytest.raises(CapabilityNotSupported):
                    getattr(provider, name)
            else:
                assert getattr(provider, name) is not None

    def test_verified_claims_never_carry_vendor_only_role_leaves(self):
        leaf = self.vendor_only_role_leaf()
        if leaf is None:
            pytest.skip("provider has no vendor role-leaf translation to verify")
        provider = self.build_provider()
        token = self.access_token_with_vendor_role_leaf(username=_USERNAME, leaf=leaf)
        claims = provider.verify_token(token)
        assert leaf not in claims.roles

    def test_set_active_tenant_then_refresh_reflects_the_new_tenant(self):
        provider = self.build_provider()
        issuer = self.issuer()
        code = self.issue_authorization_code(username=_USERNAME)
        tokens = provider.exchange_code(code=code, redirect_uri="https://app.example/cb", issuer=issuer)

        provider.set_active_tenant(username=_USERNAME, tenant_id="tenant-xyz")
        refreshed = provider.refresh(refresh_token=tokens.refresh_token, issuer=issuer)
        claims = provider.verify_token(refreshed.access_token)

        assert claims.active_tenant_ref is not None
        assert claims.active_tenant_ref.id == "tenant-xyz" or claims.active_tenant_ref.alias == "tenant-xyz"

    def test_verified_claims_memberships_carries_every_tenant(self):
        """auth-provider-seam wayfinder map, ticket 10: request-time tenant
        resolution (auth/bind.py, services/tenant_management_authorization.py)
        reads VerifiedClaims.memberships to know every tenant a request's
        session may touch -- a provider that only surfaces one membership,
        or drops the tenant id/alias, silently breaks that boundary check."""
        provider = self.build_provider()
        tenant_refs = [TenantRef(id="multi-a", alias="multi-a"), TenantRef(id="multi-b", alias="multi-b")]
        token = self.access_token_with_multiple_memberships(username=_USERNAME, tenant_refs=tenant_refs)
        claims = provider.verify_token(token)

        seen_ids = {membership.tenant_ref.id for membership in claims.memberships}
        seen_aliases = {membership.tenant_ref.alias for membership in claims.memberships}
        for ref in tenant_refs:
            assert ref.id in seen_ids
            assert ref.alias in seen_aliases
