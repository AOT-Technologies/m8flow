# m8flow-backend/src/m8flow_backend/services/tenant_context_middleware.py
from __future__ import annotations

import ast
import base64
import logging
from typing import Any
from typing import Optional
from urllib.parse import unquote

from flask import g, request
from sqlalchemy import or_

from m8flow_backend.services.tenant_identity_helpers import authentication_identifier_from_payload
from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer
from m8flow_backend.services.tenant_identity_helpers import organization_memberships_from_payload
from m8flow_backend.services.tenant_identity_helpers import payload_user_belongs_to_tenant
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.services.tenant_identity_helpers import user_belongs_to_current_tenant
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authentication_service import AuthenticationService
from spiffworkflow_backend.services.authorization_service import AuthorizationService

try:
    from sqlalchemy.exc import InvalidRequestError
except ImportError:
    InvalidRequestError = None  # type: ignore[misc, assignment]

from m8flow_backend.canonical_db import get_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer
from m8flow_backend.tenancy import (
    SELECTED_TENANT_COOKIE_NAME,
    TENANT_CLAIM,
    TENANT_CONTEXT_EXEMPT_PATH_PREFIXES,
    get_context_tenant_id,
    is_concrete_tenant_id,
    is_legacy_placeholder_tenant_id,
    path_matches_any_prefix,
    reset_context_tenant_id,
    set_context_tenant_id,
)

LOGGER = logging.getLogger(__name__)
TENANT_SELECTION_HEADER_NAME = "x-m8flow-tenant-id"
MASTER_REALM_IDENTIFIER = "master"
SUPER_ADMIN_ROLE = "super-admin"


def _shared_realm_identifier() -> str:
    from m8flow_backend.config import shared_realm_name

    return shared_realm_name()


def _master_realm_identifier() -> str:
    from m8flow_backend.config import master_realm_name

    return master_realm_name()


def _decoded_payload_from_bearer_token_without_verification(token: str | None = None) -> dict[str, Any] | None:
    """Decode the bearer token payload without signature verification for tenant routing."""
    bearer_token = token or _token_from_request()
    if not bearer_token:
        return None

    try:
        import jwt

        payload = jwt.decode(
            bearer_token,
            options={"verify_signature": False, "verify_exp": False},
        )
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    g._m8flow_decoded_token = payload
    g._m8flow_decoded_token_raw = bearer_token
    return payload


def _authenticated_tenant_id_from_payload(payload: dict[str, Any] | None) -> str | None:
    """
    Resolve the tenant for authenticated requests.

    Prefer the explicit JWT tenant claim when present. If the claim is missing,
    fall back to the broader payload-based resolver so legacy organization-only
    tokens keep working.
    """
    if not isinstance(payload, dict):
        return None

    explicit_tenant_id = payload.get(TENANT_CLAIM)
    if isinstance(explicit_tenant_id, str) and explicit_tenant_id.strip():
        payload_without_organization = dict(payload)
        payload_without_organization.pop("organization", None)
        return tenant_id_from_payload(payload_without_organization)

    return tenant_id_from_payload(payload)


