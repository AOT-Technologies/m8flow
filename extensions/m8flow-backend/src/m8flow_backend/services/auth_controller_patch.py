from __future__ import annotations

from flask import current_app

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
        # resolve tenant as soon as auth has populated g.token/cookies
        # db must be the instance bound to the current app so tenant validation uses the same engine/session
        db = current_app.extensions["sqlalchemy"]
        resolve_request_tenant(db)
        return rv

    authentication_controller.omni_auth = patched_omni_auth  # type: ignore[assignment]
    _PATCHED = True
