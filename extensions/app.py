# extensions/app.py
import logging

from flask import g, request
from extensions.bootstrap import bootstrap
bootstrap()
from spiffworkflow_backend import create_app
from m8flow_backend.routes.templates_controller import templates_blueprint

logger = logging.getLogger(__name__)

# Create the Connexion app
cnx_app = create_app()

# Register on the underlying Flask app
flask_app = getattr(cnx_app, "app", None)
if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# Configure M8Flow templates storage directory
import os
m8flow_templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
if m8flow_templates_dir:
    flask_app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = m8flow_templates_dir
    logger.info(f"M8FLOW_TEMPLATES_STORAGE_DIR configured: {m8flow_templates_dir}")

# TODO: Use tenant id from JWT token instead of request headers when tenant context auth is implemented
def load_tenant():
    logger.info("Loading tenant ID from request headers")
    g.m8flow_tenant_id = request.headers.get("M8Flow-Tenant-Id")

# Register the before_request handler
flask_app.before_request(load_tenant)

# Register extension blueprints
flask_app.register_blueprint(templates_blueprint)

# Expose the Connexion app
app = cnx_app
