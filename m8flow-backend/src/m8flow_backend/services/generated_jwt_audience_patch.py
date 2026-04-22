from __future__ import annotations

DEFAULT_AUDIENCE = "m8flow-backend"

_PATCHED = False


def apply() -> None:
    """Override the upstream generated JWT audience for M8Flow runtime tokens."""
    global _PATCHED
    if _PATCHED:
        return

    import m8flow_backend.models.user as m8flow_user_module
    import spiffworkflow_backend.models.user as user_module
    import spiffworkflow_backend.services.authentication_service as authentication_service_module

    # The model override copies objects from m8flow_backend.models.user into the
    # spiffworkflow_backend.models.user namespace. Methods like
    # UserModel.encode_auth_token() still resolve module globals from the source
    # module, so patch both modules to keep token generation and verification in sync.
    m8flow_user_module.SPIFF_GENERATED_JWT_AUDIENCE = DEFAULT_AUDIENCE
    user_module.SPIFF_GENERATED_JWT_AUDIENCE = DEFAULT_AUDIENCE
    authentication_service_module.SPIFF_GENERATED_JWT_AUDIENCE = DEFAULT_AUDIENCE
    _PATCHED = True
