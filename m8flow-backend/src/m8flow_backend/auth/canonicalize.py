"""DB-backed tenant-identifier resolution: mapping a claimed id/alias/slug to
the local canonical M8flowTenantModel row (or the row's slug), and reading
the active tenant out of the current request/context.

Collapses what were three near-identical inline queries (one per public
function) into one shared ``_find_tenant_row`` helper -- see the active-tenant
deep-module map, ticket 03.
"""

from __future__ import annotations

from flask import g, has_request_context

from m8flow_backend.auth.tenant_context import get_context_tenant_id, is_concrete_tenant_id


def _find_tenant_row(*identifiers: str | None):
    """Resolve one or more claimed identifiers (id or slug) to the matching
    ``M8flowTenantModel`` row, or ``None``. Any DB error (including an
    ambiguous match across the identifier set) resolves to ``None`` -- the
    original per-function try/except behavior, preserved.
    """
    normalized_identifiers: list[str] = []
    seen: set[str] = set()
    for identifier in identifiers:
        if not isinstance(identifier, str):
            continue
        normalized_identifier = identifier.strip()
        if not normalized_identifier or normalized_identifier in seen:
            continue
        seen.add(normalized_identifier)
        normalized_identifiers.append(normalized_identifier)

    if not normalized_identifiers:
        return None

    try:
        from sqlalchemy import or_

        from m8flow_bpmn_core.models.tenant import M8flowTenantModel

        filters = []
        for normalized_identifier in normalized_identifiers:
            filters.extend(
                (
                    M8flowTenantModel.id == normalized_identifier,
                    M8flowTenantModel.slug == normalized_identifier,
                )
            )
        return g.db_session.query(M8flowTenantModel).filter(or_(*filters)).one_or_none()
    except Exception:
        return None


def _canonical_tenant_id_from_identifiers(*identifiers: str | None) -> str | None:
    """
    Resolve token-provided tenant identifiers to the local canonical tenant id.

    When a matching tenant row exists, always return that row's primary key so
    downstream tenant scoping, group qualification, and FK-backed records stay
    consistent.
    """
    tenant = _find_tenant_row(*identifiers)
    if tenant is None or not isinstance(tenant.id, str):
        return None

    canonical_tenant_id = tenant.id.strip()
    return canonical_tenant_id or None


def current_tenant_id_or_none() -> str | None:
    """Return the active tenant id, or ``None`` when no tenant context is set."""
    if has_request_context():
        if getattr(g, "_m8flow_global_request", False) or getattr(g, "_m8flow_public_request", False):
            return None

        request_tenant = getattr(g, "m8flow_tenant_id", None)
        if isinstance(request_tenant, str):
            normalized_request_tenant = request_tenant.strip()
            if is_concrete_tenant_id(normalized_request_tenant):
                return normalized_request_tenant

    context_tenant = get_context_tenant_id()
    if isinstance(context_tenant, str):
        normalized_context_tenant = context_tenant.strip()
        if is_concrete_tenant_id(normalized_context_tenant):
            return normalized_context_tenant

    return None


def current_tenant_identifiers(tenant_id: str | None = None) -> set[str]:
    """Return the current tenant id plus any equivalent identifiers such as the slug."""
    effective_tenant_id = (tenant_id or current_tenant_id_or_none() or "").strip()
    if not effective_tenant_id:
        return set()

    identifiers = {effective_tenant_id}
    tenant = _find_tenant_row(effective_tenant_id)

    if tenant is not None:
        for value in (tenant.id, tenant.slug):
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    identifiers.add(normalized)

    return identifiers


def _tenant_slug_for_identifier(tenant_identifier: str) -> str | None:
    """Resolve a tenant id or slug to the canonical tenant slug."""
    effective_tenant_identifier = tenant_identifier.strip()
    if not effective_tenant_identifier:
        return None

    tenant = _find_tenant_row(effective_tenant_identifier)
    if tenant is None or not isinstance(tenant.slug, str):
        return None

    slug = tenant.slug.strip()
    return slug or None


def tenant_slug_for_identifier(tenant_identifier: str) -> str | None:
    """Public wrapper for resolving a tenant id or alias to the canonical tenant slug."""
    if not isinstance(tenant_identifier, str):
        return None
    return _tenant_slug_for_identifier(tenant_identifier)


class DbTenantRepo:
    """Real ``TenantRepo`` adapter (see ``ports.py``) backed by ``g.db_session``."""

    def canonical_tenant_id(self, *identifiers: str | None) -> str | None:
        return _canonical_tenant_id_from_identifiers(*identifiers)

    def current_identifiers(self, tenant_id: str) -> set[str]:
        return current_tenant_identifiers(tenant_id)

    def slug_for_identifier(self, tenant_identifier: str) -> str | None:
        return _tenant_slug_for_identifier(tenant_identifier)
