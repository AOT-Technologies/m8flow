"""Unit tests for authorization_service_patch helper behavior."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from m8flow_backend.services import authorization_service_patch
from m8flow_backend.services.authorization_service_patch import _keycloak_realm_roles_as_groups
from m8flow_backend.services.authorization_service_patch import _normalize_permissions_yaml_config
from m8flow_backend.services.authorization_service_patch import _tenant_id_for_user_info
from m8flow_backend.services.authorization_service_patch import extract_realm_from_issuer
from m8flow_backend.tenancy import TENANT_CLAIM


def test_tenant_id_for_user_info_prefers_token_claim(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: "context-tenant",
    )
    user_info = {
        TENANT_CLAIM: "token-tenant",
        "iss": "http://localhost:7002/realms/issuer-tenant",
    }

    assert _tenant_id_for_user_info(user_info) == "token-tenant"


def test_tenant_id_for_user_info_falls_back_to_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: "context-tenant",
    )
    user_info = {"iss": "http://localhost:7002/realms/issuer-tenant"}

    assert _tenant_id_for_user_info(user_info) == "context-tenant"


def test_tenant_id_for_user_info_falls_back_to_issuer_realm(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: None,
    )
    user_info = {"iss": "http://localhost:7002/realms/issuer-tenant"}

    assert _tenant_id_for_user_info(user_info) == "issuer-tenant"


def test_extract_realm_from_issuer() -> None:
    assert extract_realm_from_issuer("http://localhost:7002/realms/test-realm") == "test-realm"  # NOSONAR
    assert extract_realm_from_issuer("https://auth.example.com/realms/production/") == "production"
    assert extract_realm_from_issuer("http://localhost/auth") is None  # NOSONAR


def test_keycloak_realm_roles_as_groups_filters_to_m8flow_roles() -> None:
    user_info = {
        "realm_access": {
            "roles": [
                "offline_access",
                "default-roles-master",
                "super-admin",
                "tenant-admin",
            ]
        }
    }

    assert _keycloak_realm_roles_as_groups(user_info) == ["super-admin", "tenant-admin"]


def test_keycloak_realm_roles_as_groups_returns_empty_without_roles() -> None:
    assert _keycloak_realm_roles_as_groups({"realm_access": {"roles": "super-admin"}}) == []
    assert _keycloak_realm_roles_as_groups({"realm_access": {}}) == []
    assert _keycloak_realm_roles_as_groups({}) == []


def test_normalize_permissions_yaml_config_qualifies_group_keys_and_references() -> None:
    permission_configs = {
        "groups": {
            "tenant-admin": {"users": []},
        },
        "permissions": {
            "frontend-access": {
                "groups": ["everybody", "tenant-admin"],
                "actions": ["read"],
                "uri": "/frontend-access",
            }
        },
    }

    normalized = _normalize_permissions_yaml_config(permission_configs, tenant_id="tenant-a")

    assert normalized["groups"] == {"tenant-a:tenant-admin": {"users": []}}
    assert normalized["permissions"]["frontend-access"]["groups"] == [
        "tenant-a:everybody",
        "tenant-a:tenant-admin",
    ]


def test_parse_permissions_yaml_into_group_info_qualifies_default_group_references(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a")

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.authorization_service import AuthorizationService

        group_permissions = AuthorizationService.parse_permissions_yaml_into_group_info()

    group_permissions_by_name = {group["name"]: group for group in group_permissions}
    everybody_group = group_permissions_by_name["tenant-a:everybody"]
    super_admin_group = group_permissions_by_name["tenant-a:super-admin"]

    assert [permission["uri"] for permission in everybody_group["permissions"]] == [
        "/frontend-access",
        "/onboarding",
        "/active-users/*",
    ]
    assert super_admin_group["permissions"][0]["uri"] == "/m8flow/tenants/*"
