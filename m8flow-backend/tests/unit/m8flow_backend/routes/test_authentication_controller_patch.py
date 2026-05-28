import base64
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from flask import Flask, g
import pytest

from spiffworkflow_backend.routes import authentication_controller
from spiffworkflow_backend.exceptions.api_error import ApiError

import m8flow_backend.routes.authentication_controller_patch as auth_patch_module
from m8flow_backend.tenancy import TENANT_CLAIM
from m8flow_backend.routes.authentication_controller_patch import (
    _frontend_cookie_domain,
    _handle_tenant_login_request,
    _is_allowed_frontend_redirect_url,
    apply_public_group_patch,
    apply_cookie_domain_patch,
    apply_master_realm_auth_patch,
    apply_refresh_token_tenant_patch,
    apply_login_tenant_patch,
)
from m8flow_backend.canonical_db import set_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services import authorization_service_patch
from m8flow_backend.startup.flask_hooks import register_request_active_hooks
from m8flow_backend.startup.flask_hooks import register_request_tenant_context_hooks
from m8flow_backend.startup.guard import BootPhase
from m8flow_backend.startup.guard import set_phase
from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME
from spiffworkflow_backend.models.db import db


@pytest.fixture
def cookie_domain_patch(monkeypatch):
    original = authentication_controller._set_new_access_token_in_cookie
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    apply_cookie_domain_patch()
    yield
    monkeypatch.setattr(authentication_controller, "_set_new_access_token_in_cookie", original)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)


def test_frontend_cookie_domain_omits_domain_for_ip_frontend_url() -> None:
    assert _frontend_cookie_domain("http://192.168.1.105:8001") is None


def test_frontend_cookie_domain_strips_port_for_named_host() -> None:
    assert _frontend_cookie_domain("https://app.example.com:8443") == "app.example.com"


