# extensions/m8flow-backend/src/m8flow_backend/services/tenant_context_middleware.py
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import g, has_request_context, request

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authentication_service import AuthenticationService
from spiffworkflow_backend.services.authorization_service import AuthorizationService

try:
    from sqlalchemy.exc import InvalidRequestError
except ImportError:
    InvalidRequestError = None  # type: ignore[misc, assignment]

from m8flow_backend.canonical_db import get_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import (
    DEFAULT_TENANT_ID,
    PUBLIC_PATH_PREFIXES,
    TENANT_CLAIM,
    allow_missing_tenant_context,
    get_context_tenant_id,
    reset_context_tenant_id,
    set_context_tenant_id,
)

LOGGER = logging.getLogger(__name__)

def resolve_request_tenant() -> None:
    """
    Resolve tenant id for this Flask request and store it in:
      - g.m8flow_tenant_id
      - a ContextVar (for SQLAlchemy scoping, logging, etc.)

    Uses the canonical db (set by extensions/app.py). Tests that call this function
    must call set_canonical_db(db) in their app setup.

    Priority:
      1) JWT claim (m8flow_tenant_id)
      2) ContextVar tenant id (e.g. ASGI middleware)
      3) DEFAULT_TENANT_ID (only if allow_missing_tenant_context() is true)

    Validation:
      - If g already has tenant and token has a different tenant -> tenant_override_forbidden
      - If resolved tenant does not exist -> invalid_tenant

    Important:
      - Tenant resolution MUST happen even when auth is "disabled" for the request.
        Disabling auth should not disable tenant isolation.
    """
    db = get_canonical_db()
    if db is None:
        raise RuntimeError(
            "Canonical db not set; ensure app has been initialized (extensions/app.py calls set_canonical_db)."
        )

    if _is_public_request():
        g._m8flow_public_request = True
        return

    # NOTE: We do NOT return early when auth is disabled.
    # Auth-disabled should only mean "skip authorization checks",
    # not "skip tenant context resolution / isolation".

    existing_tenant = getattr(g, "m8flow_tenant_id", None)

    # If the request already has a tenant, ensure token (if any) doesn't conflict.
    if existing_tenant:
        token_tenant = _tenant_from_jwt_claim_cached(allow_decode=not AuthorizationService.should_disable_auth_for_request())
        if token_tenant and token_tenant != existing_tenant:
            raise ApiError(
                error_code="tenant_override_forbidden",
                message=f"Tenant override forbidden (request has '{existing_tenant}', token has '{token_tenant}').",
                status_code=400,
            )
        # Ensure ContextVar is also set for downstream code/hooks.
        if get_context_tenant_id() != existing_tenant:
            g._m8flow_ctx_token = set_context_tenant_id(existing_tenant)
        return

    tenant_id = _resolve_tenant_id()

    if not tenant_id:
        if allow_missing_tenant_context():
            tenant_id = DEFAULT_TENANT_ID
            _warn_missing_tenant_once(tenant_id)
        else:
            # Help debug which route is missing tenant resolution (e.g. swagger/openapi assets).
            try:
                path = getattr(request, "path", "") or ""
                method = getattr(request, "method", "") or ""
            except Exception:
                path = ""
                method = ""
            LOGGER.warning(
                "Tenant context not resolved for request method=%s path=%s (no JWT claim, no context tenant).",
                method,
                path,
            )
            raise ApiError(
                error_code="tenant_required",
                message=f"Tenant context could not be resolved from authentication data for path '{path}'.",
                status_code=400,
            )

    # Validate tenant exists in DB (your tests expect this).
    # Return 503 when DB is not bound so we never proceed with unvalidated tenant id.
    # Flask-SQLAlchemy may raise RuntimeError when model not bound; message check for backward compatibility.
    # InvalidRequestError used when applicable (SQLAlchemy mapping/registry errors).
    try:
        tenant = db.session.query(M8flowTenantModel).filter(M8flowTenantModel.id == tenant_id).one_or_none()
    except Exception as exc:
        _exc_tuple = (InvalidRequestError, RuntimeError) if InvalidRequestError is not None else (RuntimeError,)
        if isinstance(exc, _exc_tuple):
            if isinstance(exc, RuntimeError) and "not registered" not in str(exc):
                raise
            raise ApiError(
                error_code="service_unavailable",
                message="Tenant validation is temporarily unavailable (database not ready).",
                status_code=503,
            ) from exc
        raise
    if tenant is None:
        raise ApiError(
            error_code="invalid_tenant",
            message=f"Invalid tenant '{tenant_id}'.",
            status_code=401,
        )

    g.m8flow_tenant_id = tenant_id
    g._m8flow_ctx_token = set_context_tenant_id(tenant_id)


