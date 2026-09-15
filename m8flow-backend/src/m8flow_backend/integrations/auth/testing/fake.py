"""In-memory reference implementation of ``AuthProvider``.

Built by the auth-provider-seam wayfinder map, ticket 02 ("Build the
conformance suite + fake provider"). Exists for two reasons:

1. It is the forcing function that proves the port isn't secretly
   Keycloak-shaped -- an abstraction with only one implementation has no way
   to notice when it leaks. ``testing/conformance.py``'s
   ``AuthProviderConformance`` suite runs, unmodified, against this and
   against ``KeycloakAuthProvider``.
2. It is the worked reference a future provider author (Auth0, ...) reads
   first -- favour clarity over cleverness throughout.

Everything here is pure Python state: no HTTP, no environment reads, no
threads. It declines every directory-admin and provisioning capability --
its job is to prove the *session/verify/read* seam is provider-agnostic, not
to duplicate Keycloak's Admin API in memory.

``set_active_tenant`` followed by ``refresh`` re-mints a token carrying the
new tenant, mirroring the real behavior the active-tenant deep-module map
depends on: Keycloak does this via a RealmInfoMapper reading a user
attribute at token-mint time; here it's a plain dict lookup at the same
point (``_mint_access_token``).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from m8flow_backend.integrations.auth.base.capabilities import SupportsDirectoryAdmin, SupportsProvisioning
from m8flow_backend.integrations.auth.base.errors import CapabilityNotSupported, TokenInvalid, UserNotFound
from m8flow_backend.integrations.auth.base.models import (
    IssuerRef,
    Membership,
    TenantRef,
    TokenSet,
    User,
    VerifiedClaims,
)
from m8flow_backend.integrations.auth.base.provider import AuthProvider

_DEFAULT_TOKEN_TTL_SECONDS = 3600.0


@dataclass(frozen=True)
class FakeAuthSettings:
    """Everything ``InMemoryAuthProvider`` needs, with no environment reads
    -- the "constructible with settings, not env" idiom locked by the port
    surface's decision 5 (``assets/01-port-surface.md``)."""

    default_issuer_value: str = "fake"
    default_tenant_alias: str = "fake-tenant"
    default_tenant_name: str = "Fake Tenant"
    default_issuer_claim_value: str = "https://fake-idp.invalid/realms/fake"


@dataclass
class _Session:
    """One minted access token's state. Looked up by the token string
    itself -- there is no separate "database"; the token *is* the key."""

    subject: str
    username: str
    issuer_value: str
    roles: list[str]
    memberships: list[Membership]
    active_tenant_ref: TenantRef | None
    expires_at: float


