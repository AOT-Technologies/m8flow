# m8flow-backend/src/m8flow_backend/services/tenant_context_middleware.py
from __future__ import annotations

import ast
import base64
import logging
import os
from typing import Any, Optional
from urllib.parse import unquote

from flask import g, has_request_context, request
from sqlalchemy import or_

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
    TENANT_CONTEXT_EXEMPT_PATH_PREFIXES,
    TENANT_CLAIM,
    allow_missing_tenant_context,
    get_context_tenant_id,
    path_matches_any_prefix,
    reset_context_tenant_id,
    set_context_tenant_id,
)

LOGGER = logging.getLogger(__name__)


def _is_master_login_return_request(tenant_id: str | None) -> bool:
    try:
        path = (getattr(request, "path", "") or "").strip()
    except Exception:
        return False
    return tenant_id == "master" and "/login_return" in path


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
            "Canonical db not set; ensure app has been initialized (set_canonical_db must be called during startup)."
        )

    if _is_tenant_context_exempt_request():
        g._m8flow_tenant_context_exempt_request = True
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

    if _is_master_login_return_request(tenant_id):
        LOGGER.debug("Skipping tenant validation for master realm login_return callback.")
        return

    # Validate tenant exists in DB (your tests expect this).
    # Return 503 when DB is not bound so we never proceed with unvalidated tenant id.
    # Flask-SQLAlchemy may raise RuntimeError when model not bound; message check for backward compatibility.
    # InvalidRequestError used when applicable (SQLAlchemy mapping/registry errors).
    try:
        tenant = (
            db.session.query(M8flowTenantModel)
            .filter(or_(M8flowTenantModel.id == tenant_id, M8flowTenantModel.slug == tenant_id))
            .one_or_none()
        )
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

    canonical_tenant_id = tenant.id
    g.m8flow_tenant_id = canonical_tenant_id
    g._m8flow_ctx_token = set_context_tenant_id(canonical_tenant_id)


def teardown_request_tenant_context(_exc: Exception | None = None) -> None:
    token = getattr(g, "_m8flow_ctx_token", None)
    if token is not None:
        reset_context_tenant_id(token)
        g._m8flow_ctx_token = None


# -------------------------
# Internals
# -------------------------


def _is_tenant_context_exempt_request() -> bool:
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        return False
    return path_matches_any_prefix(path, TENANT_CONTEXT_EXEMPT_PATH_PREFIXES)


def _is_public_request() -> bool:
    return _is_tenant_context_exempt_request()


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

    # Fallback: derive tenant from authentication identifier.
    # For auth-disabled paths (e.g., login_return), only trust explicit identifiers
    # from state/cookies/headers and do not default implicitly.
    derived = _authentication_identifier(include_default=allow_decode)
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
        authentication_identifier = _authentication_identifier() or DEFAULT_TENANT_ID
        decoded = AuthenticationService.parse_jwt_token(authentication_identifier, token)
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


def _decode_state_authentication_identifier(state: str | None) -> Optional[str]:
    if not state:
        return None
    try:
        raw = base64.b64decode(unquote(state)).decode("utf-8")
        state_dict = ast.literal_eval(raw)
    except Exception:
        return None
    if not isinstance(state_dict, dict):
        return None
    identifier = state_dict.get("authentication_identifier")
    if isinstance(identifier, str) and identifier.strip():
        return identifier
    return None


def _authentication_identifier(*, include_default: bool = True) -> Optional[str]:
    path = (getattr(request, "path", "") or "").strip()
    if "/login_return" in path:
        state_identifier = _decode_state_authentication_identifier(request.args.get("state"))
        if state_identifier:
            return state_identifier

    cookie_identifier = request.cookies.get("authentication_identifier")
    if cookie_identifier:
        return cookie_identifier

    header_identifier = request.headers.get("SpiffWorkflow-Authentication-Identifier")
    if header_identifier:
        return header_identifier

    if include_default:
        return DEFAULT_TENANT_ID
    return None