def test_set_new_access_token_in_cookie_uses_host_only_cookies_for_ip_frontend_url(
    cookie_domain_patch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://192.168.1.105:8001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
        new_id_token="id-token",
        new_authentication_identifier="master",
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = authentication_controller._set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("access_token=access-token" in header for header in headers)
    assert any("id_token=id-token" in header for header in headers)
    assert any("authentication_identifier=master" in header for header in headers)
    assert all("Domain=" not in header for header in headers)


def test_set_new_access_token_in_cookie_uses_named_host_domain_when_valid(
    cookie_domain_patch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com:8443"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = authentication_controller._set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("Domain=app.example.com" in header for header in headers)


def test_synchronize_selected_organization_claims_normalizes_group_names(monkeypatch) -> None:
    import m8flow_backend.services.keycloak_service as keycloak_service

    monkeypatch.setattr(
        keycloak_service,
        "get_organization_by_alias",
        lambda alias: {"id": "org-id", "name": "m8flow"},
    )
    monkeypatch.setattr(
        keycloak_service,
        "get_organization_member_groups",
        lambda organization_id, member_id: [
            {"path": "/Administrators"},
            {"name": "Approvers"},
            {"path": " /Support/ "},
            {"path": "/Administrators"},
        ],
    )

    synchronized_token = auth_patch_module._synchronize_selected_organization_claims(
        {
            "sub": "member-1",
            "preferred_username": "admin",
        },
        selected_tenant_alias="m8flow",
        selected_tenant_id="org-id",
    )

    assert synchronized_token["organization"] == {
        "m8flow": {
            "id": "org-id",
            "groups": ["Administrators", "Approvers", "Support"],
        }
    }


def test_set_new_access_token_in_cookie_sets_persistent_realm_hint_on_login(
    cookie_domain_patch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(
        new_access_token="access-token",
        new_id_token="id-token",
        new_authentication_identifier="master",
    )

    with app.app_context():
        response = app.make_response(("ok", 200))
        updated = authentication_controller._set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("m8flow_auth_realm=master" in h for h in headers)
    assert any("m8flow_auth_realm=master" in h and "Max-Age=2592000" in h for h in headers)


def test_set_new_access_token_in_cookie_clears_persistent_realm_hint_on_logout(
    cookie_domain_patch,
) -> None:
    """Realm hint must be cleared on explicit /logout, not on token expiry."""
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(user_has_logged_out=True)

    with app.test_request_context(path="/v1.0/logout", method="GET"):
        response = app.make_response(("ok", 200))
        updated = authentication_controller._set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert any("m8flow_auth_realm" in h and "Max-Age=0" in h for h in headers)


def test_set_new_access_token_in_cookie_preserves_realm_hint_on_token_expiry(
    cookie_domain_patch,
) -> None:
    """Token expiry sets user_has_logged_out=True but must NOT clear m8flow_auth_realm."""
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace(user_has_logged_out=True)

    # Simulate a non-logout request path (e.g. an API call whose token just expired)
    with app.test_request_context(path="/v1.0/process-instances", method="GET"):
        response = app.make_response(("ok", 200))
        updated = authentication_controller._set_new_access_token_in_cookie(response)
        headers = updated.headers.getlist("Set-Cookie")

    assert not any("m8flow_auth_realm" in h and "Max-Age=0" in h for h in headers)


def test_parse_internal_token_subject_preserves_url_issuer() -> None:
    assert auth_patch_module._parse_internal_token_subject(
        "service:http://localhost:6842/realms/m8flow::service_id:26b0e310-ea33-4cea-8bfd-a32dc6bc11d4"
    ) == (
        "http://localhost:6842/realms/m8flow",
        "26b0e310-ea33-4cea-8bfd-a32dc6bc11d4",
    )


def test_handle_tenant_login_request_redirects_to_master_when_realm_hint_present(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    monkeypatch.setattr(auth_patch_module, "_master_realm_identifier", lambda: "master")

    captured = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        captured["final_url"] = final_url
        return f"http://keycloak/realms/{authentication_identifier}/protocol/openid-connect/auth"

    with (
        app.test_request_context(
            path="/v1.0/login",
            method="GET",
            query_string={"authentication_identifier": "m8flow", "redirect_url": "http://localhost:7001/tenants"},
            headers={"Cookie": "m8flow_auth_realm=master"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = _handle_tenant_login_request(app)

    assert response is not None
    assert response.status_code in (301, 302)
    assert captured["auth_id"] == "master"
    assert captured["final_url"] == "http://localhost:7001/tenants"


def test_handle_tenant_login_request_does_not_redirect_when_realm_hint_matches_requested(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    monkeypatch.setattr(auth_patch_module, "_master_realm_identifier", lambda: "master")

    with app.test_request_context(
        path="/v1.0/login",
        method="GET",
        query_string={"authentication_identifier": "master"},
        headers={"Cookie": "m8flow_auth_realm=master"},
    ):
        response = _handle_tenant_login_request(app)

    assert response is None


def test_handle_tenant_login_request_does_not_intercept_tenant_param_when_realm_hint_present(
    monkeypatch,
) -> None:
    """Realm hint must not redirect master-hint users who have a tenant= param in the request."""
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    monkeypatch.setattr(auth_patch_module, "_master_realm_identifier", lambda: "master")
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "m8flow")

    captured: dict = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        return f"https://keycloak/realms/{authentication_identifier}/auth"

    with (
        app.test_request_context(
            path="/v1.0/login",
            method="GET",
            query_string={"tenant": "tenant-a"},
            headers={"Cookie": "m8flow_auth_realm=master"},
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = _handle_tenant_login_request(app)

    assert response is not None
    assert response.status_code == 302
    # Must redirect to the shared realm, not to master
    assert captured["auth_id"] != "master"


def test_handle_tenant_login_request_rejects_prefix_trick_redirect_url() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    path = "/v1.0/login?tenant=tenant-a&redirect_url=https://app.example.com.evil.com/tasks"
    with app.test_request_context(path=path, method="GET"):
        response, status_code = _handle_tenant_login_request(app)

    assert status_code == 400
    assert response.get_json()["detail"] == "Invalid redirect_url"


def test_is_allowed_frontend_redirect_url_allows_relative_paths() -> None:
    frontend = "https://app.example.com"
    assert _is_allowed_frontend_redirect_url("/tasks", frontend) is True
    assert _is_allowed_frontend_redirect_url("/tasks?foo=bar", frontend) is True


def test_is_allowed_frontend_redirect_url_allows_exact_origin_match() -> None:
    frontend = "https://app.example.com"
    assert _is_allowed_frontend_redirect_url("https://app.example.com/tasks", frontend) is True


def test_is_allowed_frontend_redirect_url_rejects_mismatched_origin() -> None:
    frontend = "https://app.example.com"
    assert _is_allowed_frontend_redirect_url("https://evil.example.com/tasks", frontend) is False


def test_is_allowed_frontend_redirect_url_rejects_scheme_relative_and_prefix_tricks() -> None:
    frontend = "https://app.example.com"
    assert _is_allowed_frontend_redirect_url("//evil.com/tasks", frontend) is False
    assert (
        _is_allowed_frontend_redirect_url("https://app.example.com.evil.com/tasks", frontend) is False
    )


def test_apply_login_tenant_patch_is_idempotent(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    calls = {"realm": 0, "master": 0}

    def _fake_ensure_realm_identifier_in_auth_configs(_flask_app):
        calls["realm"] += 1

    def _fake_ensure_master_auth_config(_flask_app):
        calls["master"] += 1

    monkeypatch.setattr(
        "m8flow_backend.services.auth_config_service.ensure_realm_identifier_in_auth_configs",
        _fake_ensure_realm_identifier_in_auth_configs,
    )
    monkeypatch.setattr(
        "m8flow_backend.services.auth_config_service.ensure_master_auth_config",
        _fake_ensure_master_auth_config,
    )

    apply_login_tenant_patch(app)
    apply_login_tenant_patch(app)

    funcs = app.before_request_funcs.get(None, [])
    marked_handlers = [f for f in funcs if getattr(f, "_m8flow_login_tenant_patch", False)]
    assert len(marked_handlers) == 1
    assert calls["realm"] == 1
    assert calls["master"] == 1


def test_refresh_token_tenant_patch_preserves_login_return_identity(monkeypatch) -> None:
    original_login_return = authentication_controller.login_return
    original_get_user_model_from_token = authentication_controller._get_user_model_from_token

    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    try:
        apply_refresh_token_tenant_patch()

        patched = authentication_controller.login_return
        module = inspect.getmodule(patched)
        assert module is not None
        fully_qualified_name = f"{module.__name__}.{patched.__name__}"
        assert fully_qualified_name == "spiffworkflow_backend.routes.authentication_controller.login_return"
    finally:
        authentication_controller.login_return = original_login_return
        authentication_controller._get_user_model_from_token = original_get_user_model_from_token
        monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)


def test_master_realm_auth_patch_handles_global_tenant_routes(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "tenant-a", "uri": "http://keycloak/realms/tenant-a"},
        {"identifier": "master", "uri": "http://keycloak/realms/master"},
    ]

    original = authentication_controller._get_authentication_identifier_from_request
    monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)
    authentication_controller._get_authentication_identifier_from_request = lambda: "tenant-a"
    try:
        apply_master_realm_auth_patch()

        with app.test_request_context(
            path="/v1.0/m8flow/tenants",
            method="GET",
            headers={"Authorization": "Bearer test-token"},
        ):
            assert authentication_controller._get_authentication_identifier_from_request() == "master"
    finally:
        authentication_controller._get_authentication_identifier_from_request = original
        monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)


def test_master_realm_auth_patch_uses_configured_admin_realm(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "tenant-a", "uri": "http://keycloak/realms/tenant-a"},
        {"identifier": "ops-admin", "uri": "http://keycloak/realms/ops-admin"},
    ]
    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")

    original = authentication_controller._get_authentication_identifier_from_request
    monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)
    authentication_controller._get_authentication_identifier_from_request = lambda: "tenant-a"
    try:
        apply_master_realm_auth_patch()

        with app.test_request_context(
            path="/v1.0/m8flow/tenants",
            method="GET",
            headers={"Authorization": "Bearer test-token"},
        ):
            assert authentication_controller._get_authentication_identifier_from_request() == "ops-admin"
    finally:
        authentication_controller._get_authentication_identifier_from_request = original
        monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)


def test_master_realm_auth_patch_uses_realm_hint_cookie_when_auth_cookie_is_missing(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "master", "uri": "http://keycloak/realms/master"},
        {"identifier": "shared-users", "uri": "http://keycloak/realms/shared-users"},
    ]

    original = authentication_controller._get_authentication_identifier_from_request
    monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)
    authentication_controller._get_authentication_identifier_from_request = lambda: "stale-fallback"
    try:
        apply_master_realm_auth_patch()

        with app.test_request_context(
            path="/v1.0/login",
            method="GET",
            headers={"Cookie": "m8flow_auth_realm=master"},
        ):
            assert authentication_controller._get_authentication_identifier_from_request() == "master"
    finally:
        authentication_controller._get_authentication_identifier_from_request = original
        monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)


