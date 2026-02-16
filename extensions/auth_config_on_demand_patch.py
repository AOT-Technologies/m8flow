# extensions/auth_config_on_demand_patch.py
"""On-demand tenant auth config: when authentication_option_for_identifier would raise
AuthenticationOptionNotFoundError, ensure the identifier is a valid tenant realm, add its
config to SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS, then retry so any worker can decode tokens."""

_PATCHED = False


def apply_auth_config_on_demand_patch() -> None:
    """Patch AuthenticationService.authentication_option_for_identifier to add tenant config on demand."""
    global _PATCHED
    if _PATCHED:
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
            from flask import current_app

            from extensions.login_tenant_patch import _ensure_tenant_auth_config

            _ensure_tenant_auth_config(current_app, authentication_identifier)
            return _original.__func__(cls, authentication_identifier)

    AuthenticationService.authentication_option_for_identifier = (
        _patched_authentication_option_for_identifier
    )
    _PATCHED = True
