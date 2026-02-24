from __future__ import annotations

from spiffworkflow_backend.routes import authentication_controller
from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant

_PATCHED = False

def apply() -> None:
    """Patch the authentication controller to resolve tenant after auth."""
    global _PATCHED
    if _PATCHED:
        return

    original = authentication_controller.omni_auth

    def patched_omni_auth(*args, **kwargs):
        rv = original(*args, **kwargs)
        # resolve tenant as soon as auth has populated g.token/cookies (uses canonical db)
        resolve_request_tenant()
        return rv

    authentication_controller.omni_auth = patched_omni_auth  # type: ignore[assignment]
    _PATCHED = True
