# extensions/m8flow-backend/src/m8flow_backend/services/tenant_context_middleware.py
from __future__ import annotations

import logging
import os

from flask import g, request

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authentication_service import AuthenticationService
from spiffworkflow_backend.services.authorization_service import AuthorizationService

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import DEFAULT_TENANT_ID
from m8flow_backend.tenancy import allow_missing_tenant_context
from m8flow_backend.tenancy import get_context_tenant_id
from spiffworkflow_backend.models.db import db

LOGGER = logging.getLogger(__name__)

_DEFAULT_TENANT_CLAIM = "m8flow_tenant_id"


def resolve_request_tenant() -> None:
    """Resolve tenant from trusted auth context and store it in g.m8flow_tenant_id.

    Priority order:
    1) JWT claim on the token itself (for local testing with spiff-generated tokens)
    2) ContextVar tenant id (for background/worker contexts)
    """
    if AuthorizationService.should_disable_auth_for_request():
        return

    req = request._get_current_object()
    current_request_id = req.environ.setdefault("m8flow_request_id", str(id(req.environ)))
    existing_tenant = getattr(g, "m8flow_tenant_id", None)
    existing_request_id = getattr(g, "_m8flow_tenant_request_id", None)
    if existing_tenant and existing_request_id and existing_request_id != current_request_id:
        existing_tenant = None
        existing_request_id = None

    if existing_tenant and (existing_request_id is None or existing_request_id == current_request_id):
        resolved = _resolve_from_token_claim() or _resolve_from_context_var()
        if resolved and resolved != existing_tenant:
            raise ApiError(
                error_code="tenant_override_forbidden",
                message="Tenant context cannot be overridden within the same request.",
                status_code=400,
            )
        return

    tenant_id = _resolve_from_token_claim() or _resolve_from_context_var()

    if not tenant_id:
        if allow_missing_tenant_context():
            tenant_id = DEFAULT_TENANT_ID
            LOGGER.info("Tenant not resolved from auth; defaulting to '%s'.", tenant_id)
        else:
            raise ApiError(
                error_code="tenant_required",
                message="Tenant context could not be resolved from authentication data.",
                status_code=400,
            )

    g.m8flow_tenant_id = tenant_id
    g._m8flow_tenant_request_id = current_request_id

    try:
        _validate_tenant_or_raise(tenant_id)
    except Exception:
        g.m8flow_tenant_id = None
        g._m8flow_tenant_request_id = None
        raise


def _resolve_from_token_claim() -> str | None:
    token = _token_from_request()
    if not token:
        return None
    claim = os.getenv("M8FLOW_TENANT_CLAIM", _DEFAULT_TENANT_CLAIM)
    try:
        decoded = AuthenticationService.parse_jwt_token(_authentication_identifier(), token)
    except Exception as exc:
        LOGGER.warning("Failed to decode token for tenant resolution: %s", exc)
        return None
    return decoded.get(claim)


def _resolve_from_context_var() -> str | None:
    return get_context_tenant_id()


def _token_from_request() -> str | None:
    token = getattr(g, "token", None)
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ")
    access_cookie = request.cookies.get("access_token")
    if access_cookie:
        return access_cookie
    return None


def _authentication_identifier() -> str:
    if "authentication_identifier" in request.cookies:
        return request.cookies["authentication_identifier"]
    header_identifier = request.headers.get("SpiffWorkflow-Authentication-Identifier")
    if header_identifier:
        return header_identifier
    return "default"


def _validate_tenant_or_raise(tenant_id: str) -> None:
    if not tenant_id:
        raise ApiError(
            error_code="tenant_required",
            message="Tenant context is missing.",
            status_code=400,
        )
    if db.session.get(M8flowTenantModel, tenant_id) is None:
        raise ApiError(
            error_code="invalid_tenant",
            message=f"Tenant '{tenant_id}' does not exist.",
            status_code=400,
        )
