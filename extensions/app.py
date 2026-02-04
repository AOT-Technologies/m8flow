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
apply_login_tenant_patch = None
try:
    from extensions.login_tenant_patch import apply_login_tenant_patch
except ImportError:
    pass

from m8flow_backend.tenancy import DEFAULT_TENANT_ID, ensure_tenant_exists
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

# Create the Connexion app.
cnx_app = create_app()

# Add CORS for local frontend; only add headers if not already set (avoids duplicate with upstream).

_LOCAL_CORS_ORIGINS = frozenset(["http://localhost:7001", "http://127.0.0.1:7001", "http://localhost:5173"])

def _cors_headers(origin: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"access-control-allow-origin", origin.encode()),
        (b"access-control-allow-credentials", b"true"),
        (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
        (b"access-control-allow-headers", b"Content-Type, Authorization, M8Flow-Tenant-Id, SpiffWorkflow-Authentication-Identifier"),
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
if flask_app is None:
    raise RuntimeError("Could not access underlying Flask app from Connexion app")

# M8Flow: allow tenant-login-url (and other public endpoints) without authentication
try:
    from extensions.auth_exclusion_patch import apply_auth_exclusion_patch
    apply_auth_exclusion_patch()
except ImportError:
    pass

# Configure SQL echo if enabled
_configure_sql_echo(flask_app)

# Testing hook for tenant selection; replace with JWT-based tenant context.
# curl -H "M8Flow-Tenant-Id: tenant-a" http://localhost:8000/v1/process-models
# curl -H "M8Flow-Tenant-Id: tenant-b" http://localhost:8000/v1/process-models
def load_tenant():
    """Load tenant ID from request headers into Flask 'g' context."""
    # Skip tenant validation for Keycloak admin APIs and public tenant check
    api_prefix = flask_app.config.get("SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX", "/v1.0")
    path = request.path

    for public_path in TENANT_PUBLIC_PATH_PREFIXES:
        if path.startswith(api_prefix + public_path):
            g.m8flow_tenant_id = None
            return  # no tenant context required for unauthenticated check

    # Also skip login/auth related paths that might not need tenant context or handle it differently
    if path.startswith(api_prefix + "/login") or path.startswith(api_prefix + "/authentication-options"):
         # Ideally these should be in TENANT_PUBLIC_PATH_PREFIXES if they are public
         # But let's log what they do.
         pass

    logger.info("Loading tenant ID from request headers")
    try:
        tenant_id = request.headers.get("M8Flow-Tenant-Id", DEFAULT_TENANT_ID)
        g.m8flow_tenant_id = tenant_id
        ensure_tenant_exists(tenant_id)
    except Exception:
        raise

# Register the tenant loading function to run before each request.
flask_app.before_request(load_tenant)
if apply_login_tenant_patch is not None:
    apply_login_tenant_patch(flask_app)
# Ensure load_tenant runs first (before omni_auth) so g.m8flow_tenant_id is set before any DB access in auth.
_funcs = flask_app.before_request_funcs.get(None) or []
flask_app.before_request_funcs[None] = [load_tenant] + [f for f in _funcs if f is not load_tenant]

# Expose for Uvicorn: CORS wrapper so local frontend (7001, 5173) works without add_middleware API issues.
app = _CORSFallbackMiddleware(cnx_app, _LOCAL_CORS_ORIGINS)
