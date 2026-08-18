"""HTTP-level RBAC tests for the /m8flow/mcp-tools* endpoints.

test_mcp_tools_controller.py already unit-tests the three operation functions
directly (bypassing authorization entirely). test_mcp_tools_permissions.py
already locks the parsed m8flow.yml config (tenant-admin/super-admin only).
Neither exercises the actual request-time enforcement path -- the
``omni_auth`` before_request hook calling
``AuthorizationService.check_for_permission`` -- against a real logged-in
user. This file closes that gap the same way
test_viewer_can_access_process_instance_list_endpoints_m8f_133 (in
test_authentication_controller_patch.py) does for /process-instances: a real
sqlite-backed Flask app, the real m8flow.yml permissions file, the real
omni_auth hook, and a logged-in user resolved from a (mocked) decoded token.

Per this repo's AGENTS.md ("Do not validate shared-realm auth or RBAC changes
only with admin or super-admin"), this also covers a non-admin user ("editor",
the standard non-admin fixture used across this test suite) getting a 403.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from flask import Flask
from flask import request

from spiffworkflow_backend.exceptions.error import NotAuthorizedError
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.routes import authentication_controller
from spiffworkflow_backend.services.authentication_service import AuthenticationService
from spiffworkflow_backend.services.user_service import UserService

import m8flow_backend.routes.authentication_controller_patch as auth_patch_module
from m8flow_backend.canonical_db import set_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.routes import mcp_tools_controller
from m8flow_backend.routes.authentication_controller_patch import apply_refresh_token_tenant_patch
from m8flow_backend.services import authorization_service_patch
from m8flow_backend.startup.flask_hooks import register_request_active_hooks
from m8flow_backend.startup.flask_hooks import register_request_tenant_context_hooks
from m8flow_backend.startup.guard import BootPhase
from m8flow_backend.startup.guard import set_phase

ORG_TENANT_ID = "9c6c9a2e-9a35-4d5c-9d0d-3c2e4f6a7b8c"
PERMISSIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "m8flow_backend"
    / "config"
    / "permissions"
    / "m8flow.yml"
)


def _execute_mcp_tool_view():
    """Adapter reproducing Connexion's requestBody-injection for execute_mcp_tool.

    Production wires POST /m8flow/mcp-tools/execute through Connexion (api.yml's
    operationId), which parses the JSON body against the requestBody schema and
    calls ``execute_mcp_tool(body=...)`` itself. A bare Flask app (this file's
    ``_make_app``, unlike the real Connexion app) does not do that parsing/
    injection, so this reproduces just that one piece of glue -- the same spirit
    as the ``NotAuthorizedError`` -> 403 ``errorhandler`` below, which
    reconstructs the other piece of Connexion-provided plumbing this bare app
    would otherwise lack.
    """
    return mcp_tools_controller.execute_mcp_tool(request.get_json(silent=True))


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(PERMISSIONS_PATH)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    # Real operation functions, exactly as api.yml wires them (base path
    # "/v1.0" + the "/m8flow" extension prefix -- see openapi_merge.py).
    # mcp_catalog_service is mocked per-test below, so no real MCP server
    # connection is ever attempted.
    app.add_url_rule(
        "/v1.0/m8flow/mcp-tools",
        "mcp_tools_catalog",
        mcp_tools_controller.list_mcp_tools_catalog,
        methods=["GET"],
    )
    app.add_url_rule(
        "/v1.0/m8flow/mcp-tools/ping",
        "mcp_tools_ping",
        mcp_tools_controller.check_mcp_connection,
        methods=["GET"],
    )
    app.add_url_rule(
        "/v1.0/m8flow/mcp-tools/execute",
        "mcp_tools_execute",
        _execute_mcp_tool_view,
        methods=["POST"],
    )

    # omni_auth's permission check raises NotAuthorizedError (not an
    # HTTP-shaped response) on a denied request -- production maps that to a
    # 403 via connexion's own error handler (spiffworkflow_backend.exceptions
    # .api_error.handle_exception, registered on the connexion app, not on a
    # plain Flask app). This test builds a bare Flask app instead, so it
    # registers the same status-code mapping directly to get a real 403
    # response rather than an unhandled exception.
    @app.errorhandler(NotAuthorizedError)
    def _map_not_authorized_to_403(exc: NotAuthorizedError):
        return {"error_code": "not_authorized", "message": str(exc)}, 403

    return app


def _log_in_as(monkeypatch, app: Flask, *, username: str, subject: str, role: str):
    """Wire a logged-in user with ``role`` in ``ORG_TENANT_ID`` and return a test client.

    Mirrors test_viewer_can_access_process_instance_list_endpoints_m8f_133's
    login wiring exactly (mocked decoded token + real UserService/
    AuthorizationService group sync), swapping only the role and the
    username/subject.
    """
    decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": subject,
        "preferred_username": username,
        "m8flow_authentication_identifier": "m8flow",
        "m8flow_tenant_id": ORG_TENANT_ID,
        "groups": [f"/{role}"],
        "organization": {
            "it": {"id": ORG_TENANT_ID, "groups": [f"/{role}"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: decoded_token)
    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(lambda cls, decoded, authentication_identifier=None: decoded is decoded_token),
    )

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id=ORG_TENANT_ID,
                name="Information Technology",
                slug="it",
                created_by="test",
                modified_by="test",
                created_at_in_seconds=1,
                updated_at_in_seconds=1,
            )
        )
        db.session.commit()

        apply_refresh_token_tenant_patch()
        auth_patch_module.apply()
        authorization_service_patch.apply()
        app.before_request(authentication_controller.omni_auth)

        UserService.create_user(
            username=username,
            service="http://localhost:7002/realms/m8flow",
            service_id=subject,
        )

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    return client


def test_tenant_admin_gets_200_from_catalog_and_ping(monkeypatch) -> None:
    app = _make_app()
    client = _log_in_as(monkeypatch, app, username="tenant-admin-user", subject="tenant-admin-subject", role="tenant-admin")

    catalog = {"server_url": "https://mcp.example", "protocol_version": "2024-11-05", "tool_count": 0, "tools": []}
    ping_result = {"ok": True, "latency_ms": 5, "protocol_version": "2024-11-05", "authorized": True}
    monkeypatch.setattr(mcp_tools_controller.mcp_catalog_service, "get_catalog", AsyncMock(return_value=catalog))
    monkeypatch.setattr(mcp_tools_controller.mcp_catalog_service, "ping", AsyncMock(return_value=ping_result))

    catalog_response = client.get(
        "/v1.0/m8flow/mcp-tools", headers={"Authorization": "Bearer tenant-admin-token"}
    )
    ping_response = client.get(
        "/v1.0/m8flow/mcp-tools/ping", headers={"Authorization": "Bearer tenant-admin-token"}
    )

    assert catalog_response.status_code == 200, catalog_response.get_data(as_text=True)
    assert catalog_response.get_json() == catalog
    assert ping_response.status_code == 200, ping_response.get_data(as_text=True)
    assert ping_response.get_json() == ping_result


def test_non_admin_editor_gets_403_from_catalog(monkeypatch) -> None:
    """AGENTS.md: shared-realm/RBAC changes must not be validated with admin-only users."""
    app = _make_app()
    client = _log_in_as(monkeypatch, app, username="editor", subject="editor-subject", role="editor")

    # If authorization were (incorrectly) bypassed, this mock returning a
    # normal catalog would make a 403 assertion below fail loudly rather than
    # accidentally passing for the wrong reason.
    catalog = {"server_url": "https://mcp.example", "protocol_version": "2024-11-05", "tool_count": 0, "tools": []}
    monkeypatch.setattr(mcp_tools_controller.mcp_catalog_service, "get_catalog", AsyncMock(return_value=catalog))

    response = client.get("/v1.0/m8flow/mcp-tools", headers={"Authorization": "Bearer editor-token"})

    assert response.status_code == 403, response.get_data(as_text=True)
    assert response.get_json()["error_code"] == "not_authorized"

    with app.app_context():
        refreshed_user = UserService.get_user_by_service_and_service_id(
            "http://localhost:7002/realms/m8flow",
            "editor-subject",
        )
        assert refreshed_user is not None
        assert f"{ORG_TENANT_ID}:editor" in {group.identifier for group in refreshed_user.groups}
        assert f"{ORG_TENANT_ID}:tenant-admin" not in {group.identifier for group in refreshed_user.groups}


def test_tenant_admin_gets_200_from_post_execute(monkeypatch) -> None:
    """POST /execute needs the 'create' action (see
    test_read_action_alone_cannot_authorize_the_post_execute_endpoint in
    test_mcp_tools_permissions.py) -- a real HTTP-level check that the
    execute-mcp-tools grant actually authorizes it end to end, closing the gap
    left by the GET-only coverage above."""
    app = _make_app()
    client = _log_in_as(monkeypatch, app, username="tenant-admin-user", subject="tenant-admin-subject", role="tenant-admin")

    execute_result = {"result": "done"}
    mock_execute = AsyncMock(return_value=execute_result)
    monkeypatch.setattr(mcp_tools_controller.mcp_catalog_service, "execute_tool", mock_execute)

    response = client.post(
        "/v1.0/m8flow/mcp-tools/execute",
        headers={"Authorization": "Bearer tenant-admin-token"},
        json={"tool_name": "list_reports", "arguments": {}, "confirm": False},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == execute_result
    mock_execute.assert_awaited_once_with("Bearer tenant-admin-token", "list_reports", {}, False)


def test_non_admin_editor_gets_403_from_post_execute(monkeypatch) -> None:
    """AGENTS.md: shared-realm/RBAC changes must not be validated with admin-only
    users -- and this is the POST/'create' action counterpart of
    test_non_admin_editor_gets_403_from_catalog above (GET/'read')."""
    app = _make_app()
    client = _log_in_as(monkeypatch, app, username="editor", subject="editor-subject", role="editor")

    # If authorization were (incorrectly) bypassed, this mock succeeding would
    # make the 403 assertion below fail loudly rather than accidentally passing
    # for the wrong reason.
    mock_execute = AsyncMock(return_value={"result": "done"})
    monkeypatch.setattr(mcp_tools_controller.mcp_catalog_service, "execute_tool", mock_execute)

    response = client.post(
        "/v1.0/m8flow/mcp-tools/execute",
        headers={"Authorization": "Bearer editor-token"},
        json={"tool_name": "list_reports", "arguments": {}, "confirm": False},
    )

    assert response.status_code == 403, response.get_data(as_text=True)
    assert response.get_json()["error_code"] == "not_authorized"
    mock_execute.assert_not_awaited()
