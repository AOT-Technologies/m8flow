# extensions/startup/tenant_resolution.py

def register_tenant_resolution_after_auth(flask_app) -> None:
    from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant

    def _resolve_tenant_after_auth():
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
