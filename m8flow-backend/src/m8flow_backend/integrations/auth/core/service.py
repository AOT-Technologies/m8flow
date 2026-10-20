"""``AuthService``: the concrete orchestrator that owns the auth *flows* on top
of any ``AuthProvider`` (authProvider-analysis combined design, section 3.3).

Before this module, the flows lived in host code and were written around one
Keycloak topology: the tenant-switch re-mint, best-effort directory lookups
during login finalization, membership listing for the tenant switcher,
platform-session detection, and logout's active-tenant cleanup. They now live
here, written once against the port, so a new identity provider supplies
*facts* (``switch_mode``, ``trust_domain``, directory reads) and never
re-implements a flow -- including the AGENTS.md multi-organization rules.

The host keeps everything that touches the m8flow DB, RLS, or cookies.

Duck-typed providers are supported on purpose: every new hook has a default
derived from the original port methods, so providers (and test doubles) that
only implement the pre-existing surface behave exactly as before.

``AuthService`` is cheap and stateless (the only shared state is the opt-in
membership cache); build one per use with the provider your call site already
resolves, e.g. ``AuthService(get_auth_provider())``.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from m8flow_backend.integrations.auth.base.capabilities import (
    SupportsDirectoryAdmin,
    SupportsGroupAdmin,
    SupportsProvisioning,
    SupportsRoleAdmin,
    SupportsTenantAdmin,
    SupportsUserAdmin,
)
from m8flow_backend.integrations.auth.base.errors import (
    AuthProviderError,
    CapabilityNotSupported,
)
from m8flow_backend.integrations.auth.base.models import IssuerRef, Membership, TrustDomain, VerifiedClaims
from m8flow_backend.integrations.auth.core.cache import (
    InvalidatingDirectoryAdmin,
    membership_cache,
    membership_cache_ttl_seconds,
)
from m8flow_backend.integrations.auth.core.switching import SwitchMode, SwitchOutcome

logger = logging.getLogger(__name__)

#: Every capability accessor ``AuthProvider`` exposes, and the interface its
#: return value must implement to count as supported.
_CAPABILITY_TYPES: dict[str, type] = {
    "user_admin": SupportsUserAdmin,
    "tenant_admin": SupportsTenantAdmin,
    "group_admin": SupportsGroupAdmin,
    "role_admin": SupportsRoleAdmin,
    "directory_admin": SupportsDirectoryAdmin,
    "provisioning": SupportsProvisioning,
}
CAPABILITY_NAMES = tuple(_CAPABILITY_TYPES)


class AuthService:
    def __init__(self, provider: object) -> None:
        self._provider = provider

    @property
    def provider(self) -> object:
        return self._provider

    # --- provider facts, with defaults for providers that predate them ----

    @property
    def switch_mode(self) -> SwitchMode:
        mode = getattr(self._provider, "switch_mode", None)
        return SwitchMode(mode) if mode is not None else SwitchMode.REMINT

    def trust_domain(self, claims: VerifiedClaims) -> TrustDomain:
        """The issuer's trust domain: the value the provider stamped at
        verification time when present, else the provider's classifier, else
        derived from ``is_master_issuer`` (the original port method)."""
        if claims.trust_domain is not None:
            return TrustDomain(claims.trust_domain)
        classifier = getattr(self._provider, "trust_domain", None)
        if callable(classifier):
            return TrustDomain(classifier(claims))
        is_master = getattr(self._provider, "is_master_issuer", None)
        if callable(is_master) and is_master(claims):
            return TrustDomain.PLATFORM
        return TrustDomain.SHARED

    def is_platform_session(self, claims: VerifiedClaims) -> bool:
        return self.trust_domain(claims) is TrustDomain.PLATFORM

    def capabilities(self) -> dict[str, bool]:
        """Which admin capabilities the IdP supports at all (never whether the
        *user* may use them -- that is RBAC / ``permissions-check``)."""
        supported: dict[str, bool] = {}
        for name, interface in _CAPABILITY_TYPES.items():
            try:
                supported[name] = isinstance(getattr(self._provider, name), interface)
            except (CapabilityNotSupported, AttributeError):
                supported[name] = False
        return supported

    # --- membership authority ---------------------------------------------

    def directory_memberships(
        self,
        username: str,
        *,
        issuer: str | None = None,
        use_cache: bool = True,
    ) -> list[Membership]:
        """Every membership the provider's directory knows for ``username``.
        Raises on provider failure; callers choose their own fallback. Served
        from the opt-in cache when enabled, ``use_cache`` is True and the
        lookup has a cache scope (see ``membership_cache_scope``). A missing,
        non-string or blank ``username`` has no memberships and never reaches
        the provider."""
        if not isinstance(username, str) or not username.strip():
            return []
        cleaned = username.strip()
        scope = self.membership_cache_scope(issuer) if use_cache else None
        if scope is None:
            # Unknown directory: never touch the cache, so one realm's answer
            # cannot be served to another realm's identically named user.
            return self._provider.list_memberships(username=cleaned)
        return membership_cache.get_or_load(
            scope,
            cleaned,
            lambda: self._provider.list_memberships(username=cleaned),
            ttl=membership_cache_ttl_seconds(),
        )

    def membership_cache_scope(self, issuer: str | None) -> str | None:
        """The directory a username belongs to, for cache isolation: the
        provider's ``membership_cache_scope(issuer)`` when it defines one, else
        the verified token issuer. ``None`` means "unknown directory" and the
        lookup is never cached, so one realm's answer cannot be served to
        another realm's identically named user."""
        hook = getattr(self._provider, "membership_cache_scope", None)
        if callable(hook):
            scope = hook(issuer)
        else:
            scope = issuer
        if not isinstance(scope, str) or not scope.strip():
            return None
        return scope.strip()

    def directory_memberships_best_effort(self, username: str | None) -> list[Membership]:
        """Login-finalization lookup: always fresh (never cached), and an empty
        list instead of an error when the directory is unavailable."""
        if not isinstance(username, str) or not username.strip():
            return []
        try:
            return self.directory_memberships(username, use_cache=False)
        except (AuthProviderError, ValueError):
            logger.warning(
                "tenant_finalization: directory membership enrichment failed for %s",
                username,
                exc_info=True,
            )
            return []

    def memberships_for_switcher(self, claims: VerifiedClaims) -> list[Membership]:
        """The full membership list the tenant switcher offers. The token is
        used only when it declares itself complete or there is no username to
        look the user up by (service tokens); otherwise the directory is the
        source of truth -- Keycloak's RealmInfoMapper only emits the active
        organization. Provider errors propagate (the route maps them)."""
        if claims.memberships_complete:
            return list(claims.memberships)
        if claims.username:
            return self.directory_memberships(claims.username, issuer=claims.issuer)
        return list(claims.memberships)

    def invalidate(self, username: str | None = None) -> None:
        membership_cache.invalidate(username.strip() if isinstance(username, str) else None)

    @property
    def directory_admin(self) -> InvalidatingDirectoryAdmin:
        """``provider.directory_admin`` with membership writes invalidating
        the membership cache; host write paths use this one."""
        return InvalidatingDirectoryAdmin(self._provider.directory_admin, self.invalidate)

    # --- tenant switch ----------------------------------------------------

    def switch_tenant(
        self,
        *,
        username: str,
        tenant_id: str,
        refresh_token: str | None,
        issuer: IssuerRef,
    ) -> SwitchOutcome:
        """Make the session's token carry ``tenant_id`` the way this provider's
        topology allows. Never raises for an IdP-side failure in ``REMINT``
        mode: the ``m8flow_selected_tenant`` cookie is authoritative, so a
        failed re-mint degrades to "cookie switched, token claims catch up on
        the next natural refresh" (``outcome.tokens is None``)."""
        self.invalidate(username)
        mode = self.switch_mode
        if mode is SwitchMode.COOKIE_ONLY:
            return SwitchOutcome(mode=mode)
        if mode is not SwitchMode.REMINT:
            raise CapabilityNotSupported(f"tenant switch mode {mode.value!r} is not wired into the host yet")
        if not refresh_token:
            return SwitchOutcome(mode=mode)
        try:
            self._provider.set_active_tenant(username=username, tenant_id=tenant_id)
            tokens = self._provider.refresh(refresh_token=refresh_token, issuer=issuer)
        except AuthProviderError:
            logger.warning(
                "tenant switch: active-tenant re-mint failed for %s (tenant=%s); "
                "cookie switched, token claims will catch up on next refresh",
                username,
                tenant_id,
                exc_info=True,
            )
            return SwitchOutcome(mode=mode)
        return SwitchOutcome(mode=mode, tokens=tokens)

    def end_session(self, *, username: str) -> None:
        """Logout hygiene: forget any server-side active tenant so the next
        sign-in cannot silently resume it. Raises on provider failure; logout
        callers treat this as best-effort."""
        self.invalidate(username)
        if self.switch_mode is SwitchMode.REMINT:
            self._provider.clear_active_tenant(username=username)

    # --- neutral session view (GET /v1.0/m8flow/session) -------------------

    def session_view(self, claims: VerifiedClaims, *, selected_tenant: str | None) -> Mapping[str, object]:
        """Provider-neutral description of the current session so the
        frontend never has to decode vendor-shaped JWT claims."""
        active = claims.active_tenant_ref
        return {
            "subject": claims.subject,
            "username": claims.username,
            "email": claims.email,
            "trust_domain": self.trust_domain(claims).value,
            "is_platform_session": self.is_platform_session(claims),
            "selected_tenant": selected_tenant,
            "token_active_tenant": (
                None if active is None else {"id": active.id, "alias": active.alias, "name": active.name}
            ),
            "switch_mode": self.switch_mode.value,
            "capabilities": self.capabilities(),
        }
