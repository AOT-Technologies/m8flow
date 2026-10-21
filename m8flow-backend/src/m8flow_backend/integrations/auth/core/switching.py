"""Tenant-switch vocabulary: how a provider makes a session's token carry a
different tenant, and what a switch produced.

The mode is a *fact about the identity provider's topology*, declared by the
provider (``AuthProvider.switch_mode``). ``AuthService.switch_tenant`` owns the
sequencing for every mode, so a provider never re-implements the flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from m8flow_backend.integrations.auth.base.models import TokenSet


class SwitchMode(StrEnum):
    """- ``REMINT``: write server-side "active tenant" state, then a refresh
      grant re-mints the token with it (Keycloak Organizations +
      RealmInfoMapper).
    - ``REAUTHORIZE``: a new authorize request scoped to the tenant, silent
      when the IdP session is alive (Auth0 Organizations).
    - ``REAUTHENTICATE``: log in at the tenant's own issuer (Keycloak
      realm-per-tenant).
    - ``COOKIE_ONLY``: tokens are not tenant-bound; the
      ``m8flow_selected_tenant`` cookie alone switches.
    """

    REMINT = "remint"
    REAUTHORIZE = "reauthorize"
    REAUTHENTICATE = "reauthenticate"
    COOKIE_ONLY = "cookie_only"


@dataclass(frozen=True)
class SwitchOutcome:
    """Result of ``AuthService.switch_tenant``. The host still owns every
    cookie write: it always sets ``m8flow_selected_tenant``, and sets token
    cookies only when ``tokens`` is present."""

    mode: SwitchMode
    tokens: TokenSet | None = None
    redirect_url: str | None = None

    @property
    def reminted(self) -> bool:
        return self.tokens is not None