def test_omni_auth_stores_decoded_token_before_tenant_resolution(monkeypatch) -> None:
    app = Flask(__name__)
    original_omni_auth = authentication_controller.omni_auth
    decoded_token = {
        "iss": "http://localhost:7002/realms/master",
        "preferred_username": "super-admin",
        "groups": ["super-admin"],
    }
    seen: dict[str, object] = {}

    from spiffworkflow_backend.services.authorization_service import AuthorizationService

    def fake_verify_token(*args, **kwargs):
        return decoded_token

    def fake_resolve_request_tenant():
        from flask import g

        seen["decoded_token"] = getattr(g, "_m8flow_decoded_token", None)

    def fake_check_for_permission(cls, token):
        seen["permission_token"] = token

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "verify_token", fake_verify_token)
    monkeypatch.setattr(auth_patch_module, "resolve_request_tenant", fake_resolve_request_tenant)
    monkeypatch.setattr(AuthorizationService, "check_for_permission", classmethod(fake_check_for_permission))

    try:
        auth_patch_module.apply()
        with app.test_request_context(
            path="/v1.0/m8flow/tenants",
            headers={"Authorization": "Bearer test-token"},
        ):
            authentication_controller.omni_auth()
    finally:
        authentication_controller.omni_auth = original_omni_auth
        monkeypatch.setattr(auth_patch_module, "_PATCHED", False)

    assert seen["decoded_token"] == decoded_token
    assert seen["permission_token"] == decoded_token


def test_authentication_identifier_from_bearer_token_prefers_explicit_auth_claim() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "shared-users", "uri": "http://keycloak/realms/shared-users"},
        {"identifier": "ops-admin", "uri": "http://keycloak/realms/ops-admin"},
    ]

    payload = {
        "m8flow_authentication_identifier": "ops-admin",
        "m8flow_realm_name": "shared-users",
        "iss": "http://keycloak/realms/shared-users",
    }

    with (
        app.app_context(),
        app.test_request_context(headers={"Authorization": "Bearer test-token"}),
        patch("jwt.decode", return_value=payload),
    ):
        assert auth_patch_module._authentication_identifier_from_bearer_token() == "ops-admin"


def test_authentication_identifier_from_bearer_token_falls_back_to_issuer_realm() -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "shared-users", "uri": "http://keycloak/realms/shared-users"},
    ]

    with (
        app.app_context(),
        app.test_request_context(headers={"Authorization": "Bearer test-token"}),
        patch("jwt.decode", return_value={"iss": "http://keycloak/realms/shared-users"}),
    ):
        assert auth_patch_module._authentication_identifier_from_bearer_token() == "shared-users"


def test_refresh_token_tenant_patch_auto_provisions_missing_user(monkeypatch) -> None:
    original_login_return = authentication_controller.login_return
    original_get_user_model_from_token = authentication_controller._get_user_model_from_token

    sentinel_user = object()

    def fake_original(decoded_token):
        raise ApiError(
            error_code="invalid_user",
            message="Invalid user. Please log in.",
            status_code=401,
        )

    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_user_model_from_token", fake_original)
    monkeypatch.setattr(
        "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
        lambda decoded_token: sentinel_user,
    )

    try:
        apply_refresh_token_tenant_patch()
        decoded_token = {
            "iss": "http://localhost:6842/realms/master",
            "sub": "subject-123",
            "preferred_username": "super-admin",
        }
        assert authentication_controller._get_user_model_from_token(decoded_token) is sentinel_user
    finally:
        authentication_controller.login_return = original_login_return
        authentication_controller._get_user_model_from_token = original_get_user_model_from_token
        monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)


def test_protected_requests_refresh_existing_shared_realm_user_from_token_claims(monkeypatch) -> None:
    org_tenant_id = "7338e743-e0cf-4161-83a4-3b3ff446609b"
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )

    app = Flask(__name__)
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
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "reviewer-subject",
        "preferred_username": "reviewer",
        "m8flow_authentication_identifier": "m8flow",
        "m8flow_tenant_id": org_tenant_id,
        "groups": ["/reviewer"],
        "organization": {
            "it": {"id": org_tenant_id, "groups": ["/reviewer"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: decoded_token)

    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService
    from spiffworkflow_backend.models.user import UserModel

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(lambda cls, decoded, authentication_identifier=None: decoded is decoded_token),
    )

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
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

        stale_user = UserService.create_user(
            username="reviewer",
            service="http://localhost:7002/realms/m8flow",
            service_id="reviewer-subject",
        )
        assert stale_user.groups == []

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer stale-reviewer-token"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer stale-reviewer-token"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="reviewer-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{org_tenant_id}:everybody",
            f"{org_tenant_id}:reviewer",
        }