def resolve_request_tenant() -> None:
    """
    Resolve tenant id for this Flask request and store it in:
      - g.m8flow_tenant_id
      - a ContextVar (for SQLAlchemy scoping, logging, etc.)

    Uses the canonical db (set by extensions/app.py). Tests that call this function
    must call set_canonical_db(db) in their app setup.

    Priority:
      1) JWT claim (m8flow_tenant_id)
      2) Request tenant header (x-m8flow-tenant-id), validated against the authenticated user
      3) ContextVar tenant id (e.g. ASGI middleware)
      4) Selected tenant cookie for shared-realm requests
      5) No implicit default tenant fallback; exempt/public requests remain global/public.

    Validation:
      - If g already has a concrete tenant and the request resolves a different tenant -> tenant_override_forbidden
      - Header-selected tenants must belong to the authenticated user
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

    # Master realm super-admin is global by design and must bypass tenant scoping.
    if _is_master_super_admin_request():
        g._m8flow_tenant_context_exempt_request = True
        g._m8flow_public_request = False
        g._m8flow_super_admin_request = True
        return

    # NOTE: We do NOT return early when auth is disabled.
    # Auth-disabled should only mean "skip authorization checks",
    # not "skip tenant context resolution / isolation".

    tenant_resolution = _resolve_tenant_details()
    existing_tenant = getattr(g, "m8flow_tenant_id", None)
    tenant_id = tenant_resolution["tenant_id"]
    tenant_source = tenant_resolution["source"]
    tenant_reason = tenant_resolution["reason"]
    jwt_tenant_id = tenant_resolution["jwt_tenant_id"]
    header_tenant_id = tenant_resolution["header_tenant_id"]
    existing_tenant_is_concrete = is_concrete_tenant_id(existing_tenant)

    if tenant_source in {"master_realm", "login_return"}:
        g._m8flow_global_request = True
        g.m8flow_tenant_id = None
        _log_tenant_resolution(
            tenant_id=None,
            source=tenant_source,
            reason=tenant_reason,
            jwt_tenant_id=jwt_tenant_id,
            header_tenant_id=header_tenant_id,
        )
        return

    if existing_tenant_is_concrete and not tenant_id:
        tenant_id = existing_tenant
        tenant_source = "existing_request_tenant"
        tenant_reason = "Using existing request tenant context."

    if is_legacy_placeholder_tenant_id(existing_tenant) and is_concrete_tenant_id(tenant_id):
        tenant_reason = f"{tenant_reason} Overrode legacy default tenant context."

    if (
        existing_tenant_is_concrete
        and tenant_id
        and existing_tenant not in current_tenant_identifiers(tenant_id)
    ):
        _log_tenant_resolution(
            tenant_id=existing_tenant,
            source="request_context_conflict",
            reason="Existing request tenant conflicts with resolved tenant.",
            jwt_tenant_id=jwt_tenant_id,
            header_tenant_id=header_tenant_id,
        )
        raise ApiError(
            error_code="tenant_override_forbidden",
            message=f"Tenant override forbidden (request has '{existing_tenant}', token/header resolved '{tenant_id}').",
            status_code=400,
        )

    if _is_tenant_context_exempt_request() and tenant_id in {None, "public"}:
        _log_tenant_resolution(
            tenant_id=tenant_id,
            source="tenant_context_exempt",
            reason="Request path is exempt from tenant resolution and no authenticated tenant was resolved.",
            jwt_tenant_id=jwt_tenant_id,
            header_tenant_id=header_tenant_id,
        )
        g._m8flow_tenant_context_exempt_request = True
        g._m8flow_public_request = True
        return

    if not tenant_id:
        path = getattr(request, "path", "") or ""
        _log_tenant_resolution(
            tenant_id=None,
            source="unresolved",
            reason="No tenant candidate was available.",
            jwt_tenant_id=jwt_tenant_id,
            header_tenant_id=header_tenant_id,
        )
        LOGGER.warning(
            "Tenant context not resolved for request path=%s (no JWT claim, no header tenant, no context tenant).",
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
    _log_tenant_resolution(
        tenant_id=canonical_tenant_id,
        source=tenant_source,
        reason=tenant_reason,
        jwt_tenant_id=jwt_tenant_id,
        header_tenant_id=header_tenant_id,
    )


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
    return _resolve_tenant_details()["tenant_id"]


def _resolve_tenant_details() -> dict[str, Optional[str]]:
    # Auth-disabled endpoints like /v1.0/status still need to honor an incoming JWT
    # tenant claim. Decoding is safe here because token parsing is already guarded
    # and returns None on failure.

    # login_return from the master realm does not carry a tenant — detect this
    # early before attempting JWT decoding so it doesn't raise tenant_required.
    try:
        path = getattr(request, "path", "") or ""
        if "/login_return" in path:
            state_auth_id = _decode_state_authentication_identifier(request.args.get("state"))
            if state_auth_id and state_auth_id == _master_realm_identifier():
                return {
                    "tenant_id": None,
                    "source": "master_realm",
                    "reason": "login_return from master realm does not use tenant context.",
                    "jwt_tenant_id": None,
                    "header_tenant_id": _tenant_from_request_header(),
                }
    except Exception:
        pass

    allow_decode = True
    tenant_from_claim = _tenant_from_jwt_claim_cached(allow_decode=allow_decode)
    selected_tenant_override = _selected_tenant_override_for_shared_multi_org_token(
        getattr(g, "_m8flow_decoded_token", None)
    )
    if selected_tenant_override:
        return {
            "tenant_id": selected_tenant_override,
            "source": "selected_tenant_cookie",
            "reason": "Resolved tenant from selected tenant cookie for shared-realm multi-organization token.",
            "jwt_tenant_id": tenant_from_claim,
            "header_tenant_id": _tenant_from_request_header(),
        }
    if tenant_from_claim:
        return {
            "tenant_id": tenant_from_claim,
            "source": "jwt_claim",
            "reason": "Resolved tenant from JWT m8flow_tenant_id claim.",
            "jwt_tenant_id": tenant_from_claim,
            "header_tenant_id": _tenant_from_request_header(),
        }

    decoded_token = getattr(g, "_m8flow_decoded_token", None)
    if isinstance(decoded_token, dict):
        authentication_identifier = authentication_identifier_from_payload(decoded_token)
        issuer_realm = extract_realm_from_issuer(decoded_token.get("iss"))
        if authentication_identifier == _master_realm_identifier() or issuer_realm == _master_realm_identifier():
            return {
                "tenant_id": None,
                "source": "master_realm",
                "reason": "Authenticated master-realm request does not use tenant context.",
                "jwt_tenant_id": None,
                "header_tenant_id": _tenant_from_request_header(),
            }

    header_tenant_id = _tenant_from_request_header()
    if header_tenant_id:
        user = getattr(g, "user", None)
        user_id = getattr(user, "id", None) if user is not None else None
        if user is None or not user_belongs_to_current_tenant(user, tenant_id=header_tenant_id):
            raise ApiError(
                error_code="tenant_override_forbidden",
                message=(
                    f"Tenant override forbidden via {TENANT_SELECTION_HEADER_NAME}; "
                    "the authenticated user does not belong to that tenant."
                ),
                status_code=400,
            )
        return {
            "tenant_id": header_tenant_id,
            "source": "request_header",
            "reason": f"Resolved tenant from {TENANT_SELECTION_HEADER_NAME} after validating authenticated user {user_id}.",
            "jwt_tenant_id": None,
            "header_tenant_id": header_tenant_id,
        }

    tenant_from_ctx = _tenant_from_context_var()
    if tenant_from_ctx:
        return {
            "tenant_id": tenant_from_ctx,
            "source": "context_var",
            "reason": "Resolved tenant from context variable.",
            "jwt_tenant_id": None,
            "header_tenant_id": header_tenant_id,
        }

    selected_tenant = _selected_tenant_from_request()
    if selected_tenant:
        return {
            "tenant_id": selected_tenant,
            "source": "selected_tenant_cookie",
            "reason": "Resolved tenant from selected tenant cookie.",
            "jwt_tenant_id": None,
            "header_tenant_id": header_tenant_id,
        }

    # Final fallback: /login_return is the OAuth callback. The before_request hook fires BEFORE
    # the handler exchanges the auth code for a JWT, so when no other resolution path produced a
    # tenant we must NOT raise tenant_required here — the handler itself resolves the tenant
    # from the issued token (or routes shared-realm multi-org users to tenant selection).
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        path = ""
    if "/login_return" in path:
        return {
            "tenant_id": None,
            "source": "login_return",
            "reason": (
                "login_return is the OAuth callback; tenant context is established by the "
                "handler after the auth code is exchanged for a JWT."
            ),
            "jwt_tenant_id": None,
            "header_tenant_id": header_tenant_id,
        }

    return {
        "tenant_id": None,
        "source": "unresolved",
        "reason": "No tenant candidate was available.",
        "jwt_tenant_id": None,
        "header_tenant_id": header_tenant_id,
    }


def _tenant_from_context_var() -> Optional[str]:
    return get_context_tenant_id()


def _tenant_from_request_header() -> Optional[str]:
    header_tenant = request.headers.get(TENANT_SELECTION_HEADER_NAME)
    if isinstance(header_tenant, str) and header_tenant.strip():
        return header_tenant.strip()
    return None


def _log_tenant_resolution(
    *,
    tenant_id: str | None,
    source: str,
    reason: str,
    jwt_tenant_id: str | None,
    header_tenant_id: str | None,
) -> None:
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        path = ""

    user = getattr(g, "user", None)
    user_id = getattr(user, "id", None) if user is not None else None

    LOGGER.debug(
        "tenant_resolution: path=%s authenticated_user_id=%s jwt_m8flow_tenant_id=%s header_tenant_id=%s resolved_active_tenant_id=%s source=%s reason=%s",
        path,
        user_id,
        jwt_tenant_id,
        header_tenant_id,
        tenant_id,
        source,
        reason,
    )


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
    if cached_decoded is not None and (cached_raw is None or cached_raw == token):
        return _authenticated_tenant_id_from_payload(cached_decoded)

    if not allow_decode:
        return None

    unverified_decoded = _decoded_payload_from_bearer_token_without_verification(token)
    if isinstance(unverified_decoded, dict):
        return _authenticated_tenant_id_from_payload(unverified_decoded)

    authentication_identifier = _authentication_identifier()
    if not authentication_identifier:
        return None

    try:
        decoded = AuthenticationService.parse_jwt_token(authentication_identifier, token)
    except Exception as exc:
        if not getattr(g, "_m8flow_warned_decode_token", False):
            g._m8flow_warned_decode_token = True
            LOGGER.warning("Failed to decode token for tenant resolution: %s", exc)
        return None

    g._m8flow_decoded_token = decoded
    g._m8flow_decoded_token_raw = token
    return _authenticated_tenant_id_from_payload(decoded)


def _decoded_token_cached(*, allow_decode: bool) -> Optional[dict[str, Any]]:
    token = _token_from_request()
    if not token:
        return None

    cached_decoded = getattr(g, "_m8flow_decoded_token", None)
    cached_raw = getattr(g, "_m8flow_decoded_token_raw", None)
    if isinstance(cached_decoded, dict) and cached_raw == token:
        return cached_decoded

    if not allow_decode:
        return None

    try:
        authentication_identifier = _authentication_identifier()
        if not authentication_identifier:
            return None
        decoded = AuthenticationService.parse_jwt_token(authentication_identifier, token)
    except Exception as exc:
        if not getattr(g, "_m8flow_warned_decode_token", False):
            g._m8flow_warned_decode_token = True
            LOGGER.warning("Failed to decode token for tenant resolution: %s", exc)
        return None

    if isinstance(decoded, dict):
        g._m8flow_decoded_token = decoded
        g._m8flow_decoded_token_raw = token
        return decoded
    return None


def _is_master_super_admin_request() -> bool:
    user = getattr(g, "user", None)
    user_groups = getattr(user, "groups", None)
    if isinstance(user_groups, list):
        for group in user_groups:
            identifier = getattr(group, "identifier", None)
            if not isinstance(identifier, str):
                continue
            normalized = identifier.strip()
            if not normalized:
                continue
            if normalized == SUPER_ADMIN_ROLE or normalized.endswith(f":{SUPER_ADMIN_ROLE}"):
                return True

    decoded = _decoded_token_cached(allow_decode=True)
    if not isinstance(decoded, dict):
        return False

    realm = extract_realm_from_issuer(decoded.get("iss"))
    if realm != MASTER_REALM_IDENTIFIER:
        return False

    realm_access = decoded.get("realm_access")
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles")
        if isinstance(roles, list) and SUPER_ADMIN_ROLE in roles:
            return True

    # Some Keycloak master-realm browser tokens may expose role/group data only
    # via the "groups" claim (for example "/super-admin").
    groups = decoded.get("groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, str):
                continue
            normalized = group.strip("/").split("/")[-1]
            if normalized == SUPER_ADMIN_ROLE:
                return True
    return False


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


def _selected_tenant_from_request() -> Optional[str]:
    auth_identifier = _authentication_identifier()
    if auth_identifier != _shared_realm_identifier():
        return None
    selected_tenant = request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
    if isinstance(selected_tenant, str) and selected_tenant.strip():
        return selected_tenant.strip()
    return None


def _selected_tenant_override_for_shared_multi_org_token(payload: dict[str, Any] | None) -> Optional[str]:
    """Prefer the selected-tenant cookie over token tenant claims for shared-realm sessions."""
    if not isinstance(payload, dict):
        return None

    selected_tenant = _selected_tenant_from_request()
    if not isinstance(selected_tenant, str) or not selected_tenant.strip():
        return None

    authentication_identifier = authentication_identifier_from_payload(payload)
    issuer_realm = extract_realm_from_issuer(payload.get("iss"))
    if authentication_identifier != _shared_realm_identifier() and issuer_realm != _shared_realm_identifier():
        return None

    selected_identifiers = current_tenant_identifiers(selected_tenant) or {selected_tenant}
    memberships = organization_memberships_from_payload(payload)
    for organization_alias, organization_details in memberships:
        organization_identifiers = {organization_alias}
        organization_id = organization_details.get("id")
        if isinstance(organization_id, str) and organization_id.strip():
            organization_identifiers.add(organization_id.strip())
        if organization_identifiers.intersection(selected_identifiers):
            return selected_tenant

    if payload_user_belongs_to_tenant(
        payload,
        tenant_id=selected_tenant,
        tenant_identifiers=selected_identifiers,
    ):
        return selected_tenant

    return None


def _authentication_identifier() -> Optional[str]:
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

    return None
