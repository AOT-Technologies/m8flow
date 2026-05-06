"""Unit tests for m8flow_backend.services.authentication_service_patch (on-demand auth config).

These tests require m8flow_backend.services.keycloak_service and
m8flow_backend.services.auth_config_service (or mocks thereof).
"""

import time
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

# Skip entire module if optional deps not available (minimal/alternate test env)
pytest.importorskip("m8flow_backend.services.keycloak_service")
pytest.importorskip("m8flow_backend.services.auth_config_service")


@pytest.fixture
def reset_patched_flag():
    """Allow the patch to be applied in tests."""
    from m8flow_backend.services.authentication_service_patch import (
        reset_auth_config_on_demand_patch,
    )

    reset_auth_config_on_demand_patch()
    yield
    reset_auth_config_on_demand_patch()


@pytest.fixture
def reset_login_scope_patch_flag():
    """Allow the login scope patch to be applied in tests."""
    from m8flow_backend.services.authentication_service_patch import reset_login_scope_patch

    reset_login_scope_patch()
    yield
    reset_login_scope_patch()


def test_on_demand_adds_config_when_realm_exists(reset_patched_flag):
    """When identifier is missing and realm_exists returns True, ensure_tenant_auth_config runs and retry returns config."""
    from flask import Flask

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default", "label": "default"}
    ]
    tenant_config = {"identifier": "tenant-realm", "uri": "http://keycloak/realms/tenant-realm", "label": "tenant-realm"}

    def ensure_adds_config(flask_app, tenant):
        configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
        if not any(c.get("identifier") == tenant for c in configs):
            configs.append(tenant_config.copy())

    with (
        patch(
            "m8flow_backend.services.keycloak_service.realm_exists",
            return_value=True,
        ),
        patch(
            "m8flow_backend.services.auth_config_service.ensure_tenant_auth_config",
            side_effect=ensure_adds_config,
        ),
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch

        with app.app_context():
            apply_auth_config_on_demand_patch()
            result = __import__(
                "spiffworkflow_backend.services.authentication_service",
                fromlist=["AuthenticationService"],
            ).AuthenticationService.authentication_option_for_identifier("tenant-realm")
            assert result["identifier"] == "tenant-realm"
            assert result["uri"] == "http://keycloak/realms/tenant-realm"


def test_re_raises_when_realm_does_not_exist(reset_patched_flag):
    """When identifier is missing and realm_exists returns False, original exception is re-raised."""
    from flask import Flask

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default"}
    ]

    with patch(
        "m8flow_backend.services.keycloak_service.realm_exists",
        return_value=False,
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch
        from spiffworkflow_backend.services.authentication_service import (
            AuthenticationOptionNotFoundError,
            AuthenticationService,
        )

        with app.app_context():
            apply_auth_config_on_demand_patch()
            with pytest.raises(AuthenticationOptionNotFoundError) as exc_info:
                AuthenticationService.authentication_option_for_identifier("unknown-realm")
            assert "unknown-realm" in str(exc_info.value)


def test_on_demand_adds_master_config(reset_patched_flag):
    """When master is missing, ensure_master_auth_config runs and retry returns config."""
    from flask import Flask

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default", "label": "default"}
    ]
    master_config = {
        "identifier": "master",
        "uri": "http://keycloak/realms/master",
        "label": "Master",
    }

    def ensure_adds_master_config(flask_app):
        configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
        if not any(c.get("identifier") == "master" for c in configs):
            configs.append(master_config.copy())

    with patch(
        "m8flow_backend.services.auth_config_service.ensure_master_auth_config",
        side_effect=ensure_adds_master_config,
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch
        from spiffworkflow_backend.services.authentication_service import AuthenticationService

        with app.app_context():
            apply_auth_config_on_demand_patch()
            result = AuthenticationService.authentication_option_for_identifier("master")
            assert result["identifier"] == "master"
            assert result["uri"] == "http://keycloak/realms/master"


def test_on_demand_adds_config_for_configured_master_realm(reset_patched_flag, monkeypatch):
    """When the configured admin realm is missing, ensure_master_auth_config runs and retry returns config."""
    from flask import Flask

    app = Flask(__name__)
    app.config["SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS"] = [
        {"identifier": "default", "uri": "http://keycloak/realms/default", "label": "default"}
    ]
    master_config = {
        "identifier": "ops-admin",
        "uri": "http://keycloak/realms/ops-admin",
        "label": "Master",
    }
    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")

    def ensure_adds_master_config(flask_app):
        configs = flask_app.config.get("SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS") or []
        if not any(c.get("identifier") == "ops-admin" for c in configs):
            configs.append(master_config.copy())

    with patch(
        "m8flow_backend.services.auth_config_service.ensure_master_auth_config",
        side_effect=ensure_adds_master_config,
    ):
        from m8flow_backend.services.authentication_service_patch import apply_auth_config_on_demand_patch
        from spiffworkflow_backend.services.authentication_service import AuthenticationService

        with app.app_context():
            apply_auth_config_on_demand_patch()
            result = AuthenticationService.authentication_option_for_identifier("ops-admin")
            assert result["identifier"] == "ops-admin"
            assert result["uri"] == "http://keycloak/realms/ops-admin"


def test_login_scope_patch_adds_selected_organization_scope_for_shared_realm(
    reset_login_scope_patch_flag,
    monkeypatch,
) -> None:
    from flask import Flask

    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    from m8flow_backend.services.authentication_service_patch import apply_login_scope_patch

    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        assert authentication_identifier == "shared-users"
        return "https://keycloak/auth?scope=openid profile email&client_id=app"

    monkeypatch.setattr(AuthenticationService, "get_login_redirect_url", fake_get_login_redirect_url)
    monkeypatch.setattr(
        "m8flow_backend.services.authentication_service_patch.organization_scope_for_tenant",
        lambda tenant_identifier: f"organization:{tenant_identifier}",
    )

    with app.test_request_context("/v1.0/login?tenant=tenant-a"):
        apply_login_scope_patch()
        login_url = AuthenticationService().get_login_redirect_url("shared-users", final_url="/tasks")

    scopes = parse_qs(urlsplit(login_url).query)["scope"][0].split(" ")
    assert scopes == ["openid", "profile", "email", "organization:tenant-a"]


def test_login_scope_patch_uses_bare_organization_scope_without_selected_tenant(
    reset_login_scope_patch_flag,
    monkeypatch,
) -> None:
    from flask import Flask

    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    from m8flow_backend.services.authentication_service_patch import apply_login_scope_patch

    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        assert authentication_identifier == "shared-users"
        return "https://keycloak/auth?scope=openid profile email&client_id=app"

    monkeypatch.setattr(AuthenticationService, "get_login_redirect_url", fake_get_login_redirect_url)
    monkeypatch.setattr(
        "m8flow_backend.services.authentication_service_patch.organization_scope_for_tenant",
        lambda tenant_identifier: "organization:*"
        if tenant_identifier is None
        else f"organization:{tenant_identifier}",
    )

    with app.test_request_context("/v1.0/login"):
        apply_login_scope_patch()
        login_url = AuthenticationService().get_login_redirect_url("shared-users", final_url="/tasks")

    scopes = parse_qs(urlsplit(login_url).query)["scope"][0].split(" ")
    assert scopes == ["openid", "profile", "email", "organization:*"]


def test_login_scope_patch_prefers_explicit_requested_tenant_over_existing_selected_tenant(
    reset_login_scope_patch_flag,
    monkeypatch,
) -> None:
    from flask import Flask

    from spiffworkflow_backend.services.authentication_service import AuthenticationService

    from m8flow_backend.services.authentication_service_patch import apply_login_scope_patch

    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")

    def fake_get_login_redirect_url(self, authentication_identifier, final_url=None):
        assert authentication_identifier == "shared-users"
        return "https://keycloak/auth?scope=openid profile email&client_id=app"

    monkeypatch.setattr(AuthenticationService, "get_login_redirect_url", fake_get_login_redirect_url)
    monkeypatch.setattr(
        "m8flow_backend.services.authentication_service_patch.organization_scope_for_tenant",
        lambda tenant_identifier: f"organization:{tenant_identifier}",
    )

    with app.test_request_context(
        "/v1.0/login?tenant=tenant-b",
        environ_overrides={"HTTP_COOKIE": "m8flow_selected_tenant=tenant-a-id"},
    ):
        apply_login_scope_patch()
        login_url = AuthenticationService().get_login_redirect_url("shared-users", final_url="/tasks")

    scopes = parse_qs(urlsplit(login_url).query)["scope"][0].split(" ")
    assert scopes == ["openid", "profile", "email", "organization:tenant-b"]


def test_authentication_identifier_from_request_uses_realm_hint_cookie_when_auth_cookie_is_missing() -> None:
    from flask import Flask

    from spiffworkflow_backend.routes import authentication_controller

    from m8flow_backend.services.authentication_service_patch import _authentication_identifier_from_request

    app = Flask(__name__)
    original = authentication_controller._get_authentication_identifier_from_request
    authentication_controller._get_authentication_identifier_from_request = lambda: "default"
    try:
        with app.test_request_context(path="/v1.0/login", headers={"Cookie": "m8flow_auth_realm=master"}):
            assert _authentication_identifier_from_request() == "master"
    finally:
        authentication_controller._get_authentication_identifier_from_request = original


def test_patched_omni_auth_resolves_tenant_before_permission_check(monkeypatch) -> None:
    from flask import Flask, g

    from spiffworkflow_backend.routes import authentication_controller
    from spiffworkflow_backend.services.authorization_service import AuthorizationService

    import m8flow_backend.routes.authentication_controller_patch as patch_module

    monkeypatch.setattr(patch_module, "_PATCHED", False)

    seen: list[tuple[str, object | None]] = []

    def fake_verify_token(*_args, **_kwargs):
        g.user = SimpleNamespace(id=99, username="admin")
        g.token = "token"
        return {"m8flow_tenant_id": "org-id"}

    def fake_resolve_request_tenant():
        g.m8flow_tenant_id = "org-id"
        seen.append(("resolve", getattr(g, "m8flow_tenant_id", None)))

    def fake_original_omni_auth(*_args, **_kwargs):
        decoded_token = authentication_controller.verify_token()
        AuthorizationService.check_for_permission(decoded_token)

    def fake_check_for_permission(cls, decoded_token):
        from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none

        seen.append(("check", current_tenant_id_or_none()))
        seen.append(("decoded", decoded_token))

    monkeypatch.setattr(authentication_controller, "verify_token", fake_verify_token)
    monkeypatch.setattr(authentication_controller, "omni_auth", fake_original_omni_auth)
    monkeypatch.setattr(patch_module, "resolve_request_tenant", fake_resolve_request_tenant)
    monkeypatch.setattr(
        AuthorizationService,
        "check_for_permission",
        classmethod(fake_check_for_permission),
    )

    patch_module.apply()

    app = Flask(__name__)
    with app.test_request_context("/v1.0/permissions-check", headers={"Authorization": "Bearer token"}):
        authentication_controller.omni_auth()

    assert seen == [
        ("resolve", "org-id"),
        ("check", "org-id"),
        ("decoded", {"m8flow_tenant_id": "org-id"}),
    ]


def test_refresh_token_storage_tenant_maps_master_to_default() -> None:
    from m8flow_backend.services.authentication_service_patch import (
        _refresh_token_storage_tenant_id,
    )
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID

    assert _refresh_token_storage_tenant_id("master") == DEFAULT_TENANT_ID
    assert _refresh_token_storage_tenant_id("tenant-a") == "tenant-a"


def test_refresh_token_storage_tenant_maps_configured_master_to_default(monkeypatch) -> None:
    from m8flow_backend.services.authentication_service_patch import (
        _refresh_token_storage_tenant_id,
    )
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID

    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")
    assert _refresh_token_storage_tenant_id("ops-admin") == DEFAULT_TENANT_ID


def test_store_refresh_token_uses_default_storage_scope_for_master(monkeypatch) -> None:
    import sys

    from flask import Flask, g

    from m8flow_backend.services.authentication_service_patch import _patched_store_refresh_token
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID

    app = Flask(__name__)
    seen: dict[str, object] = {}

    class DummyColumn:
        def __init__(self, name: str):
            self.name = name

        def __eq__(self, other: object):
            return (self.name, other)

    class DummyQuery:
        def filter(self, *args):
            seen.setdefault("filters", []).extend(args)
            seen["scoped_tenant"] = getattr(g, "m8flow_tenant_id", None)
            return self

        def first(self):
            return None

    class DummyRefreshTokenModel:
        user_id = DummyColumn("user_id")
        m8f_tenant_id = DummyColumn("m8f_tenant_id")
        query = DummyQuery()

        def __init__(self, user_id: int, token: str, m8f_tenant_id: str):
            self.user_id = user_id
            self.token = token
            self.m8f_tenant_id = m8f_tenant_id

    class DummySession:
        def add(self, obj):
            seen["added"] = obj

        def commit(self):
            seen["committed"] = True

        def rollback(self):
            seen["rolled_back"] = True

    refresh_token_module = ModuleType("spiffworkflow_backend.models.refresh_token")
    refresh_token_module.RefreshTokenModel = DummyRefreshTokenModel
    db_module = ModuleType("spiffworkflow_backend.models.db")
    db_module.db = SimpleNamespace(session=DummySession())
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.refresh_token", refresh_token_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", db_module)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "master"
        _patched_store_refresh_token(user_id=7, refresh_token="refresh-token", tenant_id="master")

        added = seen["added"]
        assert getattr(added, "m8f_tenant_id") == DEFAULT_TENANT_ID
        assert seen["scoped_tenant"] == DEFAULT_TENANT_ID
        assert g.m8flow_tenant_id == "master"


