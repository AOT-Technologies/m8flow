from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
from functools import wraps
from ipaddress import ip_address
import logging
import re
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlsplit

from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from m8flow_backend.services.tenant_identity_helpers import authentication_identifier_from_payload
from m8flow_backend.services.tenant_identity_helpers import _canonical_tenant_id_from_identifiers
from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer
from m8flow_backend.services.tenant_identity_helpers import current_tenant_identifiers
from m8flow_backend.services.tenant_identity_helpers import normalize_organizational_group_identifier
from m8flow_backend.services.tenant_identity_helpers import organization_group_identifiers_from_payload
from m8flow_backend.services.tenant_identity_helpers import organization_memberships_from_payload
from m8flow_backend.services.tenant_identity_helpers import payload_user_belongs_to_tenant
from m8flow_backend.services.tenant_identity_helpers import qualified_config_group_identifier
from m8flow_backend.services.tenant_identity_helpers import TENANT_ALIAS_CLAIM
from m8flow_backend.services.tenant_identity_helpers import TENANT_NAME_CLAIM
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_slug_for_identifier
from spiffworkflow_backend.routes import authentication_controller

logger = logging.getLogger(__name__)

_PATCHED = False
_COOKIE_DOMAIN_PATCHED = False
_DECODE_TOKEN_PATCHED = False
_INTERNAL_TOKEN_SUBJECT_PATCHED = False
_MASTER_REALM_PATCHED = False
_PUBLIC_GROUP_PATCHED = False
_REFRESH_TOKEN_TENANT_PATCHED = False

# Path suffixes that may be called with configured admin-realm tokens (bootstrap/global admin).
M8FLOW_MASTER_REALM_PATH_SUBSTRINGS = (
    "/m8flow/tenant-realms",
    "/m8flow/create-tenant",
    "/m8flow/tenants",
)
LOGIN_RETURN_PATH_SUBSTRING = "/login_return"
_MISSING = object()


def _master_realm_identifier() -> str:
    from m8flow_backend.config import master_realm_name

    return master_realm_name()


def _shared_realm_identifier() -> str:
    from m8flow_backend.config import shared_realm_name

    return shared_realm_name()


def apply() -> None:
    """Patch the authentication controller with m8flow auth behavior."""
    apply_cookie_domain_patch()
    apply_internal_token_subject_patch()
    apply_public_group_patch()

    global _PATCHED
    if _PATCHED:
        return

    from spiffworkflow_backend.services.authorization_service import AuthorizationService

    def patched_omni_auth(*args, **kwargs):
        """Resolve tenant before permission checks run so RBAC uses the authenticated tenant."""
        from flask import g

        decoded_token = authentication_controller.verify_token(*args, **kwargs)
        token = getattr(g, "token", None)
        if isinstance(token, str) and token:
            g._m8flow_decoded_token_raw = token
        tenant_id = _tenant_for_refresh_tokens(decoded_token=decoded_token)
        with _temporary_request_tenant(tenant_id, force=True):
            decoded_token = _enrich_shared_realm_token_for_active_tenant(
                decoded_token,
                tenant_id=tenant_id,
            )
            g._m8flow_decoded_token = decoded_token
            if isinstance(tenant_id, str) and tenant_id.strip():
                g.m8flow_tenant_id = tenant_id.strip()
            resolve_request_tenant()
            AuthorizationService.check_for_permission(decoded_token)

    authentication_controller.omni_auth = patched_omni_auth  # type: ignore[assignment]
    _PATCHED = True


def _parse_internal_token_subject(subject: object) -> tuple[str, str] | None:
    """Parse ``service:<issuer>::service_id:<subject>`` without truncating URL values."""
    if not isinstance(subject, str):
        return None

    parts = subject.split("::", 1)
    if len(parts) != 2:
        return None

    service_part, service_id_part = parts
    if not service_part.startswith("service:") or not service_id_part.startswith("service_id:"):
        return None

    service = service_part.removeprefix("service:").strip()
    service_id = service_id_part.removeprefix("service_id:").strip()
    if not service or not service_id:
        return None

    return service, service_id


def apply_internal_token_subject_patch() -> None:
    """Patch internal JWT user resolution so URL-shaped issuers survive subject parsing."""
    global _INTERNAL_TOKEN_SUBJECT_PATCHED
    if _INTERNAL_TOKEN_SUBJECT_PATCHED:
        return

    original = authentication_controller._get_user_from_decoded_internal_token

    @wraps(original)
    def patched_get_user_from_decoded_internal_token(decoded_token: dict):
        parsed_subject = _parse_internal_token_subject(decoded_token.get("sub"))
        if parsed_subject is None:
            return original(decoded_token)

        service, service_id = parsed_subject

        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.services.user_service import UserService

        user = UserModel.query.filter(UserModel.service == service).filter(UserModel.service_id == service_id).first()
        if user is not None:
            return user

        preferred_username = decoded_token.get("preferred_username")
        username = preferred_username if isinstance(preferred_username, str) and preferred_username.strip() else service_id
        email = decoded_token.get("email")
        email_value = email if isinstance(email, str) and email.strip() else None
        return UserService.create_user(username, service, service_id, email=email_value)

    authentication_controller._get_user_from_decoded_internal_token = patched_get_user_from_decoded_internal_token
    _INTERNAL_TOKEN_SUBJECT_PATCHED = True


