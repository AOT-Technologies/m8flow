# extensions/startup/tenant_resolution.py
from __future__ import annotations

from typing import Any


def _view_function_sets_tenant_context(view_function: Any) -> bool:
    visited: set[int] = set()
    while view_function is not None and id(view_function) not in visited:
        visited.add(id(view_function))
        if getattr(view_function, "_m8flow_sets_tenant_context", False):
            return True
        view_function = getattr(view_function, "__wrapped__", None)
    return False


def _request_controller_sets_tenant_context(flask_app) -> bool:
    from flask import request

    endpoint = getattr(request, "endpoint", None)
    if not endpoint:
        return False
    return _view_function_sets_tenant_context(flask_app.view_functions.get(endpoint))


def register_tenant_resolution_after_auth(flask_app) -> None:
    from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant

    def _resolve_tenant_after_auth():
        if _request_controller_sets_tenant_context(flask_app):
            return None
        return resolve_request_tenant()

    def _is_auth_before_request(func) -> bool:
        mod = getattr(func, "__module__", "") or ""
        name = getattr(func, "__name__", "") or ""
        return (
            # Unpatched upstream callback registered by create_app()
            (mod == "spiffworkflow_backend.routes.authentication_controller" and name == "omni_auth")
            # Patched callback shape (if omni_auth is monkey-patched before registration)
            or (mod.endswith("authentication_controller_patch") and name == "patched_omni_auth")
        )

    if None not in flask_app.before_request_funcs:
        flask_app.before_request_funcs[None] = []
    funcs = flask_app.before_request_funcs[None]

    # Idempotency: avoid duplicate registrations on repeated startup calls in tests.
    if any(getattr(f, "__name__", "") == "_resolve_tenant_after_auth" for f in funcs):
        return

    for i, func in enumerate(funcs):
        if _is_auth_before_request(func):
            funcs.insert(i + 1, _resolve_tenant_after_auth)
            return

    flask_app.before_request(_resolve_tenant_after_auth)
