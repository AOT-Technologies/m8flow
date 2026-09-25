"""Request-time tenant binding and PostgreSQL RLS session settings.

Resolves the active tenant once per request into flask.g and the tenant
ContextVar, then applies SET LOCAL so RLS matches the old host. Cookie
`m8flow_selected_tenant` is authoritative for shared-realm sessions.

This is the request-BINDING decision (which tenant id/RLS scope this
request runs under) -- distinct from `resolve.select(...)`, the per-session
SELECTION decision (which membership + groups the login/switch flow grants).
`resolve_request_tenant` does not call `select`: it only needs membership
*presence*, not enrichment, and runs on every request.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from flask import Flask, g, has_request_context, request
from sqlalchemy import event
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.auth.tenant_context import (
    SELECTED_TENANT_COOKIE_NAME,
    TENANT_CLAIM,
    TENANT_SELECTION_HEADER_NAME,
    is_concrete_tenant_id,
    reset_context_tenant_id,
    set_context_tenant_id,
    tenant_id_from_selected_cookie,
    tenant_override_for_super_admin,
)

LOGGER = logging.getLogger(__name__)

_AFTER_BEGIN_REGISTERED = False

# Single source of truth: base path prefixes when no WSGI path prefix is set.
# When SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX is set (e.g. "/api"), we also add
# prefix + each path so both prefixed and unprefixed deployments work.
_WSGI_PATH_PREFIX = os.getenv("SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX", "").strip()

# Base (unprefixed) paths that are exempt from tenant context resolution.
_BASE_TENANT_CONTEXT_EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/.well-known",
    "/favicon.ico",
    "/v1.0/ping",
    "/v1.0/m8flow/ping",
    "/v1.0/healthy",
    "/v1.0/status",
    "/v1.0/readyz",
    "/v1.0/openapi.json",
    "/v1.0/openapi.yaml",
    "/openapi.yaml",
    "/v1.0/ui",
    "/v1.0/static",
    # Connexion serves the spec + Swagger UI under the api base path.
    "/v1.0/m8flow/openapi.json",
    "/v1.0/m8flow/openapi.yaml",
    "/v1.0/m8flow/ui",
    "/v1.0/logout",
    "/v1.0/authentication-options",
    "/v1.0/login",
    "/v1.0/refresh",
    "/v1.0/tenants/check",
    "/v1.0/m8flow/tenant-login-url",
    "/v1.0/m8flow/organization-memberships",
    "/v1.0/m8flow/tenant-realms",
    "/v1.0/m8flow/create-tenant",
    "/m8flow/create-tenant",
    "/m8flow/organization-memberships",
    # Global tenant-management endpoints are authenticated, but they do not belong to a tenant realm.
    "/v1.0/m8flow/tenants",
    "/m8flow/tenants",
    # Public invitation accept/validate endpoints: unauthenticated and not tenant-scoped at the
    # request level (the invitation row carries its own tenant id).
    "/v1.0/m8flow/invitations",
    "/m8flow/invitations",
)

# See the path-prefix rule explained above `_WSGI_PATH_PREFIX`.
TENANT_CONTEXT_EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    _BASE_TENANT_CONTEXT_EXEMPT_PATH_PREFIXES
    + (
        tuple(f"{_WSGI_PATH_PREFIX}{p}" for p in _BASE_TENANT_CONTEXT_EXEMPT_PATH_PREFIXES)
        if _WSGI_PATH_PREFIX
        else ()
    )
)

# Path suffixes for pre-login tenant selection (no tenant context required). Also included in
# TENANT_CONTEXT_EXEMPT_PATH_PREFIXES above with /v1.0 prefix.
PRE_LOGIN_TENANT_SELECTION_PATH_PREFIXES: tuple[str, ...] = ("/tenants/check", "/m8flow/tenant-login-url")

# Backward-compatible aliases while call sites migrate to clearer naming.
PUBLIC_PATH_PREFIXES = TENANT_CONTEXT_EXEMPT_PATH_PREFIXES
TENANT_PUBLIC_PATH_PREFIXES = PRE_LOGIN_TENANT_SELECTION_PATH_PREFIXES


def path_matches_prefix(path: str, prefix: str) -> bool:
    """
    True when path is exactly prefix or is a child path of prefix.

    This avoids prefix-collision bugs like `/v1.0/login_return` matching
    `/v1.0/login`.
    """
    if path == prefix:
        return True
    normalized_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
    return path.startswith(normalized_prefix)


def path_matches_any_prefix(path: str, prefixes: Iterable[str]) -> bool:
    """True when path matches any API prefix using segment-boundary semantics."""
    return any(path_matches_prefix(path, prefix) for prefix in prefixes)


def _request_uses_master_realm_without_tenant_context() -> bool:
    """Detect master-realm requests when the resolver did not tag the request."""
    if not has_request_context():
        return False

    decoded_token = getattr(g, "_m8flow_decoded_token", None)
    if not isinstance(decoded_token, dict):
        decoded_token = getattr(g, "decoded_token", None)
    if not isinstance(decoded_token, dict):
        try:
            token: str | None = getattr(g, "token", None) if isinstance(getattr(g, "token", None), str) else None
            if not token:
                auth_header = (request.headers.get("Authorization") or "").strip()
                if auth_header.startswith("Bearer ") and len(auth_header) > 7:
                    token = auth_header[7:].strip() or None
            if not token:
                token = request.cookies.get("access_token")
            if token:
                from m8flow_backend.auth import decode_auth_token

                payload = decode_auth_token(token)
                if isinstance(payload, dict):
                    decoded_token = payload
                    g._m8flow_decoded_token = payload
        except Exception:
            decoded_token = None

    if not isinstance(decoded_token, dict):
        return False

    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.base.models import VerifiedClaims

    verified_claims = getattr(g, "verified_claims", None)
    if not isinstance(verified_claims, VerifiedClaims):
        # Not every path that reaches here has a full VerifiedClaims stored --
        # a local HS256 token (decode_auth_token's "local token" branch) never
        # gets one, and its `iss` can still be a Keycloak-shaped realm URL
        # (identity_helpers.py's local-user sync sets `service`, which becomes
        # `iss`, to exactly that shape). is_master_issuer only reads
        # .issuer/.jwt_claims, so a minimal wrapper around the raw payload
        # preserves behavior without needing a real verified session.
        verified_claims = VerifiedClaims(
            subject=str(decoded_token.get("sub") or ""),
            issuer=str(decoded_token.get("iss") or ""),
            jwt_claims=decoded_token,
        )

    return get_auth_provider().is_master_issuer(verified_claims)


def is_tenant_context_exempt_request() -> bool:
    if not has_request_context():
        return False
    return bool(
        getattr(g, "_m8flow_tenant_context_exempt_request", False)
        or getattr(g, "_m8flow_public_request", False)
        # Master-realm sign-ins, /login_return callbacks, and other
        # intentionally tenant-less requests are treated the same as
        # path-exempt requests: tenant-scoped DB queries (e.g.
        # ReferenceCacheModel.basic_query) skip the tenant filter and
        # return the global view, instead of raising "missing tenant
        # context" for users who legitimately have no tenant. That is now
        # detected by _request_uses_master_realm_without_tenant_context();
        # the ``g._m8flow_global_request`` flag below is a legacy no-op (the
        # sync global tenant resolver that set it was retired) kept as a
        # defensive hook -- see the platform-host-100 map follow-up.
        or getattr(g, "_m8flow_global_request", False)
        or _request_uses_master_realm_without_tenant_context()
    )


def is_public_request() -> bool:
    return is_tenant_context_exempt_request()


def is_super_admin_request() -> bool:
    """Zero-arg convenience wrapper over `authorization.actor_is_super_admin(g.user)`
    for the many call sites that only have request context, not a `user` in hand."""
    if not has_request_context():
        return False
    from m8flow_backend.authorization import actor_is_super_admin

    return actor_is_super_admin(getattr(g, "user", None))


def require_tenant_id(user, *, allow_super_admin_override: bool = True) -> str:
    """The one 'resolve a concrete tenant id for this request or 400' helper.
    Super-admins may select any tenant via `tenantId`/`tenant_id`
    (allow_super_admin_override); everyone else -- and a super-admin who didn't
    override -- needs the `m8flow_selected_tenant` cookie. Raises tenant_required
    (400 ApiError) if no concrete tenant resolves. Sets g.m8flow_tenant_id as a
    side effect so tenant_context.get_tenant_id() and RLS session scoping see
    the same value."""
    from m8flow_backend.authorization import actor_is_super_admin

    super_admin = actor_is_super_admin(user)
    override = tenant_override_for_super_admin(is_super_admin=super_admin) if allow_super_admin_override else None
    tenant_id = override or tenant_id_from_selected_cookie()
    if not tenant_id:
        raise ApiError("tenant_required", "m8flow_selected_tenant cookie is required", 400)
    g.m8flow_tenant_id = tenant_id
    return tenant_id


def resolve_read_tenant_id(user) -> str | None:
    """Read-side sibling of `require_tenant_id`: returns None ("all tenants") for a
    super-admin who selected no concrete tenant, instead of raising tenant_required.

    Non-super-admins are delegated to `require_tenant_id` unchanged, so tenant
    isolation for them is untouched. A None return means "drop the tenant filter",
    which is only safe because the caller has been verified super-admin here -- the
    same posture as `workflow.count_active_process_instances` and
    `home_controller._resolve_own_tenant_id`, which this generalizes.

    Writes must keep using `require_tenant_id` / `require_catalog_write_tenant_id`:
    a write has to land in exactly one tenant.
    """
    from m8flow_backend.authorization import actor_is_super_admin

    if not actor_is_super_admin(user):
        return require_tenant_id(user)

    tenant_id = tenant_override_for_super_admin(is_super_admin=True) or tenant_id_from_selected_cookie()
    if tenant_id:
        g.m8flow_tenant_id = tenant_id
        return tenant_id
    return None


def require_catalog_write_tenant_id(
    user,
    *,
    explicit_tenant_id: str | None = None,
) -> str:
    """Concrete tenant for catalog / create-from-template writes (M8F-479).

    Non-super-admins ignore body ``m8f_tenant_id`` and use ``require_tenant_id``.

    Super-admins may bind via body ``m8f_tenant_id``, ``?tenantId`` / ``tenant_id``,
    or the ``m8flow_selected_tenant`` cookie. Body and resolved context must agree
    when both are present; otherwise raise ``tenant_override_forbidden``. Missing
    concrete tenant raises ``tenant_required``.
    """
    from m8flow_backend.authorization import actor_is_super_admin

    body_raw = explicit_tenant_id.strip() if isinstance(explicit_tenant_id, str) else ""
    body_tenant: str | None = None
    if body_raw:
        if not is_concrete_tenant_id(body_raw):
            raise ApiError(
                "invalid_tenant",
                f"Invalid tenant '{body_raw}'.",
                400,
            )
        body_tenant = body_raw

    if not actor_is_super_admin(user):
        return require_tenant_id(user)

    override = tenant_override_for_super_admin(is_super_admin=True)
    override_tenant = (
        override.strip()
        if isinstance(override, str) and override.strip() and is_concrete_tenant_id(override.strip())
        else None
    )
    cookie = tenant_id_from_selected_cookie()
    cookie_tenant = (
        cookie.strip()
        if isinstance(cookie, str) and cookie.strip() and is_concrete_tenant_id(cookie.strip())
        else None
    )
    resolved = override_tenant or cookie_tenant

    if body_tenant is not None and resolved is not None:
        body_canonical = _canonical(body_tenant)
        resolved_canonical = _canonical(resolved)
        if body_canonical != resolved_canonical:
            raise ApiError(
                "tenant_override_forbidden",
                "Super-admin workflow write request conflicts with the current tenant context.",
                400,
            )
        return bind_request_tenant(body_canonical)

    if body_tenant is not None:
        return bind_request_tenant(body_tenant)

    if resolved is not None:
        return bind_request_tenant(resolved)

    raise ApiError(
        "tenant_required",
        "Select a tenant before creating, updating, or executing a workflow.",
        400,
    )


def _cookie_tenant() -> str | None:
    raw = request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _header_tenant() -> str | None:
    raw = request.headers.get(TENANT_SELECTION_HEADER_NAME)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _decoded_payload() -> dict | None:
    for attr in ("decoded_token", "_m8flow_decoded_token"):
        payload = getattr(g, attr, None)
        if isinstance(payload, dict):
            return payload
    return None


def _canonical(tenant_id: str) -> str:
    from m8flow_backend.auth.canonicalize import _canonical_tenant_id_from_identifiers

    return _canonical_tenant_id_from_identifiers(tenant_id) or tenant_id.strip()


def _claims_match_cookie(claims, cookie: str) -> bool:
    """Neutral replacement for the former ``_payload_matches_cookie`` (auth-
    provider-seam wayfinder map, ticket 10): reads ``VerifiedClaims.memberships``
    instead of destructuring the raw ``organization`` claim."""
    from m8flow_backend.integrations.auth.base.models import VerifiedClaims

    if not isinstance(claims, VerifiedClaims):
        return False
    from m8flow_backend.auth.canonicalize import current_tenant_identifiers
    from m8flow_backend.auth.identity_helpers import claims_user_belongs_to_tenant

    selected = current_tenant_identifiers(cookie) or {cookie}
    for membership in claims.memberships:
        org_ids: set[str] = set()
        if membership.tenant_ref.alias:
            org_ids.add(membership.tenant_ref.alias)
        if membership.tenant_ref.id:
            org_ids.add(membership.tenant_ref.id)
        if org_ids.intersection(selected):
            return True
    return claims_user_belongs_to_tenant(claims, tenant_id=cookie, tenant_identifiers=selected)


def _jwt_tenant(claims, payload: dict | None) -> str | None:
    """Neutral replacement for the former raw-payload-only lookup (auth-
    provider-seam wayfinder map, ticket 10): ``VerifiedClaims.active_tenant_ref``
    carries the finalized/active tenant. The ``TENANT_CLAIM`` (default
    ``m8flow_tenant_id``, overridable via ``M8FLOW_TENANT_CLAIM``) fallback
    stays a raw-payload read on purpose -- it's a host-configurable generic
    claim name, not Keycloak-shape parsing, so it can't be expressed as a
    fixed VerifiedClaims field."""
    from m8flow_backend.integrations.auth.base.models import VerifiedClaims

    if isinstance(claims, VerifiedClaims) and claims.active_tenant_ref is not None:
        candidate = claims.active_tenant_ref.id or claims.active_tenant_ref.alias
        if candidate and is_concrete_tenant_id(candidate):
            return candidate
    if isinstance(payload, dict):
        explicit = payload.get(TENANT_CLAIM)
        if isinstance(explicit, str) and is_concrete_tenant_id(explicit.strip()):
            return explicit.strip()
    return None


def _user_belongs(tenant_id: str) -> bool:
    from m8flow_backend.auth.identity_helpers import user_belongs_to_current_tenant

    user = getattr(g, "user", None)
    if user is None:
        return False
    return user_belongs_to_current_tenant(user, tenant_id=tenant_id)


def bind_request_tenant(tenant_id: str) -> str:
    """Stamp flask.g and the ContextVar with a concrete tenant id."""
    canonical = _canonical(tenant_id)
    g.m8flow_tenant_id = canonical
    existing = getattr(g, "_m8flow_ctx_token", None)
    if existing is not None:
        try:
            reset_context_tenant_id(existing)
        except Exception:
            LOGGER.debug("Could not reset previous tenant ContextVar token", exc_info=True)
    g._m8flow_ctx_token = set_context_tenant_id(canonical)
    return canonical


def mark_tenant_exempt() -> None:
    g._m8flow_tenant_context_exempt_request = True


def _path_is_exempt() -> bool:
    path = getattr(request, "path", "") or ""
    return path_matches_any_prefix(path, TENANT_CONTEXT_EXEMPT_PATH_PREFIXES)


def resolve_request_tenant() -> None:
    """Bind the active tenant for this request, or fail closed.

    Order: super-admin tenantId override or exempt; selected-tenant cookie
    when it matches shared-realm membership; JWT tenant claim;
    x-m8flow-tenant-id when the user belongs; cookie fallback; fail closed
    for authenticated non-exempt paths.
    """
    if is_super_admin_request():
        override = tenant_override_for_super_admin(is_super_admin=True)
        if is_concrete_tenant_id(override):
            bind_request_tenant(str(override).strip())
            return
        cookie = request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
        if isinstance(cookie, str) and is_concrete_tenant_id(cookie.strip()):
            bind_request_tenant(cookie.strip())
            return
        mark_tenant_exempt()
        return

    payload = _decoded_payload()
    claims = getattr(g, "verified_claims", None)
    cookie = _cookie_tenant()
    if cookie and _claims_match_cookie(claims, cookie):
        bind_request_tenant(cookie)
        return

    jwt_tenant = _jwt_tenant(claims, payload)
    if jwt_tenant:
        bind_request_tenant(jwt_tenant)
        return

    # Anonymous callers: do not treat a leftover tenant cookie/header as a
    # membership override failure (400). Exempt paths stay open; protected
    # routes fail at auth (401) instead.
    user = getattr(g, "user", None)
    if user is None:
        if _path_is_exempt():
            mark_tenant_exempt()
        return

    header = _header_tenant()
    if header:
        if not _user_belongs(header):
            raise ApiError(
                "tenant_override_forbidden",
                f"Tenant override forbidden via {TENANT_SELECTION_HEADER_NAME}; "
                "the authenticated user does not belong to that tenant.",
                400,
            )
        bind_request_tenant(header)
        return

    if cookie:
        if not _user_belongs(cookie):
            raise ApiError(
                "tenant_override_forbidden",
                f"Tenant override forbidden via {SELECTED_TENANT_COOKIE_NAME}; "
                "the authenticated user does not belong to that tenant.",
                400,
            )
        bind_request_tenant(cookie)
        return

    if _path_is_exempt():
        mark_tenant_exempt()
        return

    raise ApiError(
        "tenant_required",
        "Tenant context could not be resolved from authentication data "
        f"for path '{request.path}'.",
        400,
    )


def _exec_local(connection, sql: str, params: tuple | None = None) -> None:
    exec_driver_sql = getattr(connection, "exec_driver_sql", None)
    if callable(exec_driver_sql):
        if params is None:
            exec_driver_sql(sql)
        else:
            exec_driver_sql(sql, params)
        return

    raw = getattr(connection, "connection", connection)
    driver = getattr(raw, "driver_connection", raw)
    if driver is None:
        return
    cursor = driver.cursor()
    try:
        cursor.execute(sql, params)
    finally:
        cursor.close()


def _set_local_guc(connection, name: str, value: str) -> None:
    """Apply a transaction-local GUC the way SET LOCAL would.

    PostgreSQL ``SET`` / ``SET LOCAL`` cannot take bind parameters. psycopg3
    still emits ``$1``, the server raises SyntaxError, and the request
    transaction is aborted so every later query 500s. ``set_config(...,
    is_local=true)`` is the parameterized equivalent.
    """
    _exec_local(connection, "SELECT set_config(%s, %s, true)", (name, value))


def apply_postgres_rls(connection) -> None:
    """SET LOCAL RLS GUC values for the current PostgreSQL transaction."""
    dialect = getattr(getattr(connection, "dialect", None), "name", "")
    if dialect != "postgresql":
        return

    from m8flow_backend.auth.canonicalize import current_tenant_id_or_none

    tenant_id = current_tenant_id_or_none()
    super_admin = is_super_admin_request()

    if super_admin:
        _set_local_guc(connection, "app.bypass_rls", "on")
        if tenant_id:
            _set_local_guc(connection, "app.current_tenant", tenant_id)
        return

    if is_tenant_context_exempt_request():
        return
    if not tenant_id:
        return
    _set_local_guc(connection, "app.current_tenant", tenant_id)


def apply_postgres_rls_to_request_session() -> None:
    if not has_request_context():
        return
    session = getattr(g, "db_session", None)
    if session is None:
        return
    try:
        apply_postgres_rls(session.connection())
    except Exception:
        LOGGER.debug("Could not apply PostgreSQL RLS settings on the request session", exc_info=True)
        try:
            session.rollback()
        except Exception:
            LOGGER.debug("Could not roll back after RLS GUC failure", exc_info=True)


def _on_session_after_begin(session: Session, _transaction, connection) -> None:
    apply_postgres_rls(connection)


def _register_after_begin() -> None:
    global _AFTER_BEGIN_REGISTERED
    if _AFTER_BEGIN_REGISTERED:
        return
    event.listen(Session, "after_begin", _on_session_after_begin)
    _AFTER_BEGIN_REGISTERED = True


def install_tenant_runtime(app: Flask) -> None:
    """Resolve tenant after auth and keep PostgreSQL RLS session GUCs in sync."""
    _register_after_begin()

    @app.before_request
    def _bind_request_tenant() -> None:
        resolve_request_tenant()
        apply_postgres_rls_to_request_session()

    @app.teardown_request
    def _end_request_tenant(_exc: BaseException | None) -> None:
        token = getattr(g, "_m8flow_ctx_token", None)
        if token is not None:
            reset_context_tenant_id(token)
            g._m8flow_ctx_token = None