def test_protected_requests_enrich_thin_shared_realm_token_for_editor_access(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    org_tenant_id = "7338e743-e0cf-4161-83a4-3b3ff446609b"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    thin_decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "editor-subject",
        "preferred_username": "editor",
        "m8flow_authentication_identifier": "m8flow",
        "m8flow_tenant_id": org_tenant_id,
    }
    enriched_decoded_token = {
        **thin_decoded_token,
        "organization": {
            "it": {"id": org_tenant_id, "groups": ["/editor"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: thin_decoded_token)
    monkeypatch.setattr(
        auth_patch_module,
        "_synchronize_selected_organization_claims",
        lambda decoded_token, *, selected_tenant_alias, selected_tenant_id: enriched_decoded_token,
    )

    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService
    from spiffworkflow_backend.models.user import UserModel

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(
            lambda cls, decoded, authentication_identifier=None: decoded is thin_decoded_token
            or decoded is enriched_decoded_token
        ),
    )

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
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

        stale_user = UserService.create_user(
            username="editor",
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-subject",
        )
        assert stale_user.groups == []

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer stale-editor-token"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer stale-editor-token"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{org_tenant_id}:everybody",
            f"{org_tenant_id}:editor",
        }


def test_protected_requests_enrich_thin_shared_realm_token_from_selected_tenant_cookie(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    org_tenant_id = "7338e743-e0cf-4161-83a4-3b3ff446609b"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    thin_decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "editor-cookie-subject",
        "preferred_username": "editor-cookie",
        "m8flow_authentication_identifier": "m8flow",
    }
    enriched_decoded_token = {
        **thin_decoded_token,
        "m8flow_tenant_id": org_tenant_id,
        "organization": {
            "it": {"id": org_tenant_id, "groups": ["/editor"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: thin_decoded_token)
    monkeypatch.setattr(
        auth_patch_module,
        "_synchronize_selected_organization_claims",
        lambda decoded_token, *, selected_tenant_alias, selected_tenant_id: enriched_decoded_token,
    )

    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(
            lambda cls, decoded, authentication_identifier=None: decoded is thin_decoded_token
            or decoded is enriched_decoded_token
        ),
    )

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
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

        stale_user = UserService.create_user(
            username="editor-cookie",
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-cookie-subject",
        )
        assert stale_user.groups == []

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, org_tenant_id)

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer stale-editor-cookie-token"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer stale-editor-cookie-token"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-cookie-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{org_tenant_id}:everybody",
            f"{org_tenant_id}:editor",
        }


def test_protected_requests_infer_tenant_from_local_shared_realm_user_for_thin_token(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    org_tenant_id = "7338e743-e0cf-4161-83a4-3b3ff446609b"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    thin_decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "admin-subject",
        "preferred_username": "admin",
        "m8flow_authentication_identifier": "m8flow",
    }
    enriched_decoded_token = {
        **thin_decoded_token,
        "m8flow_tenant_id": org_tenant_id,
        "m8flow_tenant_alias": "it",
        "organization": {
            "it": {"id": org_tenant_id, "groups": ["Administrators", "Manager"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: thin_decoded_token)
    monkeypatch.setattr(
        auth_patch_module,
        "_synchronize_selected_organization_claims",
        lambda decoded_token, *, selected_tenant_alias, selected_tenant_id: enriched_decoded_token,
    )

    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(
            lambda cls, decoded, authentication_identifier=None: decoded is thin_decoded_token
            or decoded is enriched_decoded_token
        ),
    )

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id=org_tenant_id,
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

        existing_user = UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="admin-subject",
        )
        tenant_admin_group = UserService.find_or_create_group(f"{org_tenant_id}:tenant-admin", source_is_open_id=True)
        everybody_group = UserService.find_or_create_group(f"{org_tenant_id}:everybody")
        manager_group = UserService.find_or_create_group(f"{org_tenant_id}:Manager", source_is_open_id=True)
        UserService.add_user_to_group(existing_user, tenant_admin_group)
        UserService.add_user_to_group(existing_user, everybody_group)
        UserService.add_user_to_group(existing_user, manager_group)

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer stale-admin-token"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer stale-admin-token"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="admin-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{org_tenant_id}:everybody",
            f"{org_tenant_id}:tenant-admin",
            f"{org_tenant_id}:Manager",
        }


def test_protected_requests_enrich_multi_org_shared_realm_token_without_active_org_groups(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    home_tenant_id = "1ca82290-ffa0-4fa5-b89f-8e0b969e2c48"
    org_tenant_id = "7f97071c-e1e8-4e0a-b44b-b389b87d1ee5"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    multi_org_decoded_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "editor-multi-org-subject",
        "preferred_username": "editor-multi-org",
        "m8flow_authentication_identifier": "m8flow",
        "m8flow_tenant_id": home_tenant_id,
        "m8flow_tenant_alias": "m8flow",
        "organization": {
            "m8flow": {"id": home_tenant_id},
            "it": {"id": org_tenant_id},
        },
    }
    enriched_decoded_token = {
        **multi_org_decoded_token,
        "m8flow_tenant_id": org_tenant_id,
        "m8flow_tenant_alias": "it",
        "organization": {
            "it": {"id": org_tenant_id, "groups": ["/editor"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: multi_org_decoded_token)
    monkeypatch.setattr(
        auth_patch_module,
        "_synchronize_selected_organization_claims",
        lambda decoded_token, *, selected_tenant_alias, selected_tenant_id: enriched_decoded_token,
    )

    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(
            lambda cls, decoded, authentication_identifier=None: decoded is multi_org_decoded_token
            or decoded is enriched_decoded_token
        ),
    )

    with app.app_context():
        db.create_all()
        db.session.add_all(
            [
                M8flowTenantModel(
                    id=home_tenant_id,
                    name="m8flow",
                    slug="m8flow",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                ),
                M8flowTenantModel(
                    id=org_tenant_id,
                    name="Information Technology",
                    slug="it",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                ),
            ]
        )
        db.session.commit()

        apply_refresh_token_tenant_patch()
        auth_patch_module.apply()
        authorization_service_patch.apply()
        app.before_request(authentication_controller.omni_auth)

        stale_user = UserService.create_user(
            username="editor-multi-org",
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-multi-org-subject",
        )
        assert stale_user.groups == []

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, org_tenant_id)

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer stale-editor-multi-org"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer stale-editor-multi-org"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="editor-multi-org-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{org_tenant_id}:everybody",
            f"{org_tenant_id}:editor",
        }


def test_selected_tenant_cookie_overrides_narrowed_shared_realm_token_for_multi_tenant_user(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    home_tenant_id = "1ca82290-ffa0-4fa5-b89f-8e0b969e2c48"
    selected_tenant_id = "7f97071c-e1e8-4e0a-b44b-b389b87d1ee5"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])

    narrowed_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "admin-multi-tenant-subject",
        "preferred_username": "admin",
        "m8flow_authentication_identifier": "m8flow",
        "m8flow_tenant_id": home_tenant_id,
        "m8flow_tenant_alias": "home",
        "organization": {
            "home": {"id": home_tenant_id},
        },
    }
    selected_tenant_token = {
        **narrowed_token,
        "m8flow_tenant_id": selected_tenant_id,
        "m8flow_tenant_alias": "it",
        "organization": {
            "it": {"id": selected_tenant_id, "groups": ["Administrators"]},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_decoded_token", lambda _token: narrowed_token)
    monkeypatch.setattr(
        auth_patch_module,
        "_synchronize_selected_organization_claims",
        lambda decoded_token, *, selected_tenant_alias, selected_tenant_id: selected_tenant_token,
    )

    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService

    monkeypatch.setattr(
        AuthenticationService,
        "validate_decoded_token",
        classmethod(
            lambda cls, decoded, authentication_identifier=None: decoded is narrowed_token
            or decoded is selected_tenant_token
        ),
    )

    with app.app_context():
        db.create_all()
        db.session.add_all(
            [
                M8flowTenantModel(
                    id=home_tenant_id,
                    name="Home",
                    slug="home",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                ),
                M8flowTenantModel(
                    id=selected_tenant_id,
                    name="Information Technology",
                    slug="it",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=2,
                    updated_at_in_seconds=2,
                ),
            ]
        )
        db.session.commit()

        apply_refresh_token_tenant_patch()
        auth_patch_module.apply()
        authorization_service_patch.apply()
        app.before_request(authentication_controller.omni_auth)

        existing_user = UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="admin-multi-tenant-subject",
        )
        selected_tenant_admin_group = UserService.find_or_create_group(
            f"{selected_tenant_id}:tenant-admin",
            source_is_open_id=True,
        )
        selected_tenant_everybody_group = UserService.find_or_create_group(
            f"{selected_tenant_id}:everybody",
        )
        UserService.add_user_to_group(existing_user, selected_tenant_admin_group)
        UserService.add_user_to_group(existing_user, selected_tenant_everybody_group)

    client = app.test_client()
    client.set_cookie("authentication_identifier", "m8flow")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, selected_tenant_id)

    onboarding_response = client.get("/v1.0/onboarding", headers={"Authorization": "Bearer narrowed-admin-token"})
    tasks_response = client.get("/v1.0/tasks", headers={"Authorization": "Bearer narrowed-admin-token"})

    assert onboarding_response.status_code == 200
    assert tasks_response.status_code == 200

    with app.app_context():
        refreshed_user = UserModel.query.filter_by(
            service="http://localhost:7002/realms/m8flow",
            service_id="admin-multi-tenant-subject",
        ).one()
        assert {group.identifier for group in refreshed_user.groups} >= {
            f"{selected_tenant_id}:everybody",
            f"{selected_tenant_id}:tenant-admin",
        }