def test_store_refresh_token_uses_default_storage_scope_for_configured_master(monkeypatch) -> None:
    import sys

    from flask import Flask, g

    from m8flow_backend.services.authentication_service_patch import _patched_store_refresh_token
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID

    app = Flask(__name__)
    seen: dict[str, object] = {}
    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")

    class DummyColumn:
        def __init__(self, name: str):
            self.name = name

        def __eq__(self, other: object):
            return (self.name, other)

    class DummyQuery:
        def filter(self, *args):
            seen.setdefault("filters", []).extend(args)
            seen["scoped_tenant"] = getattr(g, "m8flow_tenant_id", None)
            return self

        def first(self):
            return None

    class DummyRefreshTokenModel:
        user_id = DummyColumn("user_id")
        m8f_tenant_id = DummyColumn("m8f_tenant_id")
        query = DummyQuery()

        def __init__(self, user_id: int, token: str, m8f_tenant_id: str):
            self.user_id = user_id
            self.token = token
            self.m8f_tenant_id = m8f_tenant_id

    class DummySession:
        def add(self, obj):
            seen["added"] = obj

        def commit(self):
            seen["committed"] = True

        def rollback(self):
            seen["rolled_back"] = True

    refresh_token_module = ModuleType("spiffworkflow_backend.models.refresh_token")
    refresh_token_module.RefreshTokenModel = DummyRefreshTokenModel
    db_module = ModuleType("spiffworkflow_backend.models.db")
    db_module.db = SimpleNamespace(session=DummySession())
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.refresh_token", refresh_token_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", db_module)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "ops-admin"
        _patched_store_refresh_token(user_id=7, refresh_token="refresh-token", tenant_id="ops-admin")

        added = seen["added"]
        assert getattr(added, "m8f_tenant_id") == DEFAULT_TENANT_ID
        assert seen["scoped_tenant"] == DEFAULT_TENANT_ID
        assert g.m8flow_tenant_id == "ops-admin"


