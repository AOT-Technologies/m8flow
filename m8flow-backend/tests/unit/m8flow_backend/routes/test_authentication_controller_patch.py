import base64
import inspect
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from flask import Flask
import pytest

from spiffworkflow_backend.routes import authentication_controller
from spiffworkflow_backend.exceptions.api_error import ApiError

import m8flow_backend.routes.authentication_controller_patch as auth_patch_module
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
from m8flow_backend.tenancy import SELECTED_TENANT_COOKIE_NAME


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

    original = authentication_controller._get_authentication_identifier_from_request
    monkeypatch.setattr(auth_patch_module, "_MASTER_REALM_PATCHED", False)
    authentication_controller._get_authentication_identifier_from_request = lambda: "default"
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
            "iss": "http://localhost:7002/realms/master",
            "sub": "subject-123",
            "preferred_username": "super-admin",
        }
        assert authentication_controller._get_user_model_from_token(decoded_token) is sentinel_user
    finally:
        authentication_controller.login_return = original_login_return
        authentication_controller._get_user_model_from_token = original_get_user_model_from_token
        monkeypatch.setattr(auth_patch_module, "_REFRESH_TOKEN_TENANT_PATCHED", False)


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
                "groups": ["/tenant-admin"],
            }
        },
        "m8flow_tenant_id": "tenant-a-id",
        "m8flow_tenant_alias": "tenant-a",
        "m8flow_tenant_name": "Tenant A",
    }
    cookie_headers = result.headers.getlist("Set-Cookie")
    assert any(
        f"{SELECTED_TENANT_COOKIE_NAME}=tenant-a-id" in header and "Path=/" in header
        for header in cookie_headers
    )


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