def test_refresh_token_tenant_patch_auto_provisions_missing_user_with_separate_roles_and_groups(
    monkeypatch,
) -> None:
    original_login_return = authentication_controller.login_return
    original_get_user_model_from_token = authentication_controller._get_user_model_from_token

    sentinel_user = object()
    observed: dict[str, object] = {}

    def fake_original(decoded_token):
        raise ApiError(
            error_code="invalid_user",
            message="Invalid user. Please log in.",
            status_code=401,
        )

    def fake_create_user_from_sign_in(decoded_token):
        observed["tenant"] = getattr(g, "m8flow_tenant_id", None)
        observed["decoded_token"] = decoded_token
        return sentinel_user

    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(authentication_controller, "_get_user_model_from_token", fake_original)
    monkeypatch.setattr(
        "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
        fake_create_user_from_sign_in,
    )

    try:
        apply_refresh_token_tenant_patch()
        decoded_token = {
            TENANT_CLAIM: "tenant-a",
            "iss": "http://localhost:7002/realms/shared",
            "sub": "subject-789",
            "preferred_username": "editor-user",
            "groups": ["/Engineering"],
            "roles": ["editor"],
        }
        app = Flask(__name__)
        with app.test_request_context(path="/v1.0/login_return"):
            assert authentication_controller._get_user_model_from_token(decoded_token) is sentinel_user
    finally:
        authentication_controller.login_return = original_login_return
        authentication_controller._get_user_model_from_token = original_get_user_model_from_token
        monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)

    assert observed["tenant"] == "tenant-a"
    assert observed["decoded_token"] == decoded_token


def test_public_group_patch_uses_qualified_group_without_mutating_config(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()
    original = authentication_controller._check_if_request_is_public

    public_group = SimpleNamespace(principal=object())
    created_user = SimpleNamespace(encode_auth_token=lambda payload: "public-token")
    captured_identifiers: list[str] = []

    class _FakeQuery:
        def filter_by(self, **kwargs):
            captured_identifiers.append(kwargs["identifier"])
            return SimpleNamespace(first=lambda: public_group)

    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(
        "m8flow_backend.routes.authentication_controller_patch.qualified_config_group_identifier",
        lambda config_key: "tenant-a:spiff_public",
    )
    monkeypatch.setattr(
        "spiffworkflow_backend.services.authorization_service.AuthorizationService.get_permission_from_http_method",
        lambda method: "read",
    )
    monkeypatch.setattr(
        "spiffworkflow_backend.services.authorization_service.AuthorizationService.has_permission",
        lambda principals, permission, target_uri: True,
    )
    monkeypatch.setattr(
        "spiffworkflow_backend.services.user_service.UserService.create_public_user",
        lambda: created_user,
    )

    apply_public_group_patch()
    try:
        with app.app_context():
            import spiffworkflow_backend.models.group as group_module

            monkeypatch.setattr(group_module, "GroupModel", SimpleNamespace(query=_FakeQuery()))

            with app.test_request_context(path="/v1.0/frontend-access", method="GET"):
                authentication_controller._check_if_request_is_public()

                assert captured_identifiers == ["tenant-a:spiff_public"]
                assert app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] == "spiff_public"
    finally:
        authentication_controller._check_if_request_is_public = original
        monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)


# ---------------------------------------------------------------------------
# Helpers for authentication_expired retry tests
# ---------------------------------------------------------------------------

def _encode_state(state_dict: dict) -> str:
    return base64.b64encode(repr(state_dict).encode("utf-8")).decode("utf-8")


@pytest.fixture
def expired_auth_patch(monkeypatch):
    """Apply refresh_token_tenant_patch so patched_login_return is installed, then restore."""
    original_login_return = authentication_controller.login_return
    original_get_user_model = authentication_controller._get_user_model_from_token
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    apply_refresh_token_tenant_patch()
    yield
    authentication_controller.login_return = original_login_return
    authentication_controller._get_user_model_from_token = original_get_user_model
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)


# ---------------------------------------------------------------------------
# authentication_expired retry flow
# ---------------------------------------------------------------------------