def test_get_refresh_token_uses_default_storage_scope_for_master(monkeypatch) -> None:
    import sys

    from flask import Flask, g

    from m8flow_backend.services.authentication_service_patch import _patched_get_refresh_token
    from m8flow_backend.tenancy import DEFAULT_TENANT_ID

    app = Flask(__name__)
    seen: dict[str, object] = {}

    class DummyColumn:
        def __init__(self, name: str):
            self.name = name

        def __eq__(self, other: object):
            return (self.name, other)

    class DummyQuery:
        def filter(self, *args):
            seen.setdefault("filters", []).extend(args)
            seen["scoped_tenant"] = getattr(g, "m8flow_tenant_id", None)
            return self

        def first(self):
            return SimpleNamespace(token="stored-refresh-token")

    class DummyRefreshTokenModel:
        user_id = DummyColumn("user_id")
        m8f_tenant_id = DummyColumn("m8f_tenant_id")
        query = DummyQuery()

    refresh_token_module = ModuleType("spiffworkflow_backend.models.refresh_token")
    refresh_token_module.RefreshTokenModel = DummyRefreshTokenModel
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.refresh_token", refresh_token_module)

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "master"
        token = _patched_get_refresh_token(user_id=7, tenant_id="master")

        assert token == "stored-refresh-token"
        assert seen["scoped_tenant"] == DEFAULT_TENANT_ID
        assert g.m8flow_tenant_id == "master"


