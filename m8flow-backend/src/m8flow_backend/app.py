from __future__ import annotations

import logging
import os
from pathlib import Path

from connexion import FlaskApp
from connexion.middleware import MiddlewarePosition
from connexion.options import SwaggerUIOptions
from connexion.resolver import Resolver
from flask import g
from starlette.middleware.cors import CORSMiddleware

from m8flow_backend.authorization import install_default_policy
from m8flow_backend.auth import install_auth_middleware
from m8flow_backend.db import attach_host_timestamp_listeners, create_all, get_session_factory
from m8flow_backend.observability.request_context import install_request_id_middleware
from m8flow_backend.secrets import install_registry_at_boot
from m8flow_backend.connectors.proxy_auth import install_connector_proxy_client_auth
from m8flow_backend.workflow.service_task_params import (
    install_service_task_literal_fallback,
)
from m8flow_backend.auth import install_tenant_runtime
from m8flow_backend.startup.error_handlers import (
    register_connexion_error_handlers,
    register_error_handlers,
)
from m8flow_backend.startup.logging_setup import harden_logging
from m8flow_backend.startup.process_error_guard import install_process_level_error_guards
from m8flow_backend.startup.telemetry_setup import install_telemetry
from m8flow_backend.integrations.auth import get_auth_provider
from m8flow_backend.startup.env_var_mapper import is_unit_testing_environment
from m8flow_backend.startup.env_var_mapper import apply_m8flow_env_mapping
from m8flow_backend.startup.routes import (
    register_process_model_file_fallback_routes,
    register_root_route,
    register_template_file_fallback_routes,
)

# The api.yml operations are mounted here; the resolver reads each operationId
# as a dotted import path. Matches the old hand-rolled resolver's base path so
# every advertised /v1.0/m8flow/* URL is unchanged.
_API_BASE_PATH = "/v1.0/m8flow"
_SPEC_PATH = Path(__file__).resolve().parent / "api.yml"

# Local UI origins always allowed for credentialed browser calls (designer :6853,
# frontend :6841, Vite defaults). Env list is additive.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:6841",
    "http://127.0.0.1:6841",
    "http://localhost:6853",
    "http://127.0.0.1:6853",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

LOGGER = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    raw = (
        os.environ.get("M8FLOW_BACKEND_CORS_ALLOW_ORIGINS")
        or os.environ.get("SPIFFWORKFLOW_BACKEND_CORS_ALLOW_ORIGINS")
        or ""
    )
    origins: list[str] = list(_DEFAULT_CORS_ORIGINS)
    for part in raw.split(","):
        part = part.strip().rstrip("/")
        if not part:
            continue
        if "://" not in part:
            part = f"http://{part}"
        if part not in origins:
            origins.append(part)
    return origins


