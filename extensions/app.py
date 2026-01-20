# extensions/app.py
import importlib.util
import logging
import os
from pathlib import Path
import sys

from flask import g, request
from extensions.bootstrap import bootstrap
from m8flow_backend.utils.openapi_merge import patch_connexion_with_extension_spec

logger = logging.getLogger(__name__)

# Apply model overrides before importing spiffworkflow_backend.
bootstrap()

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

upgrade_m8flow_db()

from m8flow_backend.tenancy import DEFAULT_TENANT_ID, ensure_tenant_exists
from spiffworkflow_backend import create_app
from spiffworkflow_backend.models.db import db
from sqlalchemy import create_engine

# Configure the database engine for spiffworkflow_backend.
create_engine(os.environ["SPIFFWORKFLOW_BACKEND_DATABASE_URI"], pool_pre_ping=True)

# Monkey-patch connexion to merge extension API spec
api_file_path = os.path.join(os.path.dirname(__file__), "m8flow-backend/src/m8flow_backend/api.yml")
patch_connexion_with_extension_spec(api_file_path)


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


# Create the Connexion app.
cnx_app = create_app()

# Register on the underlying Flask app
flask_app = getattr(cnx_app, "app", None)
if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# Configure SQL echo if enabled
_configure_sql_echo(flask_app)

# Testing hook for tenant selection; replace with JWT-based tenant context.
# curl -H "M8Flow-Tenant-Id: tenant-a" http://localhost:8000/v1/process-models
# curl -H "M8Flow-Tenant-Id: tenant-b" http://localhost:8000/v1/process-models
def load_tenant():
    """Load tenant ID from request headers into Flask 'g' context."""
    logger.info("Loading tenant ID from request headers")
    tenant_id = request.headers.get("M8Flow-Tenant-Id", DEFAULT_TENANT_ID)
    g.m8flow_tenant_id = tenant_id
    ensure_tenant_exists(tenant_id)

# Register the tenant loading function to run before each request.
# Flask’s before_request() just appends to the handler list, so it can’t guarantee ordering 
# if auth hooks were already registered. 
# By inserting into flask_app.before_request_funcs[None] at index 0, load_tenant runs first, 
# ensuring g.m8flow_tenant_id is set before any auth/authorization hooks that depend on it.
if None not in flask_app.before_request_funcs:
    flask_app.before_request_funcs[None] = []
flask_app.before_request_funcs[None].insert(0, load_tenant)

# Expose the Connexion app
app = cnx_app