def test_resolve_refresh_token_tenant_prefers_selected_tenant_for_shared_realm(monkeypatch) -> None:
    import base64

    from flask import Flask

    from m8flow_backend.services.authentication_service_patch import _resolve_refresh_token_tenant_id

    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    app = Flask(__name__)
    state = base64.b64encode(
        bytes(str({"authentication_identifier": "shared-users"}), "utf-8")
    ).decode("utf-8")

    with app.test_request_context(
        f"/v1.0/login_return?state={state}",
        environ_overrides={"HTTP_COOKIE": "m8flow_selected_tenant=tenant-a-id"},
    ):
        assert _resolve_refresh_token_tenant_id() == "tenant-a-id"


# ---------------------------------------------------------------------------
# JWKS cache TTL patch tests
# ---------------------------------------------------------------------------

JWKS_URI = "https://keycloak/realms/test/protocol/openid-connect/certs"
STALE_JWKS = {"keys": [{"kid": "stale-key"}]}
FRESH_JWKS = {"keys": [{"kid": "fresh-key"}]}


@pytest.fixture
def jwks_patch(monkeypatch):
    """Apply the JWKS cache TTL patch with a controllable original, then restore."""
    from spiffworkflow_backend.services.authentication_service import AuthenticationService
    import m8flow_backend.services.authentication_service_patch as svc_patch_mod

    saved_original = AuthenticationService.get_jwks_config_from_uri
    saved_cache = AuthenticationService.JSON_WEB_KEYSET_CACHE.copy()
    saved_timestamps = svc_patch_mod._JWKS_CACHE_TIMESTAMPS.copy()

    call_results: dict = {"raise": False, "value": FRESH_JWKS}

    @classmethod
    def fake_original(cls, jwks_uri, force_refresh=False):
        if call_results["raise"]:
            raise ConnectionError("JWKS fetch failed")
        cls.JSON_WEB_KEYSET_CACHE[jwks_uri] = call_results["value"]
        return call_results["value"]

    AuthenticationService.get_jwks_config_from_uri = fake_original
    monkeypatch.setattr(svc_patch_mod, "_JWKS_TTL_PATCHED", False)
    svc_patch_mod.apply_jwks_cache_ttl_patch()

    yield AuthenticationService, svc_patch_mod, call_results

    AuthenticationService.get_jwks_config_from_uri = saved_original
    AuthenticationService.JSON_WEB_KEYSET_CACHE.clear()
    AuthenticationService.JSON_WEB_KEYSET_CACHE.update(saved_cache)
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS.clear()
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS.update(saved_timestamps)
    monkeypatch.setattr(svc_patch_mod, "_JWKS_TTL_PATCHED", False)


