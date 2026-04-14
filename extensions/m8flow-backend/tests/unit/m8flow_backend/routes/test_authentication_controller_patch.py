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

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        return "https://keycloak/auth?response_type=code&client_id=app"

    with (
        app.test_request_context(path="/v1.0/login?tenant=tenant-a", method="GET"),
        patch(
            "m8flow_backend.services.keycloak_service.realm_exists",
            return_value=True,
        ),
        patch(
            "m8flow_backend.services.auth_config_service.ensure_tenant_auth_config",
        ),
        patch(
            "spiffworkflow_backend.services.authentication_service.AuthenticationService.get_login_redirect_url",
            fake_get_login_redirect_url,
        ),
    ):
        result = _handle_tenant_login_request(app)

    assert result is not None
    assert result.status_code == 302
    assert "prompt=login" not in result.headers["Location"]
