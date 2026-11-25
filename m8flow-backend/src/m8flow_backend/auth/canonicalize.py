"""DB-backed tenant-identifier resolution: mapping a claimed id/alias/slug to
the local canonical M8flowTenantModel row (or the row's slug), and reading
the active tenant out of the current request/context.

Collapses what were three near-identical inline queries (one per public
function) into one shared ``_find_tenant_row`` helper.
"""

from __future__ import annotations

from flask import g, has_request_context
from sqlalchemy import event
from sqlalchemy.orm import Session

from m8flow_backend.auth.tenant_context import get_context_tenant_id, is_concrete_tenant_id

_REQUEST_MEMO_ATTR = "_m8flow_request_memo"


def request_memo(name: str, session: Session | None) -> dict | None:
    """Per-request cache bucket for a read-only lookup, or None when caching is unsafe.

    None outside a request, or while ``session`` holds unflushed writes (with
    autoflush on, a fresh query would see them; a cached answer would not).
    A flush, rollback or non-SELECT execute on *any* SQLAlchemy session drops
    every bucket (listeners below), so nothing written through a session
    earlier in the request is ever hidden, whichever session wrote it. Writes
    that bypass sessions (a raw connection, another process) are seen from
    the next request: for those, the lookups are a per-request snapshot.
    Nothing in the request path writes grants, groups or tenants that way.
    authorization ran 3 queries per (uri, method) checked, ~250 per
    permissions-check.
    """
    if session is None or not has_request_context():
        return None
    if getattr(session, "new", None) or getattr(session, "dirty", None) or getattr(session, "deleted", None):
        return None
    buckets = getattr(g, _REQUEST_MEMO_ATTR, None)
    if buckets is None:
        buckets = {}
        setattr(g, _REQUEST_MEMO_ATTR, buckets)
    return buckets.setdefault(name, {})


@event.listens_for(Session, "after_flush")
@event.listens_for(Session, "after_soft_rollback")
def _drop_request_memo(_session, *_args) -> None:
    if has_request_context():
        g.pop(_REQUEST_MEMO_ATTR, None)


@event.listens_for(Session, "do_orm_execute")
def _drop_request_memo_on_write(orm_execute_state) -> None:
    # Core writes grants with session.execute(insert(...)), which never flushes.
    if not orm_execute_state.is_select:
        _drop_request_memo(orm_execute_state.session)


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

        from m8flow_core.models.tenant import M8flowTenantModel

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

    memo = request_memo("tenant_identifiers", getattr(g, "db_session", None) if has_request_context() else None)
    if memo is not None and effective_tenant_id in memo:
        return set(memo[effective_tenant_id])

    identifiers = {effective_tenant_id}
    tenant = _find_tenant_row(effective_tenant_id)

    if tenant is not None:
        for value in (tenant.id, tenant.slug):
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    identifiers.add(normalized)
        # Only hits are cached: a tenant created later in the request must not
        # be hidden behind a remembered miss.
        if memo is not None:
            memo[effective_tenant_id] = frozenset(identifiers)

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