def apply_public_group_patch() -> None:
    """Patch public-request detection to use tenant-qualified public group identifiers."""
    global _PUBLIC_GROUP_PATCHED
    if _PUBLIC_GROUP_PATCHED:
        return

    @wraps(authentication_controller._check_if_request_is_public)
    def patched_check_if_request_is_public():
        """Authorize public requests against the tenant-qualified public group."""
        from flask import current_app
        from flask import g
        from flask import request
        from spiffworkflow_backend.models.group import GroupModel
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        permission_string = AuthorizationService.get_permission_from_http_method(request.method)
        if not permission_string:
            return None

        public_group_identifier = qualified_config_group_identifier("SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP")
        if not public_group_identifier:
            return None

        public_group = GroupModel.query.filter_by(identifier=public_group_identifier).first()
        if public_group is None:
            return None

        has_permission = AuthorizationService.has_permission(
            principals=[public_group.principal],
            permission=permission_string,
            target_uri=request.path,
        )
        if not has_permission:
            return None

        g.user = UserService.create_public_user()
        g.token = g.user.encode_auth_token({"public": True})
        tld = current_app.config["THREAD_LOCAL_DATA"]
        tld.user = g.user

    authentication_controller._check_if_request_is_public = patched_check_if_request_is_public
    _PUBLIC_GROUP_PATCHED = True


def _frontend_cookie_domain(frontend_url: str) -> str | None:
    """
    Return a valid cookie domain for the configured frontend URL.

    Browsers reject cookie Domain values that include a port, and they are also
    picky about localhost/IP literals. For local development on localhost or a
    LAN IP, host-only cookies are the most reliable choice, so return None.
    """
    candidate = (frontend_url or "").strip()
    if not candidate:
        return None

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
    except ValueError:
        hostname = None

    if not hostname:
        hostname = re.sub(r"^https?:\/\/", "", candidate).split("/")[0].split(":")[0].strip() or None

    if not hostname:
        return None

    if hostname == "localhost" or "." not in hostname:
        return None

    try:
        ip_address(hostname)
        return None
    except ValueError:
        return hostname


@contextmanager
def _temporary_frontend_url(frontend_url: str):
    """Temporarily override the configured frontend URL while cookies are written."""
    from flask import current_app

    previous = current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND")
    current_app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = frontend_url
    try:
        yield
    finally:
        current_app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = previous


def apply_cookie_domain_patch() -> None:
    """Patch cookie writing so local and named-host frontend URLs get valid cookie domains."""
    global _COOKIE_DOMAIN_PATCHED
    if _COOKIE_DOMAIN_PATCHED:
        return

    original = authentication_controller._set_new_access_token_in_cookie

    def _is_auth_cookie_clear_header(header: str) -> bool:
        return header.startswith("access_token=;") or header.startswith("id_token=;") or header.startswith(
            "authentication_identifier=;"
        )

    @wraps(original)
    def patched_set_new_access_token_in_cookie(response):
        """Set auth cookies using a host-only or normalized frontend domain as needed."""
        from flask import current_app
        from flask import g
        from flask import has_request_context

        frontend_url = str(current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))
        cookie_domain = _frontend_cookie_domain(frontend_url)
        patched_frontend_url = "localhost" if cookie_domain is None else f"https://{cookie_domain}"
        preserve_auth_cookies = has_request_context() and bool(getattr(g, "_m8flow_preserve_auth_cookies", False))

        # Read TLD before original() clears it via _clear_auth_tokens_from_thread_local_data.
        tld = current_app.config.get("THREAD_LOCAL_DATA")
        new_auth_id = getattr(tld, "new_authentication_identifier", None) if tld else None
        was_logged_out = bool(getattr(tld, "user_has_logged_out", False)) if tld else False

        cookies_before = len(response.headers.getlist("Set-Cookie"))

        with _temporary_frontend_url(patched_frontend_url):
            result = original(response)

        if preserve_auth_cookies:
            set_cookie_headers = result.headers.getlist("Set-Cookie")
            filtered_set_cookie_headers = [
                header for header in set_cookie_headers if not _is_auth_cookie_clear_header(header)
            ]
            if len(filtered_set_cookie_headers) != len(set_cookie_headers):
                if "Set-Cookie" in result.headers:
                    del result.headers["Set-Cookie"]
                for header in filtered_set_cookie_headers:
                    result.headers.add("Set-Cookie", header)

        cookies_after = len(result.headers.getlist("Set-Cookie"))
        if cookies_after != cookies_before:
            result.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            result.headers["Pragma"] = "no-cache"

        # Persist which realm the user authenticated with across session-expiry cookie clears.
        # Standard auth cookies are cleared on token expiry, but m8flow_auth_realm survives so
        # the login redirect can return the user to the correct realm.
        if isinstance(new_auth_id, str) and new_auth_id.strip():
            result.set_cookie("m8flow_auth_realm", new_auth_id, max_age=86400 * 30, path="/", domain=cookie_domain)
        elif was_logged_out:
            # Only clear the realm hint on an explicit /logout request. Token expiry also sets
            # user_has_logged_out=True (SpiffWorkflow calls set_user_has_logged_out() on refresh
            # failure), but we must keep the hint alive so that the next /login redirect goes back
            # to the same realm rather than falling through to the shared realm default.
            from flask import has_request_context
            from flask import request as flask_request

            is_explicit_logout = has_request_context() and "/logout" in (
                getattr(flask_request, "path", "") or ""
            )
            if is_explicit_logout:
                result.set_cookie("m8flow_auth_realm", "", max_age=0, path="/", domain=cookie_domain)

        return result

    authentication_controller._set_new_access_token_in_cookie = patched_set_new_access_token_in_cookie
    _COOKIE_DOMAIN_PATCHED = True