def test_authentication_expired_retry_with_valid_final_url(expired_auth_patch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    state = _encode_state({"authentication_identifier": "tenant-a", "final_url": "/tasks"})
    captured = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login_return"),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = authentication_controller.login_return(
            state=state, error="login_required", error_description="authentication_expired"
        )

    assert response.status_code == 302
    assert captured["auth_id"] == "tenant-a"
    assert captured["final_url"] == "/tasks"
    assert "prompt=login" in response.headers["Location"]


def test_authentication_expired_rejects_evil_absolute_url(expired_auth_patch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    state = _encode_state({
        "authentication_identifier": "tenant-a",
        "final_url": "https://evil.example.com",
    })
    captured = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login_return"),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = authentication_controller.login_return(
            state=state, error="login_required", error_description="authentication_expired"
        )

    assert response.status_code == 302
    assert captured["final_url"] == "https://app.example.com"


def test_authentication_expired_rejects_scheme_relative_url(expired_auth_patch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    state = _encode_state({
        "authentication_identifier": "tenant-a",
        "final_url": "//evil.com",
    })
    captured = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login_return"),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = authentication_controller.login_return(
            state=state, error="login_required", error_description="authentication_expired"
        )

    assert response.status_code == 302
    assert captured["final_url"] == "https://app.example.com"


def test_authentication_expired_handles_percent_encoded_state(expired_auth_patch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    raw_state = _encode_state({"authentication_identifier": "tenant-a", "final_url": "/tasks"})
    encoded_state = quote(raw_state, safe="")
    captured = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login_return"),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = authentication_controller.login_return(
            state=encoded_state, error="login_required", error_description="authentication_expired"
        )

    assert response.status_code == 302
    assert captured["auth_id"] == "tenant-a"
    assert captured["final_url"] == "/tasks"


def test_authentication_expired_retry_includes_prompt_login(expired_auth_patch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"

    state = _encode_state({"authentication_identifier": "tenant-a", "final_url": "/tasks"})

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login_return"),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        response = authentication_controller.login_return(
            state=state, error="login_required", error_description="authentication_expired"
        )

    location = response.headers["Location"]
    assert "prompt=login" in location


def test_normal_login_redirect_does_not_include_prompt_login() -> None:
    """After removing the global patch, get_login_redirect_url must not append prompt=login."""
    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    original = AuthenticationService.get_login_redirect_url
    assert not hasattr(original, "__wrapped__"), (
        "get_login_redirect_url should not be wrapped by a global prompt=login patch"
    )


def test_tenant_login_does_not_include_prompt_login(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    captured: dict[str, str | None] = {}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login?tenant=tenant-a", method="GET"),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert captured == {
        "auth_id": "shared-users",
        "final_url": "https://app.example.com",
    }
    assert "prompt=login" not in result.headers["Location"]
    cookie_headers = result.headers.getlist("Set-Cookie")
    assert any(
        f"{SELECTED_TENANT_COOKIE_NAME}=tenant-a-id" in header and "Path=/" in header
        for header in cookie_headers
    )


