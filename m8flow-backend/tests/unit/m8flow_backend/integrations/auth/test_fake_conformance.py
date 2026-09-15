"""InMemoryAuthProvider runs the AuthProvider conformance suite (auth-provider-
seam wayfinder map, ticket 02). See ``testing/conformance.py`` for the
contract itself and ``test_keycloak_conformance.py`` for the second
implementation running the identical suite.
"""
from __future__ import annotations

from m8flow_backend.integrations.auth.base.models import IssuerRef, Membership
from m8flow_backend.integrations.auth.base.provider import AuthProvider
from m8flow_backend.integrations.auth.testing.conformance import AuthProviderConformance
from m8flow_backend.integrations.auth.testing.fake import FakeAuthSettings, InMemoryAuthProvider


class TestInMemoryAuthProviderConformance(AuthProviderConformance):
    # The fake declines every directory-admin/provisioning capability --
    # its job is proving the session/verify/read seam is provider-agnostic,
    # not duplicating an Admin API in memory. See testing/fake.py's
    # docstring.
    declined_capabilities = frozenset(
        {"user_admin", "tenant_admin", "group_admin", "role_admin", "directory_admin", "provisioning"}
    )

    def build_provider(self) -> AuthProvider:
        # Memoized per test-method instance (pytest instantiates a fresh
        # TestInMemoryAuthProviderConformance per test): several hooks below
        # need to act on the *same* in-memory state the test's own
        # build_provider() call is exercising (e.g. issue_authorization_code
        # must register a code the same instance's exchange_code can redeem).
        provider = getattr(self, "_provider", None)
        if provider is None:
            provider = InMemoryAuthProvider(FakeAuthSettings())
            self._provider = provider
        return provider

    def issue_authorization_code(self, *, username: str) -> str:
        return self.build_provider().issue_authorization_code(username=username)

    def tampered_access_token(self, *, username: str) -> str:
        token = self.build_provider().issue_access_token(username=username)
        # Not a real signature to corrupt -- but any mutation makes the
        # string fail the fake's own "is this a token I minted" lookup,
        # the fake's analog of a bad signature.
        return token[:-1] + ("y" if token[-1] != "y" else "z")

    def expired_access_token(self, *, username: str) -> str:
        return self.build_provider().issue_access_token(username=username, expires_in=-10.0)

    def wrong_issuer_access_token(self, *, username: str) -> str:
        return self.build_provider().issue_access_token(
            username=username,
            issuer=IssuerRef(value="untrusted-issuer"),
            trusted=False,
        )

    def access_token_with_multiple_memberships(self, *, username: str, tenant_refs) -> str:
        provider = self.build_provider()
        provider.register_user(
            username=username,
            memberships=[Membership(tenant_ref=ref) for ref in tenant_refs],
        )
        return provider.issue_access_token(username=username)
