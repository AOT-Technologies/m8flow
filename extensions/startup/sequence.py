# extensions/startup/sequence.py
import os
from collections.abc import Callable
from typing import Any

from extensions.startup.env_var_mapper import apply_m8flow_env_mapping
from extensions.bootstrap import bootstrap, bootstrap_after_app, ensure_m8flow_audit_timestamps

from extensions.startup.logging_setup import harden_logging
from extensions.startup.migrations import load_migration_runner, run_migrations_if_enabled
from extensions.startup.model_identity import assert_model_identity
from extensions.startup.config import (
    configure_sql_echo,
    configure_templates_dir,
    configure_permissions_yml,
)
from extensions.startup.routes import register_template_file_fallback_routes
from extensions.startup.flask_hooks import (
    register_request_active_hooks,
    register_request_tenant_context_hooks,
    assert_db_engine_bound,
)
from extensions.startup.tenant_resolution import register_tenant_resolution_after_auth
from extensions.startup.auth_patches import apply_extension_patches_after_app

from m8flow_backend.services.asgi_tenant_context_middleware import AsgiTenantContextMiddleware
from extensions.startup.guard import set_phase, BootPhase


def _prepare_pre_app_boot() -> tuple[Any, Callable[[], None]]:
    set_phase(BootPhase.PRE_BOOTSTRAP)

    # Logging hardening as early as possible (safe even before patches).
    harden_logging()

    # Map env vars before backend config loads.
    apply_m8flow_env_mapping()

    # Apply model overrides + extension patches that do NOT need Flask app.
    bootstrap()
    set_phase(BootPhase.POST_BOOTSTRAP)

    from extensions.startup.import_contracts import import_spiff_db

    db = import_spiff_db()
    upgrade_m8flow_db = load_migration_runner()

    # Identity guard before create_app() (fail fast).
    assert_model_identity()
    return db, upgrade_m8flow_db


def _create_connexion_app() -> Any:
    # IMPORTANT: import spiff only after bootstrap/overrides.
    from spiffworkflow_backend import create_app as create_spiff_app

    return create_spiff_app()


def _configure_created_app(cnx_app: Any, db: Any, upgrade_m8flow_db: Callable[[], None]) -> None:
    flask_app = getattr(cnx_app, "app", None)
    if flask_app is None:
        raise RuntimeError("Could not access underlying Flask app from Connexion app")

    set_phase(BootPhase.APP_CREATED)

    # App-dependent patches (allowed to import models now).
    bootstrap_after_app(flask_app)

    # Canonical db (single db instance everywhere).
    from m8flow_backend.canonical_db import set_canonical_db

    set_canonical_db(db)

    # Flask request lifecycle hooks.
    register_request_active_hooks(flask_app)
    register_request_tenant_context_hooks(flask_app)

    # Register fallback routes (defensive).
    register_template_file_fallback_routes(flask_app)

    # Identity guard + db engine bound after create_app.
    assert_model_identity()
    assert_db_engine_bound(flask_app)

    # Run migrations at startup (after db bound).
    run_migrations_if_enabled(flask_app, upgrade_m8flow_db)

    # Permissions + templates configuration.
    configure_permissions_yml(flask_app)
    configure_templates_dir(flask_app)
    configure_sql_echo(flask_app, db)

    # Tenant resolution ordering (after omni_auth when present).
    register_tenant_resolution_after_auth(flask_app)

    # App-dependent patches (login tenant patch, auth config on demand, etc.).
    apply_extension_patches_after_app(flask_app)

    # Ensure m8flow AuditDateTimeMixin timestamp listeners are attached.
    ensure_m8flow_audit_timestamps()


def _wrap_asgi_if_needed(cnx_app: Any) -> Any:
    # Wrap ASGI app so logs can see ContextVar tenant.
    # Keep upstream Starlette CORSMiddleware as the only CORS handler.
    env = os.environ.get("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    if env not in ("unit_testing", "testing"):
        return AsgiTenantContextMiddleware(cnx_app)
    return cnx_app


def create_application() -> Any:
    db, upgrade_m8flow_db = _prepare_pre_app_boot()
    cnx_app = _create_connexion_app()
    _configure_created_app(cnx_app, db, upgrade_m8flow_db)
    return _wrap_asgi_if_needed(cnx_app)