def create_app() -> FlaskApp:
    install_process_level_error_guards()
    apply_m8flow_env_mapping()
    harden_logging()
    install_default_policy()
    install_connector_proxy_client_auth()
    install_registry_at_boot()
    install_service_task_literal_fallback()
    attach_host_timestamp_listeners()

    # Connexion 3.x is an ASGI app that routes + validates the api.yml operations
    # at the middleware layer and dispatches into the wrapped Flask app. Host
    # wiring below (request hooks, auth, Flask error handlers) attaches to that
    # underlying Flask app; plain-Flask routes (v1.py, root) fall through from
    # the Connexion router. CORS is Starlette middleware on the ASGI edge so
    # preflight OPTIONS and Connexion-layer errors still get Access-Control-*.
    # The served object is the FlaskApp (ASGI).
    connexion_app = FlaskApp(__name__)
    app = connexion_app.app
    session_secret = (os.environ.get("FLASK_SESSION_SECRET_KEY") or "").strip()
    if not session_secret:
        if not is_unit_testing_environment():
            raise RuntimeError(
                "FLASK_SESSION_SECRET_KEY must be set outside unit-testing environments."
            )
        session_secret = "dev-secret"
    app.config["SECRET_KEY"] = session_secret
    templates_dir = os.environ.get("M8FLOW_TEMPLATES_STORAGE_DIR")
    if templates_dir:
        app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = templates_dir
    app.extensions["auth_provider"] = get_auth_provider()
    install_request_id_middleware(app)
    install_telemetry(app)
    register_error_handlers(app)

    env = (os.environ.get("M8FLOW_BACKEND_ENV") or os.environ.get("SPIFFWORKFLOW_BACKEND_ENV") or "").strip()
    if env in {"unit_testing", "testing"} or os.environ.get("M8FLOW_CREATE_ALL_SCHEMA") == "1":
        create_all()

    session_factory = get_session_factory()

    @app.before_request
    def _open_session() -> None:
        g.db_session = session_factory()

    @app.after_request
    def _mark_error_response_for_rollback(response):
        # handle_api_errors catches exceptions and returns 4xx/500, so Flask
        # teardown sees exc=None and would otherwise COMMIT a half-finished
        # complete (human task marked done, next engine step never persisted).
        if response.status_code >= 400:
            g.m8flow_rollback_session = True
        return response

    @app.teardown_request
    def _close_session(exc) -> None:
        session = getattr(g, "db_session", None)
        if session is None:
            return
        try:
            if exc is None and not getattr(g, "m8flow_rollback_session", False):
                session.commit()
            else:
                session.rollback()
        except Exception:
            # A failed commit/rollback here happens after the response body has
            # already been built, so it can never reach an @app.errorhandler.
            # Log it explicitly (Grafana-visible) and fall back to rollback so a
            # half-committed session is never left open, then still close below.
            LOGGER.exception(
                "Failed to finalize request-scoped DB session (commit=%s)",
                exc is None and not getattr(g, "m8flow_rollback_session", False),
            )
            try:
                session.rollback()
            except Exception:
                LOGGER.exception("Rollback after failed session finalize also failed")
        finally:
            try:
                session.close()
            except Exception:
                LOGGER.exception("Failed to close request-scoped DB session")

    install_auth_middleware(app)
    install_tenant_runtime(app)

    if not is_unit_testing_environment():
        from m8flow_backend.services.sample_template_loader import load_sample_templates

        load_sample_templates(app)

    from m8flow_backend.routes.v1 import register_v1_routes

    register_v1_routes(app)
    register_root_route(app)
    # Plain-Flask fallbacks for file paths whose {file_name} can contain slashes;
    # Connexion routes only single-segment params, so multi-segment/traversal
    # paths fall through here to the same controllers (see the registrars).
    register_process_model_file_fallback_routes(app)
    register_template_file_fallback_routes(app)

    # Mount the api.yml operations on the Connexion router. Request validation is
    # on by Connexion default (it cannot be cleanly disabled). validate_responses
    # stays off: 67/68 ops declare response schemas that controllers do not
    # strictly satisfy, so runtime response validation would break working
    # responses for no parity benefit (the reference didn't response-validate
    # either) — deferred as a follow-up, not a platform-host gap. Swagger UI +
    # spec are served at {base_path}/ui and {base_path}/openapi.json.
    connexion_app.add_api(
        _SPEC_PATH,
        base_path=_API_BASE_PATH,
        resolver=Resolver(),
        strict_validation=False,
        validate_responses=False,
        swagger_ui_options=SwaggerUIOptions(swagger_ui=True, serve_spec=True),
    )
    # Render Connexion's ASGI-layer problem responses in the app's {error_code,
    # message} shape (the Flask handlers only see errors raised inside Flask).
    register_connexion_error_handlers(connexion_app)

    # CORS wraps ExceptionMiddleware (BEFORE_EXCEPTION) so preflight is answered
    # before routing and Connexion/Flask error responses still carry Access-Control-*.
    # Explicit origins + credentials; never wildcard-with-credentials.
    connexion_app.add_middleware(
        CORSMiddleware,
        position=MiddlewarePosition.BEFORE_EXCEPTION,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Accept", "x-m8flow-tenant-id"],
    )

    return connexion_app


def create_application() -> FlaskApp:
    return create_app()


app = create_app()