class InMemoryAuthProvider(AuthProvider):
    """Pure in-memory ``AuthProvider``. See module docstring."""

    def __init__(self, settings: FakeAuthSettings | None = None) -> None:
        self._settings = settings or FakeAuthSettings()
        self._trusted_issuers: set[str] = {self._settings.default_issuer_value}
        self._codes: dict[str, str] = {}
        self._access_tokens: dict[str, _Session] = {}
        self._refresh_tokens: dict[str, str] = {}  # refresh token -> username
        self._users: dict[tuple[str, str], User] = {}  # (issuer value, username) -> User
        self._memberships: dict[str, list[Membership]] = {}
        self._roles: dict[str, list[str]] = {}
        self._active_tenant: dict[str, str] = {}  # username -> tenant id

    # --- Harness / seeding hooks (not part of AuthProvider) -----------------
    # A fake's whole point is to be driven directly by its own test code --
    # unlike a real provider, there's no vendor API surface to keep private.

    def register_user(
        self,
        *,
        username: str,
        issuer: IssuerRef | None = None,
        subject: str | None = None,
        email: str | None = None,
        roles: list[str] | None = None,
        memberships: list[Membership] | None = None,
    ) -> User:
        issuer = issuer or self.default_issuer()
        user = User(subject=subject or f"user-{uuid.uuid4().hex[:8]}", username=username, email=email)
        self._users[(issuer.value, username)] = user
        self._memberships[username] = list(memberships or [])
        self._roles[username] = list(roles or [])
        return user

    def issue_authorization_code(self, *, username: str, issuer: IssuerRef | None = None) -> str:
        """Simulate the user having completed login at the (fake) IdP --
        ``exchange_code`` is the only way to redeem this, exactly like a
        real provider's authorization code. Auto-registers ``username`` with
        no roles/memberships if it isn't known yet, so simple round-trip
        scenarios don't need a separate ``register_user`` call first."""
        issuer = issuer or self.default_issuer()
        self._trusted_issuers.add(issuer.value)
        if (issuer.value, username) not in self._users:
            self.register_user(username=username, issuer=issuer)
        code = f"code-{uuid.uuid4().hex}"
        self._codes[code] = username
        return code

    def issue_access_token(
        self,
        *,
        username: str,
        issuer: IssuerRef | None = None,
        expires_in: float = _DEFAULT_TOKEN_TTL_SECONDS,
        trusted: bool = True,
    ) -> str:
        """Mint an access token directly, bypassing the login flow -- for
        conformance scenarios that need a token in a specific state (already
        expired, from an untrusted issuer) without a full round trip.
        Mirrors what a real IdP's own test tooling would offer."""
        issuer = issuer or self.default_issuer()
        if trusted:
            self._trusted_issuers.add(issuer.value)
        if (issuer.value, username) not in self._users:
            self.register_user(username=username, issuer=issuer)
        return self._mint_access_token(username=username, issuer=issuer, expires_in=expires_in)

    # --- AuthProvider: session / OIDC ---------------------------------------

    def build_login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        issuer: IssuerRef,
        nonce: str | None = None,
        prompt: str | None = None,
    ) -> str:
        del nonce, prompt  # the fake doesn't model a real browser round trip
        return f"{self._authorization_endpoint(issuer)}?redirect_uri={redirect_uri}&state={state}"

    def exchange_code(self, *, code: str, redirect_uri: str, issuer: IssuerRef) -> TokenSet:
        del redirect_uri
        username = self._codes.pop(code, None)
        if username is None:
            raise TokenInvalid("Unknown or already-redeemed authorization code")
        return self._mint_token_set(username=username, issuer=issuer)

    def refresh(self, *, refresh_token: str, issuer: IssuerRef) -> TokenSet:
        username = self._refresh_tokens.pop(refresh_token, None)
        if username is None:
            raise TokenInvalid("Unknown or already-used refresh token")
        return self._mint_token_set(username=username, issuer=issuer)

    def build_logout_url(
        self,
        *,
        issuer: IssuerRef,
        redirect_uri: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        del id_token_hint
        return f"{self._authorization_endpoint(issuer)}/logout?redirect_uri={redirect_uri or '/'}"

    # --- AuthProvider: token + directory read -------------------------------

    def verify_token(self, token: str) -> VerifiedClaims:
        session = self._access_tokens.get(token)
        if session is None:
            raise TokenInvalid("Access token is not recognized")
        if session.issuer_value not in self._trusted_issuers:
            raise TokenInvalid("Access token issuer is not trusted")
        if session.expires_at <= time.time():
            raise TokenInvalid("Access token has expired")
        return VerifiedClaims(
            subject=session.subject,
            issuer=session.issuer_value,
            username=session.username,
            roles=list(session.roles),
            memberships=list(session.memberships),
            active_tenant_ref=session.active_tenant_ref,
            jwt_claims={"sub": session.subject, "iss": session.issuer_value},
        )

    def get_user(self, *, username: str, issuer: IssuerRef) -> User:
        user = self._users.get((issuer.value, username))
        if user is None:
            raise UserNotFound(username)
        return user

    def search_users(self, *, query: str, issuer: IssuerRef, limit: int = 50, offset: int = 0) -> list[User]:
        needle = query.lower()
        matches = [
            user
            for (issuer_value, username), user in self._users.items()
            if issuer_value == issuer.value and needle in username.lower()
        ]
        return matches[offset : offset + limit]

    def list_memberships(self, *, username: str) -> list[Membership]:
        return list(self._memberships.get(username, []))

    def set_active_tenant(self, *, username: str, tenant_id: str) -> None:
        self._active_tenant[username] = tenant_id

    # --- AuthProvider: self-description -------------------------------------

    def default_issuer(self) -> IssuerRef:
        return IssuerRef(value=self._settings.default_issuer_value)

    def default_tenant_ref(self) -> TenantRef:
        return TenantRef(alias=self._settings.default_tenant_alias, name=self._settings.default_tenant_name)

    def authorization_endpoint_url(self, issuer: IssuerRef) -> str:
        return self._authorization_endpoint(issuer)

    def default_issuer_claim(self) -> str:
        return self._settings.default_issuer_claim_value

    # is_master_issuer: inherits AuthProvider's concrete `return False` --
    # the fake has no master/bootstrap-realm concept to override it with.

    # --- AuthProvider: capabilities (all declined) --------------------------

    @property
    def user_admin(self):
        raise CapabilityNotSupported("user_admin")

    @property
    def tenant_admin(self):
        raise CapabilityNotSupported("tenant_admin")

    @property
    def group_admin(self):
        raise CapabilityNotSupported("group_admin")

    @property
    def role_admin(self):
        raise CapabilityNotSupported("role_admin")

    @property
    def directory_admin(self) -> SupportsDirectoryAdmin:
        raise CapabilityNotSupported("directory_admin")

    @property
    def provisioning(self) -> SupportsProvisioning:
        raise CapabilityNotSupported("provisioning")

    # --- internals -----------------------------------------------------------

    def _authorization_endpoint(self, issuer: IssuerRef) -> str:
        return f"https://fake-idp.invalid/{issuer.value}/authorize"

    def _mint_token_set(self, *, username: str, issuer: IssuerRef) -> TokenSet:
        access_token = self._mint_access_token(
            username=username, issuer=issuer, expires_in=_DEFAULT_TOKEN_TTL_SECONDS
        )
        refresh_token = f"refresh-{uuid.uuid4().hex}"
        self._refresh_tokens[refresh_token] = username
        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=f"idtoken-{uuid.uuid4().hex}",
            expires_in=int(_DEFAULT_TOKEN_TTL_SECONDS),
        )

    def _mint_access_token(self, *, username: str, issuer: IssuerRef, expires_in: float) -> str:
        # Read fresh on every mint (not cached on the session at registration
        # time) -- this is what makes set_active_tenant() + refresh() reflect
        # a tenant switch: refresh() re-mints, and re-minting re-reads
        # self._active_tenant here.
        user = self._users.get((issuer.value, username))
        subject = user.subject if user is not None else username
        active_tenant_id = self._active_tenant.get(username)
        token = f"access-{uuid.uuid4().hex}"
        self._access_tokens[token] = _Session(
            subject=subject,
            username=username,
            issuer_value=issuer.value,
            roles=list(self._roles.get(username, [])),
            memberships=list(self._memberships.get(username, [])),
            active_tenant_ref=TenantRef(id=active_tenant_id) if active_tenant_id else None,
            expires_at=time.time() + expires_in,
        )
        return token
