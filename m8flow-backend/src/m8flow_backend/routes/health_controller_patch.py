from __future__ import annotations

import importlib
import logging
from functools import wraps
from typing import Any

from flask import g
from flask import make_response
from flask import request
from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
from spiffworkflow_backend.routes import authentication_controller
from spiffworkflow_backend.services.authorization_service import AuthorizationService

from flask import current_app

from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.tenancy import TENANT_CLAIM
from m8flow_backend.tenancy import reset_context_tenant_id
from m8flow_backend.tenancy import set_context_tenant_id

_PATCHED = False
logger = logging.getLogger(__name__)


def _health_controller_module():
    return importlib.import_module("spiffworkflow_backend.routes.health_controller")


def _is_health_status_endpoint(endpoint: str | None) -> bool:
    if not isinstance(endpoint, str) or not endpoint:
        return False
    return endpoint == "spiffworkflow_backend.routes.health_controller.status" or endpoint.endswith(
        "health_controller.status"
    )


def _selected_tenant_from_status_request() -> str | None:
    selected_tenant = request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
    if isinstance(selected_tenant, str):
        normalized_selected_tenant = selected_tenant.strip()
        if normalized_selected_tenant:
            return normalized_selected_tenant
    return None


def _canonical_tenant_id_for_status(tenant_identifier: str | None) -> str | None:
    if not isinstance(tenant_identifier, str) or not tenant_identifier.strip():
        return None

    from sqlalchemy import or_

    from m8flow_backend.canonical_db import get_canonical_db
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    db = get_canonical_db()
    tenant = (
        db.session.query(M8flowTenantModel)
        .filter(or_(M8flowTenantModel.id == tenant_identifier, M8flowTenantModel.slug == tenant_identifier))
        .one_or_none()
    )
    if tenant is None or not isinstance(tenant.id, str):
        return None
    return tenant.id.strip() or None