def test_tenant_finalization_redirects_directly_with_existing_shared_realm_session(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    captured: dict[str, object] = {}

    def fake_parse_jwt_token(authentication_identifier, token):
        captured["auth_identifier"] = authentication_identifier
        captured["token"] = token
        return {
            "iss": "http://localhost:7002/realms/shared-users",
            "sub": "user-1",
            "preferred_username": "admin",
            "organization": ["tenant-a"],
        }

    def fake_create_user_from_sign_in(decoded_token):
        captured["decoded_token"] = decoded_token

        def fake_encode_auth_token(extra_payload):
            captured["session_claims"] = extra_payload
            return "tenant-a-session-token"

        return SimpleNamespace(
            encode_auth_token=fake_encode_auth_token
        )

    with (
        app.test_request_context(
            path="/v1.0/login?tenant=tenant-a&tenant_finalization=1&authentication_identifier=shared-users",
            method="GET",
            environ_overrides={
                "HTTP_COOKIE": (
                    "authentication_identifier=shared-users; "
                    "access_token=existing-access-token"
                )
            },
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.parse_jwt_token",
            fake_parse_jwt_token,
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_by_alias",
            return_value={"id": "org-tenant-a", "alias": "tenant-a", "name": "Tenant A"},
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_member_groups",
            return_value=[{"name": "tenant-admin", "path": "/tenant-admin"}],
        ),
        patch(
            "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
            fake_create_user_from_sign_in,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert result.headers["Location"] == "https://app.example.com"
    assert captured["auth_identifier"] == "shared-users"
    assert captured["token"] == "existing-access-token"
    assert captured["decoded_token"] == {
        "iss": "http://localhost:7002/realms/shared-users",
        "sub": "user-1",
        "preferred_username": "admin",
            "organization": {
                "tenant-a": {
                    "id": "org-tenant-a",
                    "groups": ["tenant-admin"],
                }
            },
        "m8flow_tenant_id": "tenant-a-id",
        "m8flow_tenant_alias": "tenant-a",
        "m8flow_tenant_name": "Tenant A",
    }
    assert captured["session_claims"] == {
        "organization": {
            "tenant-a": {
                "id": "org-tenant-a",
                "groups": ["tenant-admin"],
            }
        },
        "m8flow_tenant_id": "tenant-a-id",
        "m8flow_tenant_alias": "tenant-a",
        "m8flow_tenant_name": "Tenant A",
        "m8flow_authentication_identifier": "shared-users",
    }
    cookie_headers = result.headers.getlist("Set-Cookie")
    assert any(
        f"{SELECTED_TENANT_COOKIE_NAME}=tenant-a-id" in header and "Path=/" in header
        for header in cookie_headers
    )
    assert any("access_token=tenant-a-session-token" in header for header in cookie_headers)


def test_tenant_finalization_redirects_directly_for_multi_org_shared_realm_session(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    captured: dict[str, object] = {}

    def fake_parse_jwt_token(authentication_identifier, token):
        captured["auth_identifier"] = authentication_identifier
        captured["token"] = token
        return {
            "iss": "http://localhost:7002/realms/shared-users",
            "sub": "user-1",
            "preferred_username": "admin",
            "organization": {
                "tenant-a": {"id": "tenant-a-id"},
                "tenant-b": {"id": "tenant-b-id"},
            },
        }

    def fake_create_user_from_sign_in(decoded_token):
        captured["decoded_token"] = decoded_token

        def fake_encode_auth_token(extra_payload):
            captured["session_claims"] = extra_payload
            return "tenant-a-session-token"

        return SimpleNamespace(
            encode_auth_token=fake_encode_auth_token
        )

    with (
        app.test_request_context(
            path="/v1.0/login?tenant=tenant-a&tenant_finalization=1&authentication_identifier=shared-users",
            method="GET",
            environ_overrides={
                "HTTP_COOKIE": (
                    "authentication_identifier=shared-users; "
                    "access_token=existing-access-token"
                )
            },
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.parse_jwt_token",
            fake_parse_jwt_token,
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_by_alias",
            return_value={"id": "org-tenant-a", "alias": "tenant-a", "name": "Tenant A"},
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_member_groups",
            return_value=[{"name": "tenant-admin", "path": "/tenant-admin"}],
        ),
        patch(
            "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
            fake_create_user_from_sign_in,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert result.headers["Location"] == "https://app.example.com"
    assert captured["auth_identifier"] == "shared-users"
    assert captured["token"] == "existing-access-token"
    assert captured["decoded_token"] == {
        "iss": "http://localhost:7002/realms/shared-users",
        "sub": "user-1",
        "preferred_username": "admin",
        "organization": {
            "tenant-a": {
                "id": "org-tenant-a",
                "groups": ["tenant-admin"],
            }
        },
        "m8flow_tenant_id": "tenant-a-id",
        "m8flow_tenant_alias": "tenant-a",
        "m8flow_tenant_name": "Tenant A",
    }
    assert captured["session_claims"] == {
        "organization": {
            "tenant-a": {
                "id": "org-tenant-a",
                "groups": ["tenant-admin"],
            }
        },
        "m8flow_tenant_id": "tenant-a-id",
        "m8flow_tenant_alias": "tenant-a",
        "m8flow_tenant_name": "Tenant A",
        "m8flow_authentication_identifier": "shared-users",
    }
    cookie_headers = result.headers.getlist("Set-Cookie")
    assert any(
        f"{SELECTED_TENANT_COOKIE_NAME}=tenant-a-id" in header and "Path=/" in header
        for header in cookie_headers
    )
    assert any("access_token=tenant-a-session-token" in header for header in cookie_headers)


def test_tenant_finalization_uses_selected_tenant_id_when_alias_lookup_fails(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    captured: dict[str, object] = {}

    def fake_parse_jwt_token(authentication_identifier, token):
        captured["auth_identifier"] = authentication_identifier
        captured["token"] = token
        return {
            "iss": "http://localhost:7002/realms/shared-users",
            "sub": "user-1",
            "preferred_username": "auslin",
            "organization": {
                "test3": {"id": "tenant-3-id"},
            },
        }

    def fake_create_user_from_sign_in(decoded_token):
        captured["decoded_token"] = decoded_token

        def fake_encode_auth_token(extra_payload):
            captured["session_claims"] = extra_payload
            return "tenant-3-session-token"

        return SimpleNamespace(encode_auth_token=fake_encode_auth_token)

    with (
        app.test_request_context(
            path="/v1.0/login?tenant=test3&tenant_finalization=1&authentication_identifier=shared-users",
            method="GET",
            environ_overrides={
                "HTTP_COOKIE": (
                    "authentication_identifier=shared-users; "
                    "access_token=existing-access-token"
                )
            },
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-3-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.parse_jwt_token",
            fake_parse_jwt_token,
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_by_alias",
            return_value=None,
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_by_id",
            return_value={"id": "tenant-3-id", "alias": "test3", "name": "Tenant 3"},
        ),
        patch(
            "m8flow_backend.services.keycloak_service.get_organization_member_groups",
            return_value=[{"name": "Administrators", "path": "/Administrators"}],
        ),
        patch(
            "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
            fake_create_user_from_sign_in,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert result.headers["Location"] == "https://app.example.com"
    assert captured["decoded_token"] == {
        "iss": "http://localhost:7002/realms/shared-users",
        "sub": "user-1",
        "preferred_username": "auslin",
        "organization": {
            "test3": {
                "id": "tenant-3-id",
                "groups": ["Administrators"],
            }
        },
        "m8flow_tenant_id": "tenant-3-id",
        "m8flow_tenant_alias": "test3",
        "m8flow_tenant_name": "Tenant 3",
    }
    assert captured["session_claims"] == {
        "organization": {
            "test3": {
                "id": "tenant-3-id",
                "groups": ["Administrators"],
            }
        },
        "m8flow_tenant_id": "tenant-3-id",
        "m8flow_tenant_alias": "test3",
        "m8flow_tenant_name": "Tenant 3",
        "m8flow_authentication_identifier": "shared-users",
    }


def test_tenant_finalization_falls_back_to_standard_login_when_session_cannot_be_parsed(monkeypatch) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        assert authentication_identifier == "shared-users"
        assert final_url == "https://app.example.com"
        return "https://keycloak/auth?response_type=code&client_id=app&scope=openid+profile+email"

    with (
        app.test_request_context(
            path="/v1.0/login?tenant=tenant-a&tenant_finalization=1&authentication_identifier=shared-users",
            method="GET",
            environ_overrides={
                "HTTP_COOKIE": (
                    "authentication_identifier=shared-users; "
                    "access_token=existing-access-token"
                )
            },
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.parse_jwt_token",
            side_effect=ValueError("bad token"),
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert result.headers["Location"] == "https://keycloak/auth?response_type=code&client_id=app&scope=openid+profile+email"


def test_tenant_finalization_falls_back_to_standard_login_when_session_lacks_organization_memberships(
    monkeypatch,
) -> None:
    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "https://app.example.com"
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    captured: dict[str, object] = {"create_user_called": False}

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        captured["auth_id"] = authentication_identifier
        captured["final_url"] = final_url
        return "https://keycloak/auth?response_type=code&client_id=app&scope=openid+profile+email"

    def fake_parse_jwt_token(authentication_identifier, token):
        captured["parsed_auth_identifier"] = authentication_identifier
        captured["parsed_token"] = token
        return {
            "iss": "http://localhost:7002/realms/shared-users",
            "sub": "user-1",
            "preferred_username": "admin",
        }

    def fake_create_user_from_sign_in(decoded_token):
        captured["create_user_called"] = True
        captured["decoded_token"] = decoded_token
        return object()

    with (
        app.test_request_context(
            path="/v1.0/login?tenant=tenant-a&tenant_finalization=1&authentication_identifier=shared-users",
            method="GET",
            environ_overrides={
                "HTTP_COOKIE": (
                    "authentication_identifier=shared-users; "
                    "access_token=existing-access-token"
                )
            },
        ),
        patch(
            "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
            return_value={"exists": True, "tenant_id": "tenant-a-id"},
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.parse_jwt_token",
            fake_parse_jwt_token,
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
        patch(
            "spiffworkflow_backend.services.authorization_service.AuthorizationService.create_user_from_sign_in",
            fake_create_user_from_sign_in,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert result.headers["Location"] == "https://keycloak/auth?response_type=code&client_id=app&scope=openid+profile+email"
    assert captured["auth_id"] == "shared-users"
    assert captured["final_url"] == "https://app.example.com"
    assert captured["parsed_auth_identifier"] == "shared-users"
    assert captured["parsed_token"] == "existing-access-token"
    assert captured["create_user_called"] is False
    cookie_headers = result.headers.getlist("Set-Cookie")
    assert any(
        f"{SELECTED_TENANT_COOKIE_NAME}=tenant-a-id" in header and "Path=/" in header
        for header in cookie_headers
    )


def test_finalized_shared_realm_token_reuses_existing_user_for_follow_up_requests(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    home_tenant_id = "1ca82290-ffa0-4fa5-b89f-8e0b969e2c48"
    selected_tenant_id = "7f97071c-e1e8-4e0a-b44b-b389b87d1ee5"

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_URL"] = "http://localhost:7000"
    app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"] = "http://localhost:7001"
    app.config["SPIFFWORKFLOW_BACKEND_USE_AUTH_FOR_METRICS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["THREAD_LOCAL_DATA"] = SimpleNamespace()

    db.init_app(app)
    set_canonical_db(db)
    set_phase(BootPhase.APP_CREATED)
    register_request_active_hooks(app)
    register_request_tenant_context_hooks(app)

    app.add_url_rule("/v1.0/onboarding", "onboarding", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/tasks", "tasks", lambda: ("ok", 200), methods=["GET"])
    app.add_url_rule("/v1.0/extensions", "extensions", lambda: ("ok", 200), methods=["GET"])

    shared_realm_token = {
        "iss": "http://localhost:7002/realms/m8flow",
        "sub": "admin-multi-tenant-subject",
        "preferred_username": "admin",
        "roles": ["default-roles-m8flow"],
        "m8flow_authentication_identifier": "m8flow",
        "organization": {
            "home": {"id": home_tenant_id},
            "it": {"id": selected_tenant_id},
        },
    }

    monkeypatch.setattr(auth_patch_module, "_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_COOKIE_DOMAIN_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_PUBLIC_GROUP_PATCHED", False)
    monkeypatch.setattr(auth_patch_module, "_INTERNAL_TOKEN_SUBJECT_PATCHED", False)
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)

    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    from spiffworkflow_backend.services.user_service import UserService

    original_parse_jwt_token = AuthenticationService.parse_jwt_token

    def fake_parse_jwt_token(cls, authentication_identifier, token):
        if token == "existing-access-token":
            return shared_realm_token
        return original_parse_jwt_token(authentication_identifier, token)

    monkeypatch.setattr(AuthenticationService, "parse_jwt_token", classmethod(fake_parse_jwt_token))

    with app.app_context():
        db.create_all()
        db.session.add_all(
            [
                M8flowTenantModel(
                    id=home_tenant_id,
                    name="Home",
                    slug="home",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=1,
                    updated_at_in_seconds=1,
                ),
                M8flowTenantModel(
                    id=selected_tenant_id,
                    name="Information Technology",
                    slug="it",
                    created_by="test",
                    modified_by="test",
                    created_at_in_seconds=2,
                    updated_at_in_seconds=2,
                ),
            ]
        )
        db.session.commit()

        apply_refresh_token_tenant_patch()
        auth_patch_module.apply()
        authorization_service_patch.apply()
        app.before_request(authentication_controller.omni_auth)

        UserService.create_user(
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="admin-multi-tenant-subject",
            email="admin@example.com",
        )

        with (
            app.test_request_context(
                path="/v1.0/login?tenant=it&tenant_finalization=1&authentication_identifier=m8flow",
                method="GET",
                environ_overrides={
                    "HTTP_COOKIE": (
                        "authentication_identifier=m8flow; "
                        "access_token=existing-access-token"
                    )
                },
            ),
            patch(
                "m8flow_backend.services.tenant_service.TenantService.check_tenant_exists",
                return_value={"exists": True, "tenant_id": selected_tenant_id},
            ),
            patch(
                "m8flow_backend.services.keycloak_service.get_organization_by_alias",
                return_value={"id": selected_tenant_id, "alias": "it", "name": "Information Technology"},
            ),
            patch(
                "m8flow_backend.services.keycloak_service.get_organization_member_groups",
                return_value=[{"name": "Administrators", "path": "/Administrators"}],
            ),
        ):
            finalization_response = _handle_tenant_login_request(app)

        issued_headers = finalization_response.headers.getlist("Set-Cookie")
        access_token_cookie = next(header for header in issued_headers if header.startswith("access_token="))
        selected_tenant_cookie = next(
            header for header in issued_headers if header.startswith(f"{SELECTED_TENANT_COOKIE_NAME}=")
        )
        authentication_identifier_cookie = next(
            header for header in issued_headers if header.startswith("authentication_identifier=")
        )

    client = app.test_client()
    issued_access_token = access_token_cookie.split(";", 1)[0].split("=", 1)[1]
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, selected_tenant_cookie.split(";", 1)[0].split("=", 1)[1])
    client.set_cookie(
        "authentication_identifier",
        authentication_identifier_cookie.split(";", 1)[0].split("=", 1)[1],
    )

    auth_headers = {"Authorization": f"Bearer {issued_access_token}"}

    assert client.get("/v1.0/tasks", headers=auth_headers).status_code == 200
    assert client.get("/v1.0/onboarding", headers=auth_headers).status_code == 200
    assert client.get("/v1.0/extensions", headers=auth_headers).status_code == 200
