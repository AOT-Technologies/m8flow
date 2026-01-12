# extensions/app.py
from flask import g, request
from extensions.bootstrap import bootstrap
bootstrap()
from spiffworkflow_backend import create_app

# Create the Connexion app
cnx_app = create_app()

# Register on the underlying Flask app
flask_app = getattr(cnx_app, "app", None)
if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# Load tenant ID from request headers before each request
def load_tenant():
    print("Loading tenant ID from request headers")
    g.m8flow_tenant_id = request.headers.get("M8Flow-Tenant-Id")

# Register the before_request handler
flask_app.before_request(load_tenant)

# Expose the Connexion app
app = cnx_app


