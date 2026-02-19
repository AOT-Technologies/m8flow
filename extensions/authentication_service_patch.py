# extensions/authentication_service_patch.py
"""Patches to spiffworkflow_backend.services.authentication_service:
- On-demand tenant auth config (authentication_option_for_identifier)
- Keycloak token error surfacing (get_auth_token_object)
- OpenID discovery status check (open_id_endpoint_for_name)
"""

from security import safe_requests  # type: ignore
import requests

from spiffworkflow_backend.config import HTTP_REQUEST_TIMEOUT_SECONDS
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.exceptions.error import OpenIdConnectionError
from spiffworkflow_backend.services.authentication_service import AuthenticationService

# --- On-demand tenant auth config ---
# On-demand tenant config requires extensions.login_tenant_patch; if that module is missing,
# unknown identifiers still raise AuthenticationOptionNotFoundError (no hard dependency).
_ON_DEMAND_PATCHED = False


def apply_auth_config_on_demand_patch() -> None:
    """Patch AuthenticationService.authentication_option_for_identifier to add tenant config on demand."""
    global _ON_DEMAND_PATCHED
    if _ON_DEMAND_PATCHED:
        return
    from spiffworkflow_backend.services.authentication_service import (
        AuthenticationOptionNotFoundError,
        AuthenticationService,
    )

    _original = AuthenticationService.authentication_option_for_identifier

    @classmethod
    def _patched_authentication_option_for_identifier(cls, authentication_identifier: str):
        try:
            return _original.__func__(cls, authentication_identifier)
        except AuthenticationOptionNotFoundError as e:
            try:
                from m8flow_backend.services.keycloak_service import realm_exists
            except ImportError:
                raise e from e
            if not realm_exists(authentication_identifier):
                raise e from e
            try:
                from flask import current_app

                from extensions.login_tenant_patch import _ensure_tenant_auth_config

                _ensure_tenant_auth_config(current_app, authentication_identifier)
                return _original.__func__(cls, authentication_identifier)
            except ImportError:
                raise e from e

    AuthenticationService.authentication_option_for_identifier = (
        _patched_authentication_option_for_identifier
    )
    _ON_DEMAND_PATCHED = True


# --- Keycloak token error surfacing ---
_original_get_auth_token_object = None
_TOKEN_ERROR_PATCHED = False


def _patched_get_auth_token_object(self, code, authentication_identifier, pkce_id=None):
    result = _original_get_auth_token_object(self, code, authentication_identifier, pkce_id)
    if not isinstance(result, dict):
        return result
    if "id_token" in result:
        return result
    if "error" in result:
        err = result.get("error", "unknown")
        desc = result.get("error_description", result.get("error", ""))
        raise ApiError(
            error_code="keycloak_token_error",
            message=f"Keycloak token exchange failed: {err}. {desc}".strip(),
            status_code=401,
        )
    return result


def apply_auth_token_error_patch() -> None:
    """Patch get_auth_token_object so Keycloak token errors are surfaced to the user."""
    global _original_get_auth_token_object, _TOKEN_ERROR_PATCHED
    if _TOKEN_ERROR_PATCHED:
        return
    _original_get_auth_token_object = AuthenticationService.get_auth_token_object
    AuthenticationService.get_auth_token_object = _patched_get_auth_token_object
    _TOKEN_ERROR_PATCHED = True


# --- OpenID discovery status check ---
_OPENID_PATCHED = False


def _patched_open_id_endpoint_for_name(cls, name: str, authentication_identifier: str, internal: bool = False) -> str:
    """Same as original but raises OpenIdConnectionError when discovery returns non-200."""
    if authentication_identifier not in cls.ENDPOINT_CACHE:
        cls.ENDPOINT_CACHE[authentication_identifier] = {}
    if authentication_identifier not in cls.JSON_WEB_KEYSET_CACHE:
        cls.JSON_WEB_KEYSET_CACHE[authentication_identifier] = {}

    internal_server_url = cls.server_url(authentication_identifier, internal=True)
    openid_config_url = f"{internal_server_url}/.well-known/openid-configuration"
    if name not in cls.ENDPOINT_CACHE[authentication_identifier]:
        try:
            response = safe_requests.get(openid_config_url, timeout=HTTP_REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 200:
                raise OpenIdConnectionError(
                    f"OpenID discovery returned {response.status_code} for {openid_config_url}. "
                    "Check that the realm exists and Keycloak is reachable. "
                    f"Body: {(response.text or '')[:200]}"
                )
            cls.ENDPOINT_CACHE[authentication_identifier] = response.json()
        except requests.exceptions.ConnectionError as ce:
            raise OpenIdConnectionError(f"Cannot connect to given open id url: {openid_config_url}") from ce
    if name not in cls.ENDPOINT_CACHE[authentication_identifier]:
        raise Exception(f"Unknown OpenID Endpoint: {name}. Tried to get from {openid_config_url}")

    config: str = cls.ENDPOINT_CACHE[authentication_identifier].get(name, "")
    external_server_url = cls.server_url(authentication_identifier)
    if internal is False:
        if internal_server_url != external_server_url:
            config = config.replace(internal_server_url, external_server_url)
    return config


def apply_openid_discovery_patch() -> None:
    """Replace AuthenticationService.open_id_endpoint_for_name with a version that checks response status."""
    global _OPENID_PATCHED
    if _OPENID_PATCHED:
        return
    import spiffworkflow_backend.services.authentication_service as _auth_svc_mod

    _auth_svc_mod.AuthenticationService.open_id_endpoint_for_name = classmethod(
        _patched_open_id_endpoint_for_name
    )
    _OPENID_PATCHED = True
