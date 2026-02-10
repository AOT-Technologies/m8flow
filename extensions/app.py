# extensions/app.py
import importlib.util
import logging
import os
from pathlib import Path
import sys
from flask import Flask, g
from extensions.bootstrap import bootstrap, ensure_m8flow_audit_timestamps
from extensions.env_var_mapper import apply_spiff_env_mapping
from m8flow_backend.services.asgi_tenant_context_middleware import AsgiTenantContextMiddleware
from m8flow_backend.tenancy import begin_request_context, end_request_context, clear_tenant_context


def _force_root_logging_for(prefixes: tuple[str, ...]) -> None:
    """
    Force selected loggers (and all their children) to:
      - have no handlers of their own
      - propagate to root (so uvicorn-log.yaml formatter/filter applies)
    """
    # Fix existing loggers already created
    for name, obj in logging.root.manager.loggerDict.items():
        if not isinstance(obj, logging.Logger):
            continue
        if name.startswith(prefixes):
            obj.handlers = []
            obj.propagate = True

    # Fix the parent loggers too (important)
    for name in prefixes:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def _strip_all_non_root_handlers() -> None:
    """
    Ensure root is the only place with handlers.
    Any logger-specific handlers bypass the root formatter/filter.
    """
    for name, obj in logging.root.manager.loggerDict.items():
        if isinstance(obj, logging.Logger):
            obj.handlers = []
            obj.propagate = True


logger = logging.getLogger(__name__)

# Map M8FLOW_* vars to SPIFF_* before any backend config loads.
apply_spiff_env_mapping()

# Apply model overrides before importing spiffworkflow_backend.
bootstrap()

import importlib
import sys

# Ensure tenant model is loaded after model overrides settle, using final db/base identity
sys.modules.pop("m8flow_backend.models.m8flow_tenant", None)
importlib.import_module("m8flow_backend.models.m8flow_tenant")

# Ensure m8flow migrations are importable and load the migrate module.
M8FLOW_MIGRATIONS_DIR = Path(__file__).resolve().parent / "m8flow-backend" / "migrations"
if str(M8FLOW_MIGRATIONS_DIR) not in sys.path:
    sys.path.insert(0, str(M8FLOW_MIGRATIONS_DIR))

try:
    from migrate import upgrade_if_enabled as upgrade_m8flow_db
except ModuleNotFoundError:
    migrate_path = M8FLOW_MIGRATIONS_DIR / "migrate.py"
    spec = importlib.util.spec_from_file_location("m8flow_migrate", migrate_path)
    if spec is None or spec.loader is None:
        raise
    migrate_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate_module)
    upgrade_m8flow_db = migrate_module.upgrade_if_enabled


from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from spiffworkflow_backend import create_app
from spiffworkflow_backend.models.db import db
from sqlalchemy import create_engine


