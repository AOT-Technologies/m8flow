"""Opt-in, short-TTL cache for directory membership lookups.

Thin tokens (Keycloak's RealmInfoMapper emits the active organization without
groups) make request-time group sync call the provider's directory on every
authenticated request. This cache bounds that cost.

**Disabled by default** (TTL 0), so behaviour is unchanged until an operator
sets ``M8FLOW_AUTH_MEMBERSHIP_CACHE_TTL_SECONDS`` (capped at 60s). A change
made directly in the IdP is visible after at most the TTL. Login finalization
bypasses the cache; tenant switch, logout and writes through
``AuthService.directory_admin`` invalidate it.

The cache is **per process**: an invalidation only reaches the worker that
made the write, so other workers can lag by up to the TTL.

Entries are keyed by ``(scope, username)``, never the bare username: in a
realm-per-tenant topology the same username can exist in several directories
with different memberships, and this process-wide instance is shared by every
``AuthService``, so the key is the only place that isolation can be enforced.
``AuthService`` derives the scope from the token issuer (or the provider's
``membership_cache_scope`` hook) and skips the cache when it has none.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

from m8flow_backend.integrations.auth.base.models import Membership

MEMBERSHIP_CACHE_TTL_ENV = "M8FLOW_AUTH_MEMBERSHIP_CACHE_TTL_SECONDS"
_MAX_TTL_SECONDS = 60.0


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
        self._entries: dict[tuple[str, str], tuple[float, list[Membership]]] = {}
        # Bumped by every ``invalidate``. A load that started before an
        # invalidate must not store its (possibly stale) result afterwards.
        self._generation = 0

    def get_or_load(
        self,
        scope: str,
        username: str,
        loader: Callable[[], list[Membership]],
        *,
        ttl: float,
    ) -> list[Membership]:
        """Return a cached copy for ``(scope, username)`` or call ``loader``.
        Loader exceptions propagate and are never cached."""
        if ttl <= 0:
            return loader()
        key = (scope, username)
        now = self._clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached[0] > now:
                return list(cached[1])
            generation = self._generation
        memberships = loader()
        with self._lock:
            if self._generation == generation:
                self._prune_expired(now)
                self._entries[key] = (now + ttl, list(memberships))
        return list(memberships)

    def invalidate(self, username: str | None = None) -> None:
        """Drop ``username``'s entries in every scope (host writes name only
        the user), or everything when ``username`` is None."""
        with self._lock:
            self._generation += 1
            if username is None:
                self._entries.clear()
            else:
                for key in [k for k in self._entries if k[1] == username]:
                    del self._entries[key]

    def _prune_expired(self, now: float) -> None:
        for key in [k for k, (expires, _) in self._entries.items() if expires <= now]:
            del self._entries[key]


#: Process-wide instance shared by every ``AuthService``.
membership_cache = MembershipCache()

#: Directory-admin writes that change a user's tenant roles or groups. A write
#: naming a ``username`` invalidates that user; group- and tenant-wide writes
#: invalidate everyone.
_MEMBERSHIP_WRITES = frozenset(
    {
        "add_member",
        "remove_member",
        "add_group_member",
        "remove_group_member",
        "assign_roles",
        "remove_roles",
        "set_group_roles",
        "rename_group",
        "delete_group",
        "delete_user",
        "delete_tenant",
    }
)


class InvalidatingDirectoryAdmin:
    """Directory-admin capability whose membership writes invalidate the
    cache, even when the write raises part-way through."""

    def __init__(self, admin: Any, invalidate: Callable[[str | None], None]) -> None:
        self._admin = admin
        self._invalidate = invalidate

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._admin, name)
        if name not in _MEMBERSHIP_WRITES:
            return attr

        def write(*args: Any, **kwargs: Any) -> Any:
            try:
                return attr(*args, **kwargs)
            finally:
                self._invalidate(kwargs.get("username") or None)

        return write