def _decode_state_authentication_identifier(state: str | None) -> str | None:
    """Extract ``authentication_identifier`` from the encoded login state payload."""
    if not state:
        return None
    try:
        raw = base64.b64decode(unquote(state)).decode("utf-8")
        state_dict = ast.literal_eval(raw)
    except Exception:
        return None
    identifier = state_dict.get("authentication_identifier") if isinstance(state_dict, dict) else None
    if isinstance(identifier, str) and identifier.strip():
        return identifier
    return None


def _selected_tenant_from_request(authentication_identifier: str | None = None) -> str | None:
    """Read the shared-realm tenant bridge only when the active auth realm is the shared realm."""
    from flask import has_request_context, request
    from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME

    if authentication_identifier != _shared_realm_identifier():
        return None
    if not has_request_context():
        return None
    selected_tenant = request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
    if isinstance(selected_tenant, str) and selected_tenant.strip():
        return selected_tenant.strip()
    return None


def _selected_tenant_overrides_shared_multi_org_token(
    decoded_token: dict[str, Any] | None,
    selected_tenant: str | None,
) -> bool:
    """Return whether the selected tenant should override token tenant claims for shared-realm sessions."""
    if not isinstance(decoded_token, dict):
        return False
    if not isinstance(selected_tenant, str) or not selected_tenant.strip():
        return False

    authentication_identifier = authentication_identifier_from_payload(decoded_token)
    issuer_realm = extract_realm_from_issuer(decoded_token.get("iss"))
    if authentication_identifier != _shared_realm_identifier() and issuer_realm != _shared_realm_identifier():
        return False

    selected_identifiers = current_tenant_identifiers(selected_tenant) or {selected_tenant}
    memberships = organization_memberships_from_payload(decoded_token)
    for organization_alias, organization_details in memberships:
        organization_identifiers = {organization_alias}
        organization_id = organization_details.get("id")
        if isinstance(organization_id, str) and organization_id.strip():
            organization_identifiers.add(organization_id.strip())
        if organization_identifiers.intersection(selected_identifiers):
            return True

    return payload_user_belongs_to_tenant(
        decoded_token,
        tenant_id=selected_tenant,
        tenant_identifiers=selected_identifiers,
    )


def _tenant_for_refresh_tokens(
    decoded_token: dict | None = None,
    state: str | None = None,
) -> str | None:
    """Derive tenant context for refresh-token flows before normal tenant hooks run."""
    from flask import g, has_request_context, request

    state_identifier = _decode_state_authentication_identifier(state)
    selected_tenant = _selected_tenant_from_request(state_identifier)
    if not selected_tenant and has_request_context():
        cookie_identifier = request.cookies.get("authentication_identifier")
        selected_tenant = _selected_tenant_from_request(cookie_identifier)
    if isinstance(decoded_token, dict):
        if selected_tenant and _selected_tenant_overrides_shared_multi_org_token(decoded_token, selected_tenant):
            return selected_tenant
        tenant_from_claim = tenant_id_from_payload(decoded_token)
        if tenant_from_claim:
            return tenant_from_claim

    if selected_tenant:
        return selected_tenant

    if isinstance(decoded_token, dict):
        inferred_tenant = _infer_single_tenant_for_shared_realm_user(decoded_token)
        if inferred_tenant:
            return inferred_tenant

    if not has_request_context():
        return None

    existing_tenant = getattr(g, "m8flow_tenant_id", None)
    if isinstance(existing_tenant, str) and existing_tenant.strip():
        return existing_tenant

    request_state_identifier = _decode_state_authentication_identifier(request.args.get("state"))
    request_selected_tenant = _selected_tenant_from_request(request_state_identifier)
    if request_selected_tenant:
        return request_selected_tenant

    cookie_identifier = request.cookies.get("authentication_identifier")
    cookie_selected_tenant = _selected_tenant_from_request(cookie_identifier)
    if cookie_selected_tenant:
        return cookie_selected_tenant

    return None


def _infer_single_tenant_for_shared_realm_user(decoded_token: dict[str, object] | None) -> str | None:
    """
    Infer the active tenant for thin shared-realm bearer tokens from the local user mirror.

    Some shared-realm access tokens omit both ``m8flow_tenant_id`` and
    organization-local groups. When the browser also lacks the selected-tenant
    cookie, fall back to the already-provisioned local shared-realm user and
    recover the single tenant implied by that user's tenant-qualified groups.
    """
    if not isinstance(decoded_token, dict):
        return None

    authentication_identifier = authentication_identifier_from_payload(decoded_token)
    issuer = decoded_token.get("iss")
    issuer_realm = extract_realm_from_issuer(issuer)
    if (
        authentication_identifier != _shared_realm_identifier()
        and issuer_realm != _shared_realm_identifier()
    ):
        return None

    subject = decoded_token.get("sub")
    preferred_username = decoded_token.get("preferred_username")
    if not isinstance(subject, str):
        subject = ""
    if not isinstance(preferred_username, str):
        preferred_username = ""

    if not subject.strip() and not preferred_username.strip():
        return None

    try:
        from spiffworkflow_backend.models.user import UserModel
    except Exception:
        return None

    candidate_users: list[object] = []
    seen_user_ids: set[object] = set()

    if isinstance(issuer, str) and issuer.strip() and subject.strip():
        for user in UserModel.query.filter_by(service=issuer.strip(), service_id=subject.strip()).all():
            user_id = getattr(user, "id", None)
            if user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
            candidate_users.append(user)

    if preferred_username.strip():
        for user in UserModel.query.filter_by(username=preferred_username.strip()).all():
            user_id = getattr(user, "id", None)
            if user_id in seen_user_ids:
                continue

            user_service_realm = extract_realm_from_issuer(getattr(user, "service", None))
            if issuer_realm and user_service_realm and user_service_realm != issuer_realm:
                continue

            seen_user_ids.add(user_id)
            candidate_users.append(user)

    inferred_tenant_ids: set[str] = set()

    for user in candidate_users:
        groups = getattr(user, "groups", None) or []
        for group in groups:
            group_identifier = getattr(group, "identifier", None)
            if not isinstance(group_identifier, str):
                continue

            tenant_prefix, separator, _group_suffix = group_identifier.partition(":")
            normalized_tenant_prefix = tenant_prefix.strip()
            if not separator or not normalized_tenant_prefix:
                continue

            canonical_tenant_id = (
                _canonical_tenant_id_from_identifiers(normalized_tenant_prefix)
                or normalized_tenant_prefix
            )
            inferred_tenant_ids.add(canonical_tenant_id)
            if len(inferred_tenant_ids) > 1:
                return None

    if len(inferred_tenant_ids) != 1:
        return None

    return next(iter(inferred_tenant_ids))


