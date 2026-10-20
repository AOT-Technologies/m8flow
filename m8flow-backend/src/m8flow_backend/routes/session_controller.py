"""``GET /v1.0/m8flow/session``: the authenticated session described in
provider-neutral terms (authProvider-analysis redesign).

The frontend decodes Keycloak-shaped JWT claims today (``preferred_username``,
``realm_access``, ``organization``, the ``'master'`` realm name). That breaks
for any other identity provider. This endpoint answers the same questions
through ``AuthService`` so the UI can stop reading vendor claims. Additive:
nothing existing calls it yet.

Authentication mirrors ``organization-memberships``: the Bearer header or the
``access_token`` cookie, verified through the auth-provider port. Tenant
exempt -- it describes the session, it does not touch tenant data.
"""
from __future__ import annotations

from flask import request

from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors
from m8flow_backend.integrations.auth import get_auth_provider
from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid


def _session_token() -> str | None:
    header = (request.headers.get("Authorization") or "").strip()
    if header.startswith("Bearer ") and header[7:].strip():
        return header[7:].strip()
    cookie = request.cookies.get("access_token")
    return cookie.strip() if isinstance(cookie, str) and cookie.strip() else None


@handle_api_errors
def get_current_session() -> tuple[dict, int]:
    from m8flow_backend.integrations.auth.core import AuthService

    token = _session_token()
    if token is None:
        raise ApiError(error_code="not_authenticated", message="Authentication token not found", status_code=401)
    provider = get_auth_provider()
    try:
        claims = provider.verify_token(token)
    except TokenInvalid as exc:
        raise ApiError(
            error_code="not_authenticated", message="Authentication token is invalid", status_code=401
        ) from exc
    except ProviderUnavailable as exc:
        # Not a 401: an IdP/JWKS outage must not look like a logout to the UI.
        raise ApiError(
            error_code="identity_provider_unavailable", message="Identity provider unavailable", status_code=503
        ) from exc
    selected = (request.cookies.get(SELECTED_TENANT_COOKIE_NAME) or "").strip() or None
    return dict(AuthService(provider).session_view(claims, selected_tenant=selected)), 200