def test_jwks_expired_cache_refresh_failure_returns_stale_cached(jwks_patch) -> None:
    AuthenticationService, svc_patch_mod, call_results = jwks_patch

    AuthenticationService.JSON_WEB_KEYSET_CACHE[JWKS_URI] = STALE_JWKS
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS[JWKS_URI] = time.monotonic() - svc_patch_mod.CACHE_TTL_SECONDS - 10

    call_results["raise"] = True
    result = AuthenticationService.get_jwks_config_from_uri(JWKS_URI)
    assert result == STALE_JWKS


def test_jwks_expired_cache_refresh_failure_no_cached_entry_raises(jwks_patch) -> None:
    AuthenticationService, svc_patch_mod, call_results = jwks_patch

    AuthenticationService.JSON_WEB_KEYSET_CACHE.pop(JWKS_URI, None)
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS.pop(JWKS_URI, None)

    call_results["raise"] = True
    with pytest.raises(ConnectionError, match="JWKS fetch failed"):
        AuthenticationService.get_jwks_config_from_uri(JWKS_URI)


def test_jwks_force_refresh_failure_raises_even_with_cached(jwks_patch) -> None:
    AuthenticationService, svc_patch_mod, call_results = jwks_patch

    AuthenticationService.JSON_WEB_KEYSET_CACHE[JWKS_URI] = STALE_JWKS
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS[JWKS_URI] = time.monotonic()

    call_results["raise"] = True
    with pytest.raises(ConnectionError, match="JWKS fetch failed"):
        AuthenticationService.get_jwks_config_from_uri(JWKS_URI, force_refresh=True)


def test_jwks_expired_cache_successful_refresh_updates_cache_and_timestamp(jwks_patch) -> None:
    AuthenticationService, svc_patch_mod, call_results = jwks_patch

    AuthenticationService.JSON_WEB_KEYSET_CACHE[JWKS_URI] = STALE_JWKS
    svc_patch_mod._JWKS_CACHE_TIMESTAMPS[JWKS_URI] = time.monotonic() - svc_patch_mod.CACHE_TTL_SECONDS - 10

    call_results["raise"] = False
    call_results["value"] = FRESH_JWKS
    before = time.monotonic()
    result = AuthenticationService.get_jwks_config_from_uri(JWKS_URI)

    assert result == FRESH_JWKS
    assert svc_patch_mod._JWKS_CACHE_TIMESTAMPS[JWKS_URI] >= before
