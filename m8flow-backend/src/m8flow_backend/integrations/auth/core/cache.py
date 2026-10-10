"""Opt-in, short-TTL cache for directory membership lookups.

Thin tokens (Keycloak's RealmInfoMapper emits the active organization without
groups) make request-time group sync call the provider's directory on every
authenticated request. This cache bounds that cost.

**Disabled by default** (TTL 0), so behaviour is unchanged until an operator
sets ``M8FLOW_AUTH_MEMBERSHIP_CACHE_TTL_SECONDS``. When enabled, a role or
membership removed directly in the IdP is visible after at most the TTL; keep
it short (<= 60s). Host-initiated writes call ``invalidate`` so they are
visible immediately, and login finalization / tenant switch always bypass it.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

from m8flow_backend.integrations.auth.base.models import Membership

MEMBERSHIP_CACHE_TTL_ENV = "M8FLOW_AUTH_MEMBERSHIP_CACHE_TTL_SECONDS"
_MAX_TTL_SECONDS = 300.0


def membership_cache_ttl_seconds() -> float:
    raw = (os.environ.get(MEMBERSHIP_CACHE_TTL_ENV) or "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, min(value, _MAX_TTL_SECONDS))


class MembershipCache:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[Membership]]] = {}

    def get_or_load(self, username: str, loader: Callable[[], list[Membership]], *, ttl: float) -> list[Membership]:
        """Return a cached copy for ``username`` or call ``loader``. Loader
        exceptions propagate and are never cached."""
        if ttl <= 0:
            return loader()
        now = self._clock()
        with self._lock:
            cached = self._entries.get(username)
            if cached is not None and cached[0] > now:
                return list(cached[1])
        memberships = loader()
        with self._lock:
            self._entries[username] = (now + ttl, list(memberships))
        return list(memberships)

    def invalidate(self, username: str | None = None) -> None:
        with self._lock:
            if username is None:
                self._entries.clear()
            else:
                self._entries.pop(username, None)


#: Process-wide instance shared by every ``AuthService``.
membership_cache = MembershipCache()
