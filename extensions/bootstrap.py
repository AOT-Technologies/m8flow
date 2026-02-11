# bootstrap.py
# Extension bootstrap code for M8Flow-specific patches.
# This module is imported by extensions/app.py before creating the app.
# Add any other extension-wide initialization code here.
# This file is part of the M8Flow extension to SpiffWorkflow Backend.
#
# ensure_m8flow_audit_timestamps() is intended to be called from app.py after
# tenant re-import and db imports (so m8flow models are loaded).



def apply_extension_patches() -> None:
    """Apply extension patches that do not require the Flask app instance."""
    try:
        from extensions.openid_discovery_patch import apply_openid_discovery_patch
        apply_openid_discovery_patch()
    except ImportError:
        pass
    try:
        from extensions.auth_token_error_patch import apply_auth_token_error_patch
        apply_auth_token_error_patch()
    except ImportError:
        pass
    try:
        from extensions.decode_token_debug_patch import apply_decode_token_debug_patch
        apply_decode_token_debug_patch()
    except ImportError:
        pass
    try:
        from extensions.create_user_tenant_scope_patch import apply_create_user_tenant_scope_patch
        apply_create_user_tenant_scope_patch()
    except ImportError:
        pass
    # M8Flow: allow tenant-login-url (and other public endpoints) without authentication
    try:
        from extensions.auth_exclusion_patch import apply_auth_exclusion_patch
        apply_auth_exclusion_patch()
    except ImportError:
        pass
    # M8Flow: create-realm/create-tenant accept Keycloak master realm token when no auth identifier set
    try:
        from extensions.master_realm_auth_patch import apply_master_realm_auth_patch
        apply_master_realm_auth_patch()
    except ImportError:
        pass


def bootstrap() -> None:
    from m8flow_backend.services.authorization_service_patch import apply as apply_authorization_service_patch
    from m8flow_backend.services.auth_controller_patch import apply as apply_auth_controller_patch
    from m8flow_backend.services.spiff_config_patch import apply as apply_spiff_config_patch
    from m8flow_backend.services.model_override_patch import apply as apply_model_override_patch
    from m8flow_backend.services.file_system_service_patch import apply as apply_file_system_service_patch
    from m8flow_backend.services.tenant_scoping_patch import apply as apply_tenant_scoping_patch
    from m8flow_backend.services.openapi_merge_patch import apply as apply_openapi_merge_patch
    from m8flow_backend.services.logging_service_patch import apply as apply_logging_service_patch
    apply_openapi_merge_patch()
    apply_auth_controller_patch()
    apply_spiff_config_patch()
    apply_model_override_patch()
    apply_file_system_service_patch()
    apply_tenant_scoping_patch()
    apply_logging_service_patch()
    apply_authorization_service_patch()
    apply_extension_patches()


def ensure_m8flow_audit_timestamps() -> None:
    """Ensure m8flow models that use AuditDateTimeMixin participate in Spiff's timestamp listeners."""
    from m8flow_backend.models._timestamps_bootstrap import apply as apply_m8flow_timestamp_listeners
    apply_m8flow_timestamp_listeners()
