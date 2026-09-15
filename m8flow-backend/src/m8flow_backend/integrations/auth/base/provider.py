"""Abstract ``AuthProvider``: session/verify + directory read, plus typed capability accessors.

``ABC`` with ``@abstractmethod`` on every required method (auth-provider-seam
wayfinder map, ticket 13, per ticket 01's locked decision): a half-built
concrete provider fails at construction, not at first call. ``is_master_issuer``
is the one deliberate exception — a concrete default, not abstract; see its
own docstring.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from m8flow_backend.integrations.auth.base.capabilities import (
    SupportsDirectoryAdmin,
    SupportsGroupAdmin,
    SupportsProvisioning,
    SupportsRoleAdmin,
    SupportsTenantAdmin,
    SupportsUserAdmin,
)
from m8flow_backend.integrations.auth.base.errors import CapabilityNotSupported
from m8flow_backend.integrations.auth.base.models import IssuerRef, Membership, TenantRef, TokenSet, User, VerifiedClaims


class AuthProvider(ABC):
    """Provider-agnostic auth seam. The backend never sees a vendor vocabulary here."""

    @abstractmethod
    def build_login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        issuer: IssuerRef,
        nonce: str | None = None,
        prompt: str | None = None,
    ) -> str: ...

    @abstractmethod
    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        issuer: IssuerRef,
    ) -> TokenSet: ...

    @abstractmethod
    def refresh(self, *, refresh_token: str, issuer: IssuerRef) -> TokenSet: ...

    @abstractmethod
    def build_logout_url(
        self,
        *,
        issuer: IssuerRef,
        redirect_uri: str | None = None,
        id_token_hint: str | None = None,
    ) -> str: ...

    @abstractmethod
    def verify_token(self, token: str) -> VerifiedClaims: ...

    @abstractmethod
    def get_user(self, *, username: str, issuer: IssuerRef) -> User: ...

    @abstractmethod
    def search_users(
        self,
        *,
        query: str,
        issuer: IssuerRef,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]: ...

    @abstractmethod
    def list_memberships(self, *, username: str) -> list[Membership]: ...

    @abstractmethod
    def set_active_tenant(self, *, username: str, tenant_id: str) -> None:
        """Record the user's single active tenant/org so the next minted token
        carries its claims. Paired with ``refresh`` to re-mint seamlessly on a
        tenant switch (active-tenant deep-module map, ticket 10)."""
        ...

    # --- Added by the auth-provider-seam map's ticket 06 --------------------
    # (drain the nine thin config readers). Host code needs a default
    # identifier before any tenant is known — ticket 01 deferred that design
    # to this ticket; see assets/01-port-surface.md's addendum.

    @abstractmethod
    def default_issuer(self) -> IssuerRef:
        """The identifier session calls use before any tenant is known — the
        shared-realm login entry point is the default case, not an edge
        case (see IssuerRef's docstring)."""
        ...

    @abstractmethod
    def default_tenant_ref(self) -> TenantRef:
        """The tenant this provider treats as the default/shared-realm
        tenant, for bootstrap reconciliation and as a last-resort tenant_id
        fallback when nothing else has resolved one."""
        ...

    @abstractmethod
    def authorization_endpoint_url(self, issuer: IssuerRef) -> str:
        """Bare browser-facing authorization endpoint URL for ``issuer``, no
        query parameters. Distinct from ``build_login_url``, which always
        builds a complete login-flow redirect (state/redirect_uri/nonce/
        prompt) — some callers only want to know which URL a login for this
        issuer would start at, without building the redirect themselves."""
        ...

    @abstractmethod
    def default_issuer_claim(self) -> str:
        """The ``iss`` claim value a verified token from the default/shared
        realm carries — the full issuer string, not the routing-only
        IssuerRef. For local bookkeeping that must match a real verified
        token's issuer (e.g. tracking a locally-synced user's identity
        provider origin) without a token in hand."""
        ...

    def is_master_issuer(self, claims: VerifiedClaims) -> bool:
        """Whether ``claims`` came from this provider's platform/bootstrap
        realm, if it has one. Concrete default (not abstract, a deliberate
        exception to every other method on this class): providers without
        that concept get the safe answer, never true, with no
        CapabilityNotSupported ceremony for a plain yes/no question."""
        return False

    @property
    def user_admin(self) -> SupportsUserAdmin:
        raise CapabilityNotSupported("user_admin")

    @property
    def tenant_admin(self) -> SupportsTenantAdmin:
        raise CapabilityNotSupported("tenant_admin")

    @property
    def group_admin(self) -> SupportsGroupAdmin:
        raise CapabilityNotSupported("group_admin")

    @property
    def role_admin(self) -> SupportsRoleAdmin:
        raise CapabilityNotSupported("role_admin")

    @property
    def directory_admin(self) -> SupportsDirectoryAdmin:
        raise CapabilityNotSupported("directory_admin")

    @property
    def provisioning(self) -> SupportsProvisioning:
        raise CapabilityNotSupported("provisioning")
