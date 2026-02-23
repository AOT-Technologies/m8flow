# extensions/auth_exclusion_patch.py
"""Patches AuthorizationService.authentication_exclusion_list in spiffworkflow_backend.services.authorization_service."""

import logging

logger = logging.getLogger(__name__)
_PATCHED = False

# Endpoints that must be callable without authentication (pre-login tenant selection, tenant login URL,
# bootstrap: create realm / create tenant — no tenant in token yet; Keycloak admin is server-side;
# health for ALB/load balancer checks).
M8FLOW_AUTH_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.get_tenant_login_url",
    "m8flow_backend.routes.keycloak_controller.create_realm",
    "m8flow_backend.routes.tenant_controller.create_tenant",
    "m8flow_backend.tenancy.health_check",
]


def apply_auth_exclusion_patch() -> None:
    """Patch AuthorizationService.authentication_exclusion_list to include M8Flow public endpoints."""
    global _PATCHED
    if _PATCHED:
        return
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
    _PATCHED = True
    logger.info("auth_exclusion_patch: added %s to authentication_exclusion_list", M8FLOW_AUTH_EXCLUSION_ADDITIONS)
