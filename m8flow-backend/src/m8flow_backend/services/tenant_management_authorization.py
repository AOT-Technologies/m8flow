from __future__ import annotations

from flask import g
from flask import request

from m8flow_backend.authorization import allow_uri
from m8flow_backend.errors import ApiError
from m8flow_backend.integrations.auth.base.models import VerifiedClaims
from m8flow_backend.auth import is_super_admin_request


def _user_is_tenant_admin_or_super_admin(
    user: object,
    tenant_id: str | None = None,
) -> bool:
    """Return True if the user has tenant-admin or super-admin access via group membership.

    Used as a fallback when SpiffWorkflow permissions have not yet been populated in the DB
    (e.g. first login with a multi-org token that defers group sync, or YAML import has not
    run for the current login cycle).
    """
    if is_super_admin_request():
        return True

    from m8flow_backend.auth.canonicalize import (
        current_tenant_id_or_none,
        current_tenant_identifiers,
    )

    effective_tenant_id = tenant_id or current_tenant_id_or_none()
    if not effective_tenant_id:
        return False

    tenant_ids = current_tenant_identifiers(effective_tenant_id)
    for group in getattr(user, "groups", []):
        identifier = getattr(group, "identifier", None)
        if not isinstance(identifier, str) or not identifier:
            continue
        if identifier == "super-admin":
            return True
        prefix, sep, role = identifier.partition(":")
        if sep and prefix in tenant_ids and role == "tenant-admin":
            return True

    return False


def require_authorized_user(
    action: str,
    *,
    forbidden_message: str,
    tenant_id: str | None = None,
    group_fallback: bool = True,
):
    user = getattr(g, "user", None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401,
        )

    if allow_uri(
        user,
        action,
        request.path,
        session=getattr(g, "db_session", None),
        group_fallback=group_fallback,
    ):
        return user

    # Fallback: check group membership directly (see _user_is_tenant_admin_or_super_admin
    # docstring for why permissions may not be in the DB yet).
    if _user_is_tenant_admin_or_super_admin(user, tenant_id=tenant_id):
        return user

    raise ApiError(
        error_code="forbidden",
        message=forbidden_message,
        status_code=403,
    )


def _normalized_request_tenant_identifiers() -> set[str]:
    """Every tenant identifier (id and/or alias) this request's session can
    plausibly be scoped to: the already-resolved request tenant, the
    finalized/active tenant, and every tenant the user is a member of.

    Reads only `VerifiedClaims` (auth-provider-seam wayfinder map, ticket 10:
    "Neutralize the token shape") -- `active_tenant_ref` replaces the former
    raw `m8flow_tenant_id`/`m8flow_tenant_alias`/active-organization claim
    reads, and `memberships` replaces the raw `organization` claim
    destructuring. Despite the filename this is tenant-identifier
    resolution, not authorization.
    """
    tenant_identifiers: set[str] = set()

    request_tenant_id = getattr(g, "m8flow_tenant_id", None)
    if isinstance(request_tenant_id, str) and request_tenant_id.strip():
        tenant_identifiers.add(request_tenant_id.strip())

    claims = getattr(g, "verified_claims", None)
    if not isinstance(claims, VerifiedClaims):
        return tenant_identifiers

    if claims.active_tenant_ref is not None:
        if claims.active_tenant_ref.id:
            tenant_identifiers.add(claims.active_tenant_ref.id.strip())
        if claims.active_tenant_ref.alias:
            tenant_identifiers.add(claims.active_tenant_ref.alias.strip())

    for membership in claims.memberships:
        if membership.tenant_ref.id:
            tenant_identifiers.add(membership.tenant_ref.id.strip())
        if membership.tenant_ref.alias:
            tenant_identifiers.add(membership.tenant_ref.alias.strip())

    return tenant_identifiers


def _requested_tenant_identifiers(tenant_identifier: str) -> set[str]:
    normalized_tenant_identifier = str(tenant_identifier or "").strip()
    if not normalized_tenant_identifier:
        return set()

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.db import db

    tenant = (
        db.session.query(M8flowTenantModel)
        .filter(
            (M8flowTenantModel.id == normalized_tenant_identifier)
            | (M8flowTenantModel.slug == normalized_tenant_identifier)
        )
        .one_or_none()
    )
    if tenant is None:
        return {normalized_tenant_identifier}

    requested_identifiers = {normalized_tenant_identifier}
    for value in (tenant.id, tenant.slug):
        if isinstance(value, str) and value.strip():
            requested_identifiers.add(value.strip())
    return requested_identifiers


def ensure_request_can_access_tenant(
    tenant_identifier: str,
    *,
    forbidden_message: str,
) -> None:
    if is_super_admin_request():
        return

    # Master-realm requests are treated as global (no tenant scope). The
    # ``_m8flow_global_request`` flag is a legacy no-op (the sync global tenant
    # resolver that set it was retired); kept as a defensive hook. Master
    # super-admin access is covered by is_super_admin_request() above.
    if getattr(g, "_m8flow_global_request", False):
        return

    request_tenant_identifiers = _normalized_request_tenant_identifiers()
    if not request_tenant_identifiers:
        raise ApiError(
            error_code="forbidden",
            message=forbidden_message,
            status_code=403,
        )

    if request_tenant_identifiers.intersection(_requested_tenant_identifiers(tenant_identifier)):
        return

    raise ApiError(
        error_code="forbidden",
        message=forbidden_message,
        status_code=403,
    )