def _env_truthy(value: str | None) -> bool:
    """Interpret environment variable value as boolean truthy."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configure_sql_echo(app) -> None:
    """Configure SQLAlchemy echo based on environment variable."""
    enable_sql_echo = _env_truthy(os.environ.get("M8FLOW_SQLALCHEMY_ECHO"))
    if not enable_sql_echo:
        return
    app.config["SQLALCHEMY_ECHO"] = True
    try:
        with app.app_context():
            db.engine.echo = True
    except Exception:
        pass


_strip_all_non_root_handlers()
_force_root_logging_for(("spiffworkflow_backend", "spiff", "alembic"))
import m8flow_backend.models.m8flow_tenant  # noqa: F401
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

logger.warning("Tenant tablename: %s", getattr(M8flowTenantModel, "__tablename__", None))
logger.warning("Tenant has __table__? %s", hasattr(M8flowTenantModel, "__table__"))
if hasattr(M8flowTenantModel, "__table__"):
    logger.warning("Tenant table name: %s", M8flowTenantModel.__table__.name)
    logger.warning("Tenant metadata is db.metadata? %s", M8flowTenantModel.__table__.metadata is db.metadata)
    logger.warning("Tenant metadata tables count: %s", len(M8flowTenantModel.__table__.metadata.tables))


def _assert_model_identity() -> None:
    """
    Fail fast if model overrides resulted in multiple db/base/metadata identities.
    This catches the "fragile import order" regressions early.
    """
    from spiffworkflow_backend.models.db import db, SpiffworkflowBaseDBModel
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

    # 1) Must be mapped (SQLAlchemy instrumentation happened)
    assert hasattr(M8flowTenantModel, "__table__"), (
        "M8flowTenantModel is not mapped yet (no __table__). "
        "This usually means the model module was imported before the final db/base was established."
    )

    # 2) Must be using the same MetaData object as the runtime db
    model_md = M8flowTenantModel.__table__.metadata
    db_md = db.metadata
    assert model_md is db_md, (
        "MetaData mismatch: M8flowTenantModel.__table__.metadata is not db.metadata.\n"
        f"  model metadata id={id(model_md)}\n"
        f"  db.metadata id={id(db_md)}\n"
        "This indicates two different SQLAlchemy registries/bases are in play "
        "(often caused by import order / overrides not settled)."
    )

    # 3) Must be derived from the expected base (guards against 'wrong base class' case)
    assert issubclass(M8flowTenantModel, SpiffworkflowBaseDBModel), (
        "Base class mismatch: M8flowTenantModel is not a subclass of SpiffworkflowBaseDBModel.\n"
        f"  tenant model base(s)={M8flowTenantModel.mro()}\n"
        "This indicates the model was built against a different declarative base."
    )

    # 4) Table must be registered in db.metadata.tables under the expected key.
    #    Key can differ from __tablename__ if schema is involved; check both.
    tablename = getattr(M8flowTenantModel, "__tablename__", None)
    assert tablename, "M8flowTenantModel.__tablename__ is missing."

    tables = db.metadata.tables
    if tablename not in tables:
        # fallback: look for exact Table object identity anywhere in metadata
        if all(tbl is not M8flowTenantModel.__table__ for tbl in tables.values()):
            raise AssertionError(
                "Tenant table not registered in db.metadata.tables.\n"
                f"  expected tablename='{tablename}'\n"
                f"  registered table keys={sorted(tables.keys())}\n"
            )


# Assert identity BEFORE create_app (fail fast on import/override ordering issues)
_assert_model_identity()

# TODO: Move these patch applications into the bootstrap functions. Refactor it to be more modular and 
# less fragile (currently relies on import order and global state). Each patch module can have its own apply() function that is called from bootstrap.
from m8flow_backend.services.user_service_patch import apply as apply_user_service_patch
apply_user_service_patch()
# Ensure m8flow models that use AuditDateTimeMixin participate in Spiff's
# timestamp listeners (created_at_in_seconds / updated_at_in_seconds).
ensure_m8flow_audit_timestamps()


# Create the Connexion app.
cnx_app = create_app()

# Register on the underlying Flask app
flask_app = getattr(cnx_app, "app", None)


def _register_request_active_hooks(app: Flask) -> None:
    @app.before_request
    def _m8flow_mark_request_active() -> None:
        # Mark the current execution as "in a request"
        g._m8flow_request_active_token = begin_request_context()

    @app.teardown_request
    def _m8flow_unmark_request_active(_exc: Exception | None) -> None:
        token = getattr(g, "_m8flow_request_active_token", None)
        if token is not None:
            end_request_context(token)
            g._m8flow_request_active_token = None


def _register_request_tenant_context_hooks(app: Flask) -> None:
    @app.before_request
    def _m8flow_before_request() -> None:
        # prevent cross-request leakage
        clear_tenant_context()

    @app.teardown_request
    def _m8flow_teardown_request(_exc: Exception | None) -> None:
        clear_tenant_context()


def _assert_db_engine_bound(app: Flask) -> None:
    from spiffworkflow_backend.models.db import db
    with app.app_context():
        assert db.engine is not None, "db.engine is not initialized/bound inside app_context."


def _m8flow_migration(app: Flask) -> None:
    """Run m8flow migrations at startup if enabled."""
    # Make sure everything flows through root (uvicorn-log.yaml formatter/filter)
    _strip_all_non_root_handlers()
    _force_root_logging_for(("spiffworkflow_backend", "spiff", "alembic"))

    # Ensure db is bound before migrating (defensive)
    _assert_db_engine_bound(app)

    # Run migrations now if enabled
    upgrade_m8flow_db()


_register_request_active_hooks(flask_app)
_register_request_tenant_context_hooks(flask_app)

# Assert again AFTER create_app (catches re-init/duplicate db/base during app creation)
_assert_model_identity()
_assert_db_engine_bound(flask_app)

# Run migrations at startup 
_m8flow_migration(flask_app)

if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# Configure SQL echo if enabled
_configure_sql_echo(flask_app)

m8flow_templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
if m8flow_templates_dir:
    flask_app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = m8flow_templates_dir
    logger.info(f"M8FLOW_TEMPLATES_STORAGE_DIR configured: {m8flow_templates_dir}")

# Register the tenant loading function to run after auth hooks.
if None not in flask_app.before_request_funcs:
    flask_app.before_request_funcs[None] = []
before_request_funcs = flask_app.before_request_funcs[None]
try:
    from spiffworkflow_backend.routes.authentication_controller import omni_auth
    auth_index = before_request_funcs.index(omni_auth)
    before_request_funcs.insert(auth_index + 1, resolve_request_tenant)
except Exception:
    flask_app.before_request(resolve_request_tenant)


# Wrap ASGI app so uvicorn/connexion/starlette logs can see ContextVar tenant.
cnx_app = AsgiTenantContextMiddleware(cnx_app)

# Expose the Connexion app
app = cnx_app

logging.getLogger(__name__).warning(
    "Registered tables AFTER create_app: %s",
    sorted(db.metadata.tables.keys()),
)