@contextmanager
def _temporary_request_tenant(tenant_id: str | None, *, force: bool = False):
    """Temporarily bind ``g.m8flow_tenant_id`` for pre-resolution auth flows."""
    from flask import g, has_request_context

    if not has_request_context() or not tenant_id:
        yield
        return

    previous = getattr(g, "m8flow_tenant_id", _MISSING)
    if force or previous is _MISSING or previous is None:
        g.m8flow_tenant_id = tenant_id
    try:
        yield
    finally:
        if previous is _MISSING:
            if hasattr(g, "m8flow_tenant_id"):
                delattr(g, "m8flow_tenant_id")
        else:
            g.m8flow_tenant_id = previous


def _token_contains_authoritative_membership_claims(decoded_token: dict | None) -> bool:
    """Return whether the token can safely refresh local group memberships."""
    if not isinstance(decoded_token, dict):
        return False

    groups = decoded_token.get("groups")
    if isinstance(groups, list) and any(isinstance(group, str) and group.strip() for group in groups):
        return True

    organization = decoded_token.get("organization")
    if isinstance(organization, dict) and organization:
        return True
    if isinstance(organization, list) and organization:
        return True

    realm_access = decoded_token.get("realm_access")
    if isinstance(realm_access, dict):
        roles = realm_access.get("roles")
        if isinstance(roles, list) and any(isinstance(role, str) and role.strip() for role in roles):
            return True

    return False


def _shared_realm_token_has_active_organization_groups(
    decoded_token: dict | None,
    *,
    tenant_id: str | None,
) -> bool:
    """Return whether the shared-realm token already carries org-local groups for the active tenant."""
    if not isinstance(decoded_token, dict):
        return False
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        return False
    return bool(organization_group_identifiers_from_payload(decoded_token, tenant_id=tenant_id.strip()))


def _enrich_shared_realm_token_for_active_tenant(
    decoded_token: dict | None,
    *,
    tenant_id: str | None = None,
) -> dict | None:
    """
    Reconstruct active-organization membership claims for thin shared-realm tokens.

    Some shared-realm access tokens identify the active tenant but do not carry the
    organization-local groups needed to refresh local M8Flow RBAC. When the request
    already has a concrete tenant context, fetch the selected organization's member
    groups from Keycloak and rewrite the token into the same single-organization
    shape used by tenant finalization.
    """
    if not isinstance(decoded_token, dict):
        return decoded_token

    authentication_identifier = authentication_identifier_from_payload(decoded_token)
    issuer_realm = extract_realm_from_issuer(decoded_token.get("iss"))
    is_shared_realm_token = (
        authentication_identifier == _shared_realm_identifier() or issuer_realm == _shared_realm_identifier()
    )
    if not is_shared_realm_token:
        if _token_contains_authoritative_membership_claims(decoded_token):
            return decoded_token
        return decoded_token

    effective_tenant_id = tenant_id or _tenant_for_refresh_tokens(decoded_token=decoded_token)
    if not isinstance(effective_tenant_id, str) or not effective_tenant_id.strip():
        return decoded_token
    effective_tenant_id = effective_tenant_id.strip()

    if _shared_realm_token_has_active_organization_groups(decoded_token, tenant_id=effective_tenant_id):
        return decoded_token

    selected_tenant_alias = tenant_slug_for_identifier(effective_tenant_id)
    if not isinstance(selected_tenant_alias, str) or not selected_tenant_alias.strip():
        token_alias = decoded_token.get(TENANT_ALIAS_CLAIM)
        if isinstance(token_alias, str) and token_alias.strip():
            selected_tenant_alias = token_alias.strip()
        else:
            selected_tenant_alias = effective_tenant_id

    try:
        enriched_token = _synchronize_selected_organization_claims(
            decoded_token,
            selected_tenant_alias=selected_tenant_alias,
            selected_tenant_id=effective_tenant_id,
        )
    except Exception:
        logger.warning(
            "shared_realm_token_enrichment_failed: tenant_id=%s alias=%s",
            effective_tenant_id,
            selected_tenant_alias,
            exc_info=True,
        )
        return decoded_token

    return enriched_token if isinstance(enriched_token, dict) else decoded_token