def teardown_request_tenant_context(_exc: Exception | None = None) -> None:
    token = getattr(g, "_m8flow_ctx_token", None)
    if token is not None:
        reset_context_tenant_id(token)
        g._m8flow_ctx_token = None


# -------------------------
# Internals
# -------------------------


def _is_public_request() -> bool:
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        return False
    return any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def _resolve_tenant_id() -> Optional[str]:
    # If auth is disabled, we should avoid decoding JWTs, but still
    # accept ContextVar or default behavior.
    allow_decode = not AuthorizationService.should_disable_auth_for_request()
    tenant_from_claim = _tenant_from_jwt_claim_cached(allow_decode=allow_decode)
    if tenant_from_claim:
        return tenant_from_claim
    tenant_from_ctx = _tenant_from_context_var()
    if tenant_from_ctx:
        return tenant_from_ctx

    # Fallback: if the IdP doesn't include tenant claims in the JWT, derive tenant from
    # the authentication identifier (which aligns with the Keycloak realm in this setup).
    # This is supported by runtime evidence: decoded token issuer realm == authentication_identifier
    # and tenant claims are absent.
    if allow_decode:
        derived = _authentication_identifier()
        if derived:
            LOGGER.debug(
                "Derived tenant from authentication_identifier fallback: %s",
                str(derived)[:80],
            )
            return derived
    return None


def _tenant_from_context_var() -> Optional[str]:
    return get_context_tenant_id()


def _warn_missing_tenant_once(default_tenant: str) -> None:
    if not has_request_context():
        return
    if getattr(g, "_m8flow_warned_missing_tenant", False):
        return
    g._m8flow_warned_missing_tenant = True
    LOGGER.warning("Tenant not resolved from auth; defaulting to '%s'.", default_tenant)


def _tenant_from_jwt_claim_cached(*, allow_decode: bool) -> Optional[str]:
    """
    Resolve tenant id from token claim, decoding at most once per request.
    If allow_decode is False, do not attempt to decode JWTs.
    """
    token = _token_from_request()
    if not token:
        return None

    cached_decoded = getattr(g, "_m8flow_decoded_token", None)
    cached_raw = getattr(g, "_m8flow_decoded_token_raw", None)
    if cached_decoded is not None and cached_raw == token:
        return _get_str_claims(cached_decoded, (TENANT_CLAIM,))

    if not allow_decode:
        return None

    try:
        decoded = AuthenticationService.parse_jwt_token(_authentication_identifier(), token)
    except Exception as exc:
        if not getattr(g, "_m8flow_warned_decode_token", False):
            g._m8flow_warned_decode_token = True
            LOGGER.warning("Failed to decode token for tenant resolution: %s", exc)
        return None

    g._m8flow_decoded_token = decoded
    g._m8flow_decoded_token_raw = token
    return _get_str_claims(decoded, (TENANT_CLAIM,))


def _get_str_claims(decoded: Any, claims: tuple[str, ...]) -> Optional[str]:
    if not isinstance(decoded, dict):
        return None
    for claim in claims:
        value = decoded.get(claim)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _token_from_request() -> Optional[str]:
    token = getattr(g, "token", None)
    if isinstance(token, str) and token:
        return token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip() or None

    access_cookie = request.cookies.get("access_token")
    if access_cookie:
        return access_cookie

    return None


def _authentication_identifier() -> str:
    cookie_identifier = request.cookies.get("authentication_identifier")
    if cookie_identifier:
        return cookie_identifier

    header_identifier = request.headers.get("SpiffWorkflow-Authentication-Identifier")
    if header_identifier:
        return header_identifier

    return DEFAULT_TENANT_ID
