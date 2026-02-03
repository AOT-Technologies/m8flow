# extensions/auth_token_error_patch.py
# When Keycloak token endpoint returns an error (e.g. invalid_grant, redirect_uri mismatch),
# surface it as an ApiError instead of the generic "missing_token".
# All changes stay in extensions; spiffworkflow_backend is not modified.

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.services.authentication_service import AuthenticationService

_original_get_auth_token_object = None


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
    global _original_get_auth_token_object
    _original_get_auth_token_object = AuthenticationService.get_auth_token_object
    AuthenticationService.get_auth_token_object = _patched_get_auth_token_object
