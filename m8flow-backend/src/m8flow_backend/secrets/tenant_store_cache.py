"""Shared state and invalidation for cached tenant-scoped Vault stores.

This module intentionally has no dependency on Vault provisioning or provider
code. Tenant cleanup can invalidate cached stores without creating an import
cycle between those modules.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Condition, RLock
from typing import Any

CacheKey = tuple[tuple[str, str | None, str, str, bool | str], str]
TenantStore = Any

TENANT_STORE_CACHE: OrderedDict[CacheKey, tuple[TenantStore, float]] = OrderedDict()
TENANT_STORE_CACHE_LOCK = RLock()
TENANT_STORE_CACHE_CONDITION = Condition(TENANT_STORE_CACHE_LOCK)
TENANT_STORES_INITIALIZING: set[CacheKey] = set()


def invalidate_tenant_store_cache(tenant_id: str) -> None:
    """Forget cached tenant stores after tenant cleanup or identity retirement."""
    with TENANT_STORE_CACHE_CONDITION:
        while any(key[1] == tenant_id for key in TENANT_STORES_INITIALIZING):
            TENANT_STORE_CACHE_CONDITION.wait()
        for cache_key in tuple(TENANT_STORE_CACHE):
            if cache_key[1] == tenant_id:
                TENANT_STORE_CACHE.pop(cache_key, None)
