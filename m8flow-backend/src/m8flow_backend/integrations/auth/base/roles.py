"""Canonical neutral role vocabulary for m8flow RBAC.

This is m8flow's own, provider-independent vocabulary. A provider translates
between these names and its realization of them (Keycloak: organization groups
named ``Administrators``/``Designers``/... plus realm roles).

The Keycloak group-name table lives in ``integrations.auth.keycloak.role_mapping``.
(``services.tenant_group_mapping`` used to re-export these names for older
callers; deleted once its last caller was drained -- auth-provider-seam
wayfinder map, ticket 16.)
"""
from __future__ import annotations

from collections.abc import Iterable

VALID_TENANT_ROLE_NAMES = frozenset(
    (
        "tenant-admin",
        "editor",
        "integrator",
        "reviewer",
        "submitter",
        "viewer",
    )
)

# The global, non-tenant-scoped role that grants platform super-admin.
SUPER_ADMIN_ROLE = "super-admin"


def normalize_tenant_role_name(role_name: str | None) -> str:
    """Return ``role_name`` if it is a valid neutral tenant role, else ``""``."""
    normalized = str(role_name or "").strip()
    if normalized not in VALID_TENANT_ROLE_NAMES:
        return ""
    return normalized


def normalize_tenant_role_names(role_names: Iterable[str | None] | None) -> tuple[str, ...]:
    """Validate, de-duplicate, and sort a collection of neutral tenant role names."""
    normalized_role_names: list[str] = []
    seen: set[str] = set()
    for role_name in role_names or ():
        normalized = normalize_tenant_role_name(role_name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_role_names.append(normalized)
    return tuple(sorted(normalized_role_names))
