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
apply_login_tenant_patch = None
try:
    from extensions.login_tenant_patch import apply_login_tenant_patch
except ImportError:
    pass
try:
    from extensions.cookie_path_patch import apply_cookie_path_patch
    apply_cookie_path_patch()
except ImportError:
    pass

from m8flow_backend.services.tenant_context_middleware import resolve_request_tenant
from spiffworkflow_backend import create_app
from spiffworkflow_backend.models.db import db

# Unauthenticated tenant check for pre-login tenant selection (no tenant context required)
TENANT_PUBLIC_PATH_PREFIXES = ("/tenants/check", "/m8flow/tenant-login-url")


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

# Ensure m8flow models that use AuditDateTimeMixin participate in Spiff's
# timestamp listeners (created_at_in_seconds / updated_at_in_seconds).
ensure_m8flow_audit_timestamps()

# Create the Connexion app.
cnx_app = create_app()

# Add CORS for local frontend; only add headers if not already set (avoids duplicate with upstream).

_LOCAL_CORS_ORIGINS = frozenset(["http://localhost:7001", "http://127.0.0.1:7001", "http://localhost:5173"])

def _cors_headers(origin: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"access-control-allow-origin", origin.encode()),
        (b"access-control-allow-credentials", b"true"),
        (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
        (b"access-control-allow-headers", b"Content-Type, Authorization"),
        (b"access-control-max-age", b"3600"),
    ]

class _CORSFallbackMiddleware:
    """ASGI middleware that adds CORS headers when missing and handles OPTIONS preflight."""

    def __init__(self, app, origins=None, **kwargs):
        self.app = app
        self.origins = origins or frozenset()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = None
        for h in scope.get("headers", []):
            if h[0].lower() == b"origin":
                origin = h[1].decode("latin-1")
                break

        # Handle preflight: respond immediately with 200 + CORS headers.
        if scope.get("method") == "OPTIONS" and origin and origin in self.origins:
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": _cors_headers(origin),
            })
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                has_allow_origin = any(k.lower() == b"access-control-allow-origin" for k, _ in headers)
                if not has_allow_origin and origin and origin in self.origins:
                    headers.extend(_cors_headers(origin))
                    message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_cors)
        except Exception:
            raise

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

# M8Flow: ensure permissions are loaded from m8flow.yml so RBAC groups (tenant-admin, editor, etc.) get assignments.
# Always use the package's m8flow.yml when present so login-time import_permissions_from_yaml_file creates
# permission assignments for token groups regardless of env (env may be unset, relative, or point elsewhere).
_m8flow_permissions_yml = os.path.join(
    os.path.dirname(__import__("m8flow_backend").__file__),
    "config", "permissions", "m8flow.yml",
)
if os.path.isfile(_m8flow_permissions_yml):
    _abs = os.path.abspath(_m8flow_permissions_yml)
    flask_app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = _abs
    logger.info("M8Flow: using permissions file %s", _abs)

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

# Configure SQL echo if enabled
_configure_sql_echo(flask_app)

m8flow_templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
if m8flow_templates_dir:
    flask_app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = m8flow_templates_dir
    logger.info(f"M8FLOW_TEMPLATES_STORAGE_DIR configured: {m8flow_templates_dir}")

# Register the tenant loading function to run after auth hooks.
# Tenant id (m8flow_tenant_id/m8flow_tenant_name) is resolved from the JWT in resolve_request_tenant (tenant_context_middleware.py).
if None not in flask_app.before_request_funcs:
    flask_app.before_request_funcs[None] = []
before_request_funcs = flask_app.before_request_funcs[None]
try:
    from spiffworkflow_backend.routes.authentication_controller import omni_auth
    auth_index = before_request_funcs.index(omni_auth)
    before_request_funcs.insert(auth_index + 1, lambda: resolve_request_tenant(db))
except Exception:
    flask_app.before_request(lambda: resolve_request_tenant(db))

if apply_login_tenant_patch is not None:
    apply_login_tenant_patch(flask_app)
try:
    from extensions.auth_config_on_demand_patch import apply_auth_config_on_demand_patch
    apply_auth_config_on_demand_patch()
except ImportError:
    pass

# Wrap ASGI app so uvicorn/connexion/starlette logs can see ContextVar tenant.
cnx_app = AsgiTenantContextMiddleware(cnx_app)

# Expose the Connexion app
app = cnx_app

logging.getLogger(__name__).warning(
    "Registered tables AFTER create_app: %s",
    sorted(db.metadata.tables.keys()),
)
