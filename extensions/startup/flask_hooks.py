# extensions/startup/flask_hooks.py
from flask import Flask, g
from m8flow_backend.tenancy import begin_request_context, end_request_context, clear_tenant_context
from extensions.startup.guard import require_at_least, BootPhase

def register_request_active_hooks(app: Flask) -> None:
    if getattr(app, "_m8flow_request_active_hooks_registered", False):
        return

    @app.before_request
    def _m8flow_mark_request_active() -> None:
        g._m8flow_request_active_token = begin_request_context()

    @app.teardown_request
    def _m8flow_unmark_request_active(_exc) -> None:
        token = getattr(g, "_m8flow_request_active_token", None)
        if token is not None:
            end_request_context(token)
            g._m8flow_request_active_token = None

    app._m8flow_request_active_hooks_registered = True

def register_request_tenant_context_hooks(app: Flask) -> None:
    if getattr(app, "_m8flow_request_tenant_hooks_registered", False):
        return

    @app.before_request
    def _m8flow_before_request() -> None:
        clear_tenant_context()

    @app.teardown_request
    def _m8flow_teardown_request(_exc) -> None:
        clear_tenant_context()

    app._m8flow_request_tenant_hooks_registered = True

def assert_db_engine_bound(app):
    require_at_least(BootPhase.APP_CREATED, what="db.engine access")
    from spiffworkflow_backend.models.db import db
    with app.app_context():
        _ = db.engine
