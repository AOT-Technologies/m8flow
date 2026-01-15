# extensions/app.py
import importlib.util
import logging
import os
from pathlib import Path
import sys

from flask import g, request
from extensions.bootstrap import bootstrap

logger = logging.getLogger(__name__)

# Apply model overrides before importing spiffworkflow_backend.
bootstrap()

M8FLOW_DB_DIR = Path(__file__).resolve().parent / "m8flow-backend" / "db"
if str(M8FLOW_DB_DIR) not in sys.path:
    sys.path.insert(0, str(M8FLOW_DB_DIR))

try:
    from migrate import upgrade_if_enabled as upgrade_m8flow_db
except ModuleNotFoundError:
    migrate_path = M8FLOW_DB_DIR / "migrate.py"
    spec = importlib.util.spec_from_file_location("m8flow_migrate", migrate_path)
    if spec is None or spec.loader is None:
        raise
    migrate_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate_module)
    upgrade_m8flow_db = migrate_module.upgrade_if_enabled

upgrade_m8flow_db()

from m8flow_backend.tenancy import DEFAULT_TENANT_ID, ensure_tenant_exists
from spiffworkflow_backend import create_app
from sqlalchemy import create_engine

# Configure the database engine for spiffworkflow_backend.
create_engine(os.environ["SPIFFWORKFLOW_BACKEND_DATABASE_URI"], pool_pre_ping=True)

# Create the Connexion app.
cnx_app = create_app()

# Register on the underlying Flask app
flask_app = getattr(cnx_app, "app", None)
if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# PoC/testing hook for tenant selection; replace with JWT-based tenant context.
# curl -H "M8Flow-Tenant-Id: tenant-a" http://localhost:8000/v1/process-models
# curl -H "M8Flow-Tenant-Id: tenant-b" http://localhost:8000/v1/process-models
def load_tenant():
    logger.info("Loading tenant ID from request headers")
    tenant_id = request.headers.get("M8Flow-Tenant-Id") 
    g.m8flow_tenant_id = tenant_id
    ensure_tenant_exists(tenant_id)

# Register the before_request handler
flask_app.before_request(load_tenant)

# Expose the Connexion app
app = cnx_app