def _synchronize_status_token_to_selected_tenant(decoded_token: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(decoded_token, dict):
        return decoded_token

    selected_tenant = _canonical_tenant_id_for_status(_selected_tenant_from_status_request())
    if not selected_tenant:
        return decoded_token

    organization_claim = decoded_token.get("organization")
    if not isinstance(organization_claim, dict):
        return decoded_token

    for organization_alias, organization_details in organization_claim.items():
        if not isinstance(organization_alias, str) or not organization_alias.strip():
            continue
        if not isinstance(organization_details, dict):
            continue

        organization_id = organization_details.get("id")
        normalized_organization_id = organization_id.strip() if isinstance(organization_id, str) else ""
        if selected_tenant not in {organization_alias.strip(), normalized_organization_id}:
            continue

        synchronized_token = dict(decoded_token)
        synchronized_token["organization"] = {organization_alias.strip(): dict(organization_details)}
        synchronized_token[TENANT_CLAIM] = normalized_organization_id or selected_tenant
        synchronized_token["m8flow_tenant_alias"] = organization_alias.strip()
        return synchronized_token

    return decoded_token


def _bind_status_tenant_context(decoded_token: dict[str, Any] | None) -> None:
    if not isinstance(decoded_token, dict):
        return

    from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload

    tenant_id = tenant_id_from_payload(decoded_token)
    canonical_tenant_id = _canonical_tenant_id_for_status(tenant_id)
    if not canonical_tenant_id:
        return

    existing_tenant_id = getattr(g, "m8flow_tenant_id", None)
    existing_ctx_token = getattr(g, "_m8flow_ctx_token", None)
    if existing_tenant_id == canonical_tenant_id and existing_ctx_token is not None:
        return

    if existing_ctx_token is not None:
        reset_context_tenant_id(existing_ctx_token)

    g._m8flow_global_request = False
    g.m8flow_tenant_id = canonical_tenant_id
    g._m8flow_ctx_token = set_context_tenant_id(canonical_tenant_id)


def _log_status_frontend_access_state(
    *,
    stage: str,
    user: Any | None,
    decoded_token: dict[str, Any] | None,
    can_access_frontend: bool | None = None,
) -> None:
    organization_claim = decoded_token.get("organization") if isinstance(decoded_token, dict) else None
    organization_keys = list(organization_claim.keys()) if isinstance(organization_claim, dict) else None
    logger.debug(
        "status_frontend_access: stage=%s path=%s selected_tenant_cookie=%s request_tenant=%s authenticated=%s public_request=%s user_id=%s username=%s decoded_tenant=%s organization_keys=%s can_access_frontend=%s",
        stage,
        getattr(request, "path", "") or "",
        _selected_tenant_from_status_request(),
        getattr(g, "m8flow_tenant_id", None),
        getattr(g, "authenticated", None),
        getattr(g, "_m8flow_public_request", False),
        getattr(user, "id", None) if user is not None else None,
        getattr(user, "username", None) if user is not None else None,
        decoded_token.get(TENANT_CLAIM) if isinstance(decoded_token, dict) else None,
        organization_keys,
        can_access_frontend,
    )


def _status_request_has_auth_context(decoded_token: dict[str, Any] | None, user: Any | None) -> bool:
    if user is not None:
        return True
    if isinstance(decoded_token, dict) and bool(decoded_token):
        return True

    authorization_header = request.headers.get("Authorization")
    if isinstance(authorization_header, str) and authorization_header.strip():
        return True

    return bool(getattr(g, "authenticated", False))


def _preserve_status_auth_cookies_for_external_token(_decoded_token: dict[str, Any] | None) -> None:
    """
    Prevent the auth-exempt status endpoint from clearing auth cookies.

    Upstream after-request cookie handling treats ``user_has_logged_out`` as a
    signal to expire auth cookies. That is correct for protected endpoints, but
    ``/v1.0/status`` is auth exempt and should never be the request that clears
    an otherwise-usable session or forces a redirect loop.
    """
    g._m8flow_preserve_auth_cookies = True
    tld = current_app.config.get("THREAD_LOCAL_DATA")
    if tld is not None and hasattr(tld, "user_has_logged_out"):
        delattr(tld, "user_has_logged_out")


def _status_token_can_refresh_memberships(decoded_token: dict[str, Any] | None) -> bool:
    """Only sync local users from tokens that carry authoritative membership claims."""
    if not isinstance(decoded_token, dict):
        return False

    from m8flow_backend.routes.authentication_controller_patch import (
        _token_contains_authoritative_membership_claims,
    )

    return _token_contains_authoritative_membership_claims(decoded_token)


def _enrich_verified_status_token_for_active_tenant(decoded_token: dict[str, Any] | None) -> dict[str, Any] | None:
    """Enrich verified shared-realm status tokens when the active org's local groups are missing."""
    if not isinstance(decoded_token, dict):
        return decoded_token

    from m8flow_backend.routes.authentication_controller_patch import (
        _enrich_shared_realm_token_for_active_tenant,
    )

    return _enrich_shared_realm_token_for_active_tenant(decoded_token)


def apply(flask_app: Any | None = None) -> None:
    """Resolve tenant context and frontend access inside the status endpoint."""
    global _PATCHED
    if _PATCHED:
        return

    health_controller = _health_controller_module()
    original_status = health_controller.status

    @wraps(original_status)
    def patched_status(*args, **kwargs):
        ProcessInstanceModel.query.filter().first()

        decoded_token = getattr(g, "_m8flow_decoded_token", None)
        decoded_token_verified = False

        try:
            resolve_request_tenant()
        except Exception:
            decoded_token = getattr(g, "_m8flow_decoded_token", decoded_token)
            logger.warning("health_controller_patch: tenant resolution failed during status", exc_info=True)
        else:
            decoded_token = getattr(g, "_m8flow_decoded_token", decoded_token)

        decoded_token = _synchronize_status_token_to_selected_tenant(decoded_token)

        user = getattr(g, "user", None)
        _log_status_frontend_access_state(stage="post_tenant_resolution", user=user, decoded_token=decoded_token)
        if user is None and _status_request_has_auth_context(decoded_token, user):
            try:
                verified_decoded_token = authentication_controller.verify_token(force_run=True)
                if isinstance(verified_decoded_token, dict):
                    decoded_token = _synchronize_status_token_to_selected_tenant(verified_decoded_token)
                    decoded_token = _enrich_verified_status_token_for_active_tenant(decoded_token)
                    g._m8flow_decoded_token = decoded_token
                    _bind_status_tenant_context(decoded_token)
                    decoded_token_verified = True
                user = getattr(g, "user", None)
            except Exception:
                logger.info("health_controller_patch: status request has no verified authenticated user", exc_info=True)
            _log_status_frontend_access_state(stage="post_verify_token", user=user, decoded_token=decoded_token)

        if user is None and decoded_token_verified and isinstance(decoded_token, dict):
            try:
                resolved_user = authentication_controller._get_user_model_from_token(decoded_token)
                if resolved_user is not None:
                    user = resolved_user
                    g.user = resolved_user
                    logger.info(
                        "health_controller_patch: resolved user from decoded status token user_id=%s username=%s",
                        getattr(resolved_user, "id", None),
                        getattr(resolved_user, "username", None),
                    )
            except Exception:
                logger.info(
                    "health_controller_patch: failed to resolve user model from decoded status token",
                    exc_info=True,
                )
            _log_status_frontend_access_state(stage="post_user_lookup", user=user, decoded_token=decoded_token)

        if user is None and decoded_token_verified and _status_token_can_refresh_memberships(decoded_token):
            try:
                user = AuthorizationService.create_user_from_sign_in(decoded_token)
                g.user = user
                logger.info(
                    "health_controller_patch: synchronized user from decoded status token user_id=%s username=%s",
                    getattr(user, "id", None),
                    getattr(user, "username", None),
                )
            except Exception:
                logger.warning(
                    "health_controller_patch: failed to synchronize user from decoded status token",
                    exc_info=True,
                )
            _log_status_frontend_access_state(stage="post_user_sync", user=user, decoded_token=decoded_token)
        elif user is None and isinstance(decoded_token, dict):
            logger.debug(
                "health_controller_patch: skipping user synchronization for unverified or non-authoritative decoded status token"
            )

        can_access_frontend = not _status_request_has_auth_context(decoded_token, user)
        if user is not None:
            can_access_frontend = AuthorizationService.user_has_permission(
                user=user,
                permission="read",
                target_uri="/frontend-access",
            )
            _log_status_frontend_access_state(
                stage="post_permission_check",
                user=user,
                decoded_token=decoded_token,
                can_access_frontend=can_access_frontend,
            )
            if not can_access_frontend and decoded_token_verified and _status_token_can_refresh_memberships(decoded_token):
                try:
                    refreshed_user = AuthorizationService.create_user_from_sign_in(decoded_token)
                    g.user = refreshed_user
                    user = refreshed_user
                    can_access_frontend = AuthorizationService.user_has_permission(
                        user=refreshed_user,
                        permission="read",
                        target_uri="/frontend-access",
                    )
                    logger.info(
                        "health_controller_patch: retried frontend access after user sync user_id=%s username=%s allowed=%s",
                        getattr(refreshed_user, "id", None),
                        getattr(refreshed_user, "username", None),
                        can_access_frontend,
                    )
                except Exception:
                    logger.warning(
                        "health_controller_patch: failed to refresh user during frontend access retry",
                        exc_info=True,
                    )
                _log_status_frontend_access_state(
                    stage="post_permission_retry",
                    user=user,
                    decoded_token=decoded_token,
                    can_access_frontend=can_access_frontend,
                )
            elif not can_access_frontend and isinstance(decoded_token, dict):
                logger.debug(
                    "health_controller_patch: skipping frontend-access retry for unverified or non-authoritative decoded status token"
                )

        _preserve_status_auth_cookies_for_external_token(decoded_token)
        return make_response({"ok": True, "can_access_frontend": can_access_frontend}, 200)

    health_controller.status = patched_status

    app = flask_app or current_app._get_current_object()
    patched = False

    for endpoint, view_function in list(app.view_functions.items()):
        if _is_health_status_endpoint(endpoint) or (
            getattr(view_function, "__module__", None) == health_controller.__name__
            and getattr(view_function, "__name__", None) == "status"
        ):
            app.view_functions[endpoint] = patched_status
            patched = True

    if not patched:
        for rule in app.url_map.iter_rules():
            if "GET" not in (rule.methods or set()):
                continue
            view_function = app.view_functions.get(rule.endpoint)
            if _is_health_status_endpoint(rule.endpoint) or (
                getattr(view_function, "__module__", None) == health_controller.__name__
                and getattr(view_function, "__name__", None) == "status"
            ):
                app.view_functions[rule.endpoint] = patched_status
                patched = True

    logger.info("health_controller_patch: patched status endpoint=%s", patched)
    _PATCHED = True
