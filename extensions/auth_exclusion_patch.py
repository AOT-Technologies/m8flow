# extensions/auth_exclusion_patch.py
# Add M8Flow public API endpoints to the auth exclusion list so they can be called without login.
# Does not modify spiffworkflow_backend; only patches AuthorizationService.authentication_exclusion_list.

import logging

logger = logging.getLogger(__name__)

# Endpoints that must be callable without authentication (pre-login tenant selection, tenant login URL).
M8FLOW_AUTH_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.get_tenant_login_url",
]


def apply_auth_exclusion_patch() -> None:
    """Patch AuthorizationService.authentication_exclusion_list to include M8Flow public endpoints."""
    from spiffworkflow_backend.services import authorization_service

    _original = authorization_service.AuthorizationService.authentication_exclusion_list

    @classmethod
    def _patched_authentication_exclusion_list(cls) -> list:
        result = _original.__func__(cls)  # call original classmethod with cls
        for path in M8FLOW_AUTH_EXCLUSION_ADDITIONS:
            if path not in result:
                result = list(result) + [path]
        return result

    authorization_service.AuthorizationService.authentication_exclusion_list = _patched_authentication_exclusion_list
    logger.info("auth_exclusion_patch: added %s to authentication_exclusion_list", M8FLOW_AUTH_EXCLUSION_ADDITIONS)