def apply_refresh_token_tenant_patch() -> None:
    """
    Ensure refresh-token operations have tenant context during auth controller
    flows that run before tenant-resolution hooks.
    """
    global _REFRESH_TOKEN_TENANT_PATCHED
    if _REFRESH_TOKEN_TENANT_PATCHED:
        return

    original_login_return = authentication_controller.login_return
    original_get_user_model_from_token = authentication_controller._get_user_model_from_token

    @wraps(original_login_return)
    def patched_login_return(*args, **kwargs):
        """Retry expired auth flows and ensure tenant context exists while login_return executes."""
        from flask import current_app, redirect
        from spiffworkflow_backend.services.authentication_service import AuthenticationService

        state = kwargs.get("state")
        if state is None and args:
            state = args[0]

        error = kwargs.get("error")
        error_description = kwargs.get("error_description")
        if error and error_description and "authentication_expired" in str(error_description):
            try:
                decoded_state = unquote(state) if isinstance(state, str) else ""
                state_dict = ast.literal_eval(base64.b64decode(decoded_state).decode("utf-8"))

                auth_id = state_dict.get("authentication_identifier")
                final_url = state_dict.get("final_url") or "/"
                frontend_url = str(current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))

                if not _is_allowed_frontend_redirect_url(final_url, frontend_url):
                    final_url = frontend_url or "/"

                if auth_id:
                    login_url = AuthenticationService().get_login_redirect_url(
                        authentication_identifier=auth_id,
                        final_url=final_url,
                    )
                    if "prompt=" not in login_url:
                        login_url += "&prompt=login"
                    logger.info("authentication_expired detected, retrying login for identifier=%s", auth_id)
                    return redirect(login_url)
            except Exception:
                logger.warning("Failed to auto-retry login after authentication_expired", exc_info=True)

        tenant_id = _tenant_for_refresh_tokens(state=state if isinstance(state, str) else None)
        auth_identifier = _authentication_identifier_from_state() or (
            _decode_state_authentication_identifier(state) if isinstance(state, str) else None
        )
        if auth_identifier:
            try:
                from m8flow_backend.services.keycloak_service import (
                    ensure_backend_redirect_uri_in_keycloak_client,
                )

                ensure_backend_redirect_uri_in_keycloak_client(auth_identifier)
            except Exception:
                pass
        with _temporary_request_tenant(tenant_id, force=True):
            return original_login_return(*args, **kwargs)

    @wraps(original_get_user_model_from_token)
    def patched_get_user_model_from_token(decoded_token: dict):
        """Resolve or auto-provision the user while refresh-token tenant context is temporarily bound."""
        tenant_id = _tenant_for_refresh_tokens(decoded_token=decoded_token)
        with _temporary_request_tenant(tenant_id, force=True):
            decoded_token = _enrich_shared_realm_token_for_active_tenant(
                decoded_token,
                tenant_id=tenant_id,
            )
            try:
                user_model = original_get_user_model_from_token(decoded_token)
            except Exception as exc:
                from spiffworkflow_backend.exceptions.api_error import ApiError

                if not isinstance(exc, ApiError) or exc.error_code != "invalid_user":
                    raise
                if not isinstance(decoded_token, dict) or "iss" not in decoded_token or "sub" not in decoded_token:
                    raise

                from spiffworkflow_backend.services.authorization_service import AuthorizationService

                user_model = AuthorizationService.create_user_from_sign_in(decoded_token)
                logger.info(
                    "refresh_token_tenant_patch: auto-provisioned missing user for issuer=%s subject=%s",
                    decoded_token.get("iss"),
                    decoded_token.get("sub"),
                )
                return user_model

            if not _token_contains_authoritative_membership_claims(decoded_token):
                return user_model

            from spiffworkflow_backend.models.user import UserModel
            from spiffworkflow_backend.services.authorization_service import AuthorizationService

            issuer = decoded_token.get("iss")
            if not isinstance(issuer, str) or issuer == UserModel.spiff_generated_jwt_issuer():
                return user_model

            refreshed_user = AuthorizationService.create_user_from_sign_in(decoded_token)
            logger.info(
                "refresh_token_tenant_patch: refreshed existing user from token issuer=%s subject=%s user_id=%s",
                decoded_token.get("iss"),
                decoded_token.get("sub"),
                getattr(refreshed_user, "id", None),
            )
            return refreshed_user

    authentication_controller.login_return = patched_login_return  # type: ignore[assignment]
    authentication_controller._get_user_model_from_token = patched_get_user_model_from_token  # type: ignore[assignment]
    _REFRESH_TOKEN_TENANT_PATCHED = True


def _patched_get_decoded_token(token: str):
    """Delegate token decoding while preserving a hook point for targeted debugging."""
    return authentication_controller._original_get_decoded_token(token)


def apply_decode_token_debug_patch() -> None:
    """Install a thin wrapper around token decoding for debug instrumentation."""
    global _DECODE_TOKEN_PATCHED
    if _DECODE_TOKEN_PATCHED:
        return
    authentication_controller._original_get_decoded_token = authentication_controller._get_decoded_token
    authentication_controller._get_decoded_token = _patched_get_decoded_token
    _DECODE_TOKEN_PATCHED = True


def _authentication_identifier_from_state() -> str | None:
    """On login_return, state contains base64 dict with authentication_identifier."""
    from flask import request

    path = (request.path or "").strip()
    if LOGIN_RETURN_PATH_SUBSTRING not in path:
        return None
    state = request.args.get("state")
    if not state or not isinstance(state, str):
        return None
    try:
        state = unquote(state)
        raw = base64.b64decode(state).decode("utf-8")
        state_dict = ast.literal_eval(raw)
        return state_dict.get("authentication_identifier")
    except Exception:
        return None


