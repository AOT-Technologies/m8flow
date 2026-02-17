# extensions/openid_discovery_patch.py
# Monkey-patch OpenID discovery to raise a clear error when Keycloak returns 404/5xx
# instead of caching the error body and raising "Unknown OpenID Endpoint".
# All changes stay in extensions; spiffworkflow_backend is not modified.
#
# IMPORTANT: This patch only runs when the backend is started with the extensions app
# (e.g. "uvicorn extensions.app:app" from repo root with PYTHONPATH=.). If you start
# the backend with "./bin/run_server_locally" (spiff_web_server), the patch is not loaded.

from security import safe_requests  # type: ignore
import requests

from spiffworkflow_backend.config import HTTP_REQUEST_TIMEOUT_SECONDS
from spiffworkflow_backend.exceptions.error import OpenIdConnectionError
from spiffworkflow_backend.services.authentication_service import AuthenticationService


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
    if internal is True:
        discovery_issuer = cls.ENDPOINT_CACHE[authentication_identifier].get("issuer") or ""
        if discovery_issuer and discovery_issuer != internal_server_url:
            config = config.replace(discovery_issuer, internal_server_url)
    elif internal is False:
        if internal_server_url != external_server_url:
            config = config.replace(internal_server_url, external_server_url)
    return config


def apply_openid_discovery_patch() -> None:
    """Replace AuthenticationService.open_id_endpoint_for_name with a version that checks response status.
    Patch via the defining module so the same class used by authentication_controller is patched.
    """
    import spiffworkflow_backend.services.authentication_service as _auth_svc_mod
    # Force Keycloak logic to use HTTP internally by disabling the secure connection requirement if possible
    # or by intercepting the request logic.
    # The error "HTTPS required" comes from Keycloak itself (ssl-required=external or all).
    # Since we are running locally (http://localhost:7002), we need to make sure Keycloak allows HTTP.
    
    # We can also monkeypatch `open_id_endpoint_for_name` to handle this but the issue is Keycloak config.
    # However, if we can't change Keycloak config easily, we might need to pretend we are HTTPS or fix the URL?
    # The URL is http://localhost:7002.
    
    _auth_svc_mod.AuthenticationService.open_id_endpoint_for_name = classmethod(
        _patched_open_id_endpoint_for_name
    )
