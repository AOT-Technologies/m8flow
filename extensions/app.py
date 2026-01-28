# extensions/app.py
import importlib.util
import logging
import os
from pathlib import Path
import sys

from extensions.bootstrap import bootstrap

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
# Configure M8Flow templates storage directory

m8flow_templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
if m8flow_templates_dir:
    flask_app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = m8flow_templates_dir
    logger.info(f"M8FLOW_TEMPLATES_STORAGE_DIR configured: {m8flow_templates_dir}")

# TODO: Use tenant id from JWT token instead of request headers when tenant context auth is implemented
def load_tenant():
    """Resolve tenant from auth context and store it in Flask 'g'."""
    resolve_request_tenant()

# Register the tenant loading function to run after auth hooks.
if None not in flask_app.before_request_funcs:
    flask_app.before_request_funcs[None] = []
before_request_funcs = flask_app.before_request_funcs[None]
try:
    from spiffworkflow_backend.routes.authentication_controller import omni_auth
    auth_index = before_request_funcs.index(omni_auth)
    before_request_funcs.insert(auth_index + 1, load_tenant)
except Exception:
    flask_app.before_request(load_tenant)

# Expose the Connexion app
app = cnx_app