def _has_master_auth_config() -> bool:
    """True if SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS has an entry for the configured admin realm."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    master_identifier = _master_realm_identifier()
    return any(isinstance(c, dict) and c.get("identifier") == master_identifier for c in configs)


def _auth_config_identifiers() -> list[str]:
    """Return auth config identifiers (e.g., realm names)."""
    from flask import current_app

    configs = current_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
    return [c["identifier"] for c in configs if isinstance(c, dict) and c.get("identifier")]


def _authentication_identifier_from_bearer_token() -> str | None:
    """
    Decode Bearer payload without signature verification and derive the auth
    identifier from explicit realm/auth claims before falling back to ``iss``.
    """
    from flask import request
    from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer

    auth_header = (request.headers.get("Authorization") or "").strip()
    if not auth_header.startswith("Bearer ") or len(auth_header) <= 7:
        return None
    token = auth_header[7:].strip()
    if not token:
        return None

    try:
        import jwt

        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    identifiers = _auth_config_identifiers()

    authentication_identifier = authentication_identifier_from_payload(payload)
    if authentication_identifier in identifiers:
        return authentication_identifier

    iss = payload.get("iss")
    realm_from_iss = extract_realm_from_issuer(iss if isinstance(iss, str) else None)
    if realm_from_iss and realm_from_iss in identifiers:
        return realm_from_iss

    return None


def apply_master_realm_auth_patch() -> None:
    """Patch identifier resolution for master/bootstrap and Bearer-only requests."""
    global _MASTER_REALM_PATCHED
    if _MASTER_REALM_PATCHED:
        return
    from flask import request

    original = authentication_controller._get_authentication_identifier_from_request

    def _patched_get_authentication_identifier_from_request() -> str:
        """Resolve the auth config identifier from state, bearer token, or the upstream logic."""
        path = (request.path or "").strip()
        state_id = _authentication_identifier_from_state()
        if state_id:
            return state_id

        auth_header = (request.headers.get("Authorization") or "").strip()
        has_bearer = auth_header.startswith("Bearer ") and len(auth_header) > 7
        cookie_id = request.cookies.get("authentication_identifier")
        header_id = request.headers.get("SpiffWorkflow-Authentication-Identifier")
        path_match = any(s in path for s in M8FLOW_MASTER_REALM_PATH_SUBSTRINGS)
        has_master_config = _has_master_auth_config()
        master_identifier = _master_realm_identifier()

        if has_bearer and not cookie_id and not header_id and path_match and has_master_config:
            return master_identifier

        if has_bearer and not cookie_id and not header_id:
            derived = _authentication_identifier_from_bearer_token()
            if derived:
                return derived

        realm_hint = request.cookies.get("m8flow_auth_realm")
        if isinstance(realm_hint, str):
            realm_hint = realm_hint.strip() or None

        identifier = original()
        if isinstance(identifier, str):
            normalized_identifier = identifier.strip()
            if normalized_identifier and normalized_identifier in _auth_config_identifiers():
                return normalized_identifier

        if realm_hint:
            return realm_hint

        return identifier

    authentication_controller._get_authentication_identifier_from_request = (
        _patched_get_authentication_identifier_from_request
    )
    _MASTER_REALM_PATCHED = True
    logger.info(
        "master_realm_auth_patch: global tenant-management endpoints may use %r when Bearer is present, no identifier is supplied, and the configured admin auth config exists.",
        _master_realm_identifier(),
    )


def _handle_tenant_login_request(flask_app):
    """Handle tenant-selected login redirects and return a response when intercepted."""
    from flask import jsonify, redirect, request
    from m8flow_backend.services.tenant_service import TenantService
    from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME
    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    api_prefix = flask_app.config.get("SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX", "/v1.0")
    if not request.path.startswith(api_prefix) or not request.path.rstrip("/").endswith("/login"):
        return None
    if request.method != "GET":
        return None

    # If the user previously authenticated with master realm (tracked by a long-lived cookie),
    # redirect them back to master realm login even when the short-lived authentication_identifier
    # cookie has been cleared by session expiry. This prevents master realm users from being
    # redirected to the shared realm after their token expires.
    master_id = _master_realm_identifier()
    realm_hint = request.cookies.get("m8flow_auth_realm")
    if realm_hint == master_id and not request.args.get("tenant"):
        requested_id = (
            request.args.get("authentication_identifier")
            or request.cookies.get("authentication_identifier")
            or ""
        )
        if requested_id != master_id:
            realm_redirect_url = request.args.get("redirect_url") or flask_app.config.get(
                "SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "/"
            )
            realm_frontend_url = str(flask_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))
            if not _is_allowed_frontend_redirect_url(realm_redirect_url, realm_frontend_url):
                realm_redirect_url = realm_frontend_url or "/"
            login_redirect_url = AuthenticationService().get_login_redirect_url(
                authentication_identifier=master_id,
                final_url=realm_redirect_url,
            )
            return redirect(login_redirect_url)

    tenant = request.args.get("tenant")
    if not tenant or not str(tenant).strip():
        return None
    tenant = str(tenant).strip()

    redirect_url = request.args.get("redirect_url") or flask_app.config.get(
        "SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "/"
    )
    frontend_url = str(flask_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""))
    if not _is_allowed_frontend_redirect_url(redirect_url, frontend_url):
        return jsonify({"detail": "Invalid redirect_url"}), 400

    tenant_exists = TenantService.check_tenant_exists(tenant)
    if not tenant_exists.get("exists"):
        return jsonify({"detail": "Tenant not found"}), 404

    finalized_response = _finalize_tenant_from_existing_shared_realm_session(
        selected_tenant_alias=tenant,
        selected_tenant_id=tenant_exists["tenant_id"],
        redirect_url=redirect_url,
    )
    if finalized_response is not None:
        return finalized_response

    login_redirect_url = AuthenticationService().get_login_redirect_url(
        authentication_identifier=_shared_realm_identifier(),
        final_url=redirect_url,
    )
    response = redirect(login_redirect_url)
    response.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_exists["tenant_id"], path="/")
    return response


def _origin_tuple(url: str) -> tuple[str, str, int | None] | None:
    """Return normalized (scheme, host, port) for absolute URLs."""
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return None

    if not parsed.scheme or not parsed.hostname:
        return None

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None

    if port is None:
        if scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443

    return (scheme, host, port)


def _is_allowed_frontend_redirect_url(redirect_url: str, frontend_url: str) -> bool:
    """
    Allow:
    - Relative paths (`/tasks`, `/tasks?foo=bar`) for same-origin frontend redirects.
    - Absolute URLs whose origin exactly matches SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND.
    Reject:
    - Prefix tricks like `https://app.example.com.evil.com`.
    - Scheme-relative URLs (`//evil.com`).
    """
    redirect = (redirect_url or "").strip()
    frontend = (frontend_url or "").strip()

    if not frontend:
        return True

    frontend_origin = _origin_tuple(frontend)
    if frontend_origin is None:
        return False

    if redirect.startswith("/") and not redirect.startswith("//"):
        return True

    redirect_origin = _origin_tuple(redirect)
    if redirect_origin is None:
        return False

    return redirect_origin == frontend_origin


def _finalize_tenant_from_existing_shared_realm_session(
    selected_tenant_alias: str,
    selected_tenant_id: str,
    redirect_url: str,
):
    """
    Finalize tenant selection locally when the browser already has an app session.

    This avoids a second OIDC round-trip after the user has already authenticated
    against the shared realm. It also lets us synchronize tenant-scoped local
    groups from the selected organization without asking for the password again.
    """
    from flask import current_app, jsonify, redirect, request
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.authorization_service import AuthorizationService

    explicit_finalization = str(request.args.get("tenant_finalization", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not explicit_finalization:
        return None

    authentication_identifier = request.args.get("authentication_identifier") or request.cookies.get(
        "authentication_identifier"
    )
    if authentication_identifier != _shared_realm_identifier():
        return None

    session_token = request.cookies.get("access_token") or request.cookies.get("id_token")
    if not session_token:
        return None

    try:
        decoded_token = AuthenticationService.parse_jwt_token(authentication_identifier, session_token)
    except Exception:
        logger.warning(
            "tenant_finalization: unable to parse existing shared-realm session; falling back to standard login"
        )
        return None

    organization_memberships = organization_memberships_from_payload(decoded_token)
    organization_aliases = {
        organization_alias
        for organization_alias, _organization_details in organization_memberships
    }
    if not organization_aliases:
        logger.warning(
            "tenant_finalization: shared-realm session lacked organization memberships; falling back to standard login"
        )
        return None

    if selected_tenant_alias not in organization_aliases:
        return jsonify({"detail": "Selected tenant is not available for this session"}), 403

    synchronized_token = _synchronize_selected_organization_claims(
        decoded_token,
        selected_tenant_alias=selected_tenant_alias,
        selected_tenant_id=selected_tenant_id,
    )

    with _temporary_request_tenant(selected_tenant_id):
        user_model = AuthorizationService.create_user_from_sign_in(synchronized_token)

    tld = current_app.config["THREAD_LOCAL_DATA"]
    tld.new_access_token = user_model.encode_auth_token(_tenant_scoped_session_claims(synchronized_token))
    tld.new_authentication_identifier = _shared_realm_identifier()

    from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME

    response = redirect(redirect_url)
    response.set_cookie(SELECTED_TENANT_COOKIE_NAME, selected_tenant_id, path="/")
    return authentication_controller._set_new_access_token_in_cookie(response)


def _synchronize_selected_organization_claims(
    decoded_token: dict,
    *,
    selected_tenant_alias: str,
    selected_tenant_id: str,
) -> dict:
    """
    Enrich a shared-realm login token with the selected organization's local groups.

    The initial shared-realm sign-in uses ``organization:*`` so Keycloak can
    prompt for organization choice after credentials. Those first-hop tokens may
    list organization aliases but omit org-local role groups. Before local group
    synchronization runs, fetch the selected organization membership/groups from
    Keycloak and rewrite the payload to one active organization.
    """
    if not isinstance(decoded_token, dict):
        return decoded_token

    synchronized_token = dict(decoded_token)

    try:
        from m8flow_backend.services.keycloak_service import get_organization_by_alias
        from m8flow_backend.services.keycloak_service import get_organization_by_id
        from m8flow_backend.services.keycloak_service import get_organization_member_by_username
        from m8flow_backend.services.keycloak_service import get_organization_member_groups
    except Exception:
        logger.warning("tenant_finalization: unable to import Keycloak organization helpers", exc_info=True)
        synchronized_token["organization"] = {
            selected_tenant_alias: {"id": selected_tenant_id, "groups": []}
        }
        synchronized_token["m8flow_tenant_id"] = selected_tenant_id
        synchronized_token[TENANT_ALIAS_CLAIM] = selected_tenant_alias
        return synchronized_token

    organization = get_organization_by_alias(selected_tenant_alias)
    if not isinstance(organization, dict):
        try:
            organization = get_organization_by_id(selected_tenant_id)
        except Exception:
            organization = None
            logger.warning(
                "tenant_finalization: unable to resolve organization by selected tenant id",
                extra={"selected_tenant_id": selected_tenant_id, "selected_tenant_alias": selected_tenant_alias},
                exc_info=True,
            )
    if not isinstance(organization, dict):
        synchronized_token["organization"] = {
            selected_tenant_alias: {"id": selected_tenant_id, "groups": []}
        }
        synchronized_token["m8flow_tenant_id"] = selected_tenant_id
        synchronized_token[TENANT_ALIAS_CLAIM] = selected_tenant_alias
        return synchronized_token

    organization_id = organization.get("id")
    if not isinstance(organization_id, str) or not organization_id.strip():
        organization_id = selected_tenant_id
    else:
        organization_id = organization_id.strip()

    member_id = decoded_token.get("sub")
    if isinstance(member_id, str):
        member_id = member_id.strip()
    else:
        member_id = ""

    organization_groups: list[dict] = []
    if member_id:
        try:
            organization_groups = get_organization_member_groups(organization_id, member_id)
        except Exception:
            logger.warning(
                "tenant_finalization: unable to fetch organization groups by subject",
                extra={"organization_id": organization_id, "member_id": member_id},
                exc_info=True,
            )

    if not organization_groups:
        username = decoded_token.get("preferred_username")
        if isinstance(username, str) and username.strip():
            try:
                member = get_organization_member_by_username(organization_id, username.strip())
            except Exception:
                member = None
                logger.warning(
                    "tenant_finalization: unable to resolve organization member by username",
                    extra={"organization_id": organization_id, "username": username.strip()},
                    exc_info=True,
                )
            if isinstance(member, dict):
                member_id = member.get("id")
                if isinstance(member_id, str) and member_id.strip():
                    try:
                        organization_groups = get_organization_member_groups(organization_id, member_id.strip())
                    except Exception:
                        logger.warning(
                            "tenant_finalization: unable to fetch organization groups by member lookup",
                            extra={"organization_id": organization_id, "member_id": member_id.strip()},
                            exc_info=True,
                        )

    normalized_group_paths: list[str] = []
    seen_group_paths: set[str] = set()
    for organization_group in organization_groups:
        if not isinstance(organization_group, dict):
            continue
        group_path = organization_group.get("path")
        if not isinstance(group_path, str) or not group_path.strip():
            group_name = organization_group.get("name")
            if isinstance(group_name, str) and group_name.strip():
                group_path = f"/{group_name.strip()}"
            else:
                continue
        normalized_group_path = normalize_organizational_group_identifier(group_path.strip()).lstrip("/")
        if normalized_group_path and normalized_group_path not in seen_group_paths:
            seen_group_paths.add(normalized_group_path)
            normalized_group_paths.append(normalized_group_path)

    synchronized_organization_details = {
        "id": organization_id,
        "groups": normalized_group_paths,
    }
    organization_name = organization.get("name")
    if isinstance(organization_name, str) and organization_name.strip():
        synchronized_organization_details["name"] = organization_name.strip()

    synchronized_token["organization"] = {
        selected_tenant_alias: synchronized_organization_details
    }
    synchronized_token["m8flow_tenant_id"] = selected_tenant_id
    synchronized_token[TENANT_ALIAS_CLAIM] = selected_tenant_alias

    if isinstance(organization_name, str) and organization_name.strip():
        synchronized_token[TENANT_NAME_CLAIM] = organization_name.strip()

    return synchronized_token


def _tenant_scoped_session_claims(synchronized_token: dict) -> dict:
    """Create a backend-signed tenant-scoped session payload from the selected org claims."""
    if not isinstance(synchronized_token, dict):
        return {}

    allowed_claim_keys = (
        "organization",
        "roles",
        "name",
        "given_name",
        "family_name",
        "email_verified",
        "m8flow_authentication_identifier",
        "m8flow_realm_name",
        "m8flow_realm_id",
        TENANT_ALIAS_CLAIM,
        TENANT_NAME_CLAIM,
        "m8flow_tenant_id",
    )

    claims: dict[str, object] = {}
    for key in allowed_claim_keys:
        value = synchronized_token.get(key)
        if value is not None:
            claims[key] = value

    if "m8flow_authentication_identifier" not in claims:
        claims["m8flow_authentication_identifier"] = _shared_realm_identifier()

    return claims


def apply_login_tenant_patch(flask_app) -> None:
    """Register a before_request handler to intercept login when tenant param is present."""
    if getattr(flask_app, "_m8flow_login_tenant_patch_applied", False):
        return

    from m8flow_backend.services.auth_config_service import (
        ensure_master_auth_config,
        ensure_realm_identifier_in_auth_configs,
    )

    ensure_realm_identifier_in_auth_configs(flask_app)
    ensure_master_auth_config(flask_app)

    def before_login_tenant():
        """Short-circuit standard login handling when a tenant login redirect is requested."""
        resp = _handle_tenant_login_request(flask_app)
        if resp is not None:
            return resp

    before_login_tenant._m8flow_login_tenant_patch = True  # type: ignore[attr-defined]
    before_request_funcs = flask_app.before_request_funcs.setdefault(None, [])
    if any(getattr(func, "_m8flow_login_tenant_patch", False) for func in before_request_funcs):
        flask_app._m8flow_login_tenant_patch_applied = True
        return

    flask_app.before_request(before_login_tenant)
    flask_app._m8flow_login_tenant_patch_applied = True
    logger.info("login_tenant_patch: applied tenant-aware login redirect")
