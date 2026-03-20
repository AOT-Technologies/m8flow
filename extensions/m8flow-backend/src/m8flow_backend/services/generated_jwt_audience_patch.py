from __future__ import annotations

DEFAULT_AUDIENCE = "m8flow-backend"

_PATCHED = False


def apply() -> None:
    """Override the upstream generated JWT audience for M8Flow runtime tokens."""
    global _PATCHED
    if _PATCHED:
        return

    import spiffworkflow_backend.models.user as user_module
    import spiffworkflow_backend.services.authentication_service as authentication_service_module

    user_module.SPIFF_GENERATED_JWT_AUDIENCE = DEFAULT_AUDIENCE
    authentication_service_module.SPIFF_GENERATED_JWT_AUDIENCE = DEFAULT_AUDIENCE
    _PATCHED = True
