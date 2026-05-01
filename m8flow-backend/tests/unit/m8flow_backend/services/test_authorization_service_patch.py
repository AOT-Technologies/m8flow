"""Unit tests for authorization_service_patch helper behavior."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from m8flow_backend.services import authorization_service_patch
from m8flow_backend.services.authorization_service_patch import _find_existing_user_for_sign_in
from m8flow_backend.services.authorization_service_patch import _find_existing_user_in_same_realm
from m8flow_backend.services.authorization_service_patch import _keycloak_realm_roles_as_groups
from m8flow_backend.services.authorization_service_patch import _display_name_from_user_info
from m8flow_backend.services.authorization_service_patch import _normalize_keycloak_groups
from m8flow_backend.services.authorization_service_patch import _normalize_openid_group_identifiers
from m8flow_backend.services.authorization_service_patch import _normalize_permissions_yaml_config
from m8flow_backend.services.authorization_service_patch import _should_defer_tenant_group_sync
from m8flow_backend.services.authorization_service_patch import _tenant_id_for_user_info
from m8flow_backend.services.authorization_service_patch import _username_from_user_info
from m8flow_backend.services.authorization_service_patch import extract_realm_from_issuer
from m8flow_backend.tenancy import TENANT_CLAIM


MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "migrations"
    / "versions"
    / "h1a2b3c4d5e6_add_user_username_realm_uniqueness.py"
)


def _load_user_realm_migration_module():
    spec = importlib.util.spec_from_file_location("user_realm_uniqueness_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_tenant_id_for_user_info_uses_local_canonical_tenant_from_org_claim(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: None,
    )
    user_info = {
        "organization": {
            "m8flow": {
                "id": "370465d2-9b78-4c8b-9d82-c9a4818b747f",
            }
        },
        "m8flow_authentication_identifier": "m8flow",
        "iss": "http://localhost:7002/realms/m8flow",
    }

    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.tenant_id_from_payload",
        lambda payload: "m8flow",
    )

    assert _tenant_id_for_user_info(user_info) == "m8flow"


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


def test_tenant_id_for_user_info_does_not_treat_shared_realm_as_tenant(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: None,
    )
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "iss": "http://localhost:7002/realms/shared-users",
    }

    assert _tenant_id_for_user_info(user_info) is None


def test_tenant_id_for_user_info_does_not_treat_master_realm_as_tenant(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: None,
    )
    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")
    user_info = {
        "m8flow_authentication_identifier": "ops-admin",
        "iss": "http://localhost:7002/realms/ops-admin",
    }

    assert _tenant_id_for_user_info(user_info) is None


def test_should_defer_tenant_group_sync_for_multi_org_shared_realm_login(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "organization": {
            "tenant-a": {"id": "tenant-a-id"},
            "tenant-b": {"id": "tenant-b-id"},
        },
    }

    assert _should_defer_tenant_group_sync(user_info, tenant_id=None) is True
    assert _should_defer_tenant_group_sync(user_info, tenant_id="tenant-a-id") is False


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
                "admin@tenant-a",
                "editor@tenant-b",
            ]
        }
    }

    assert _keycloak_realm_roles_as_groups(user_info) == [
        "super-admin",
        "tenant-admin",
        "admin@tenant-a",
        "editor@tenant-b",
    ]


def test_keycloak_realm_roles_as_groups_returns_empty_without_roles() -> None:
    assert _keycloak_realm_roles_as_groups({"realm_access": {"roles": "super-admin"}}) == []
    assert _keycloak_realm_roles_as_groups({"realm_access": {}}) == []
    assert _keycloak_realm_roles_as_groups({}) == []


def test_normalize_keycloak_groups_uses_leaf_for_path_values() -> None:
    user_info = {"groups": ["/super-admin", "/a/b/reviewer", "viewer", "/viewer", "/admin@tenant-a", "", None]}

    assert _normalize_keycloak_groups(user_info) == ["super-admin", "reviewer", "viewer", "admin@tenant-a"]


def test_normalize_openid_group_identifiers_maps_active_tenant_role_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    normalized = _normalize_openid_group_identifiers(
        ["admin@tenant-a", "editor@tenant-a-id", "viewer"],
        tenant_id="tenant-a-id",
    )

    assert normalized == [
        "tenant-a-id:tenant-admin",
        "tenant-a-id:editor",
        "tenant-a-id:viewer",
    ]


def test_normalize_openid_group_identifiers_ignores_other_tenant_roles(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    normalized = _normalize_openid_group_identifiers(
        ["admin@tenant-b", "reviewer@tenant-c", "editor"],
        tenant_id="tenant-a-id",
    )

    assert normalized == ["tenant-a-id:editor"]


def test_find_existing_user_in_same_realm_prefers_most_recent_match() -> None:
    users = [
        SimpleNamespace(
            id=1,
            username="editor",
            service="http://localhost:7002/realms/m8flow",
            created_at_in_seconds=100,
            updated_at_in_seconds=100,
        ),
        SimpleNamespace(
            id=6,
            username="editor",
            service="http://localhost:7002/realms/m8flow",
            created_at_in_seconds=200,
            updated_at_in_seconds=250,
        ),
        SimpleNamespace(
            id=7,
            username="editor",
            service="http://localhost:7002/realms/other",
            created_at_in_seconds=300,
            updated_at_in_seconds=300,
        ),
    ]

    match = _find_existing_user_in_same_realm("editor", "http://localhost:7002/realms/m8flow", users=users)

    assert match is users[1]


def test_find_existing_user_for_sign_in_resolves_exact_subject_only() -> None:
    users = [
        SimpleNamespace(
            id=6,
            username="editor",
            service="http://localhost:7002/realms/m8flow",
            service_id="old-subject",
            created_at_in_seconds=200,
            updated_at_in_seconds=250,
        ),
        SimpleNamespace(
            id=7,
            username="editor",
            service="http://localhost:7002/realms/other",
            service_id="other-subject",
            created_at_in_seconds=300,
            updated_at_in_seconds=300,
        ),
    ]

    match = _find_existing_user_for_sign_in(
        username="editor",
        service="http://localhost:7002/realms/m8flow",
        service_id="new-subject",
        users=users,
    )

    assert match is None


def test_username_from_user_info_prefers_preferred_username() -> None:
    user_info = {
        "preferred_username": "editor",
        "sub": "subject-123",
        "email": "editor@example.com",
    }

    assert _username_from_user_info(user_info) == "editor"


def test_username_from_user_info_falls_back_to_subject_not_email() -> None:
    user_info = {
        "sub": "subject-123",
        "email": "duplicate@example.com",
    }

    assert _username_from_user_info(user_info) == "subject-123"


def test_display_name_from_user_info_uses_best_non_identity_claim() -> None:
    user_info = {
        "nickname": "Editor",
        "name": "Editor Example",
        "email": "editor@example.com",
    }

    assert _display_name_from_user_info(user_info) == "Editor"


def test_user_realm_migration_picks_most_recent_duplicate() -> None:
    migration = _load_user_realm_migration_module()

    rows = [
        {
            "id": 1,
            "username": "editor",
            "service": "http://localhost:7002/realms/m8flow",
            "created_at_in_seconds": 100,
            "updated_at_in_seconds": 100,
        },
        {
            "id": 6,
            "username": "editor",
            "service": "http://localhost:7002/realms/m8flow",
            "created_at_in_seconds": 200,
            "updated_at_in_seconds": 250,
        },
    ]

    survivor, losers = migration._pick_survivor_and_losers(rows)

    assert survivor["id"] == 6
    assert [loser["id"] for loser in losers] == [1]


def test_user_realm_migration_picks_next_available_username_suffix() -> None:
    migration = _load_user_realm_migration_module()

    used_usernames = {"editor", "editor2", "editor4"}

    renamed_username = migration._next_available_username("editor", used_usernames, 255)

    assert renamed_username == "editor3"
    assert "editor3" in used_usernames


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
    assert super_admin_group["permissions"][0]["uri"] == "/m8flow/tenants*"


def test_add_permissions_from_group_permissions_keeps_config_unqualified(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"

    captured_group_identifiers: list[str] = []

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a")

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        monkeypatch.setattr(
            UserService,
            "find_or_create_group",
            classmethod(
                lambda cls, group_identifier, source_is_open_id=False: (
                    captured_group_identifiers.append(group_identifier) or SimpleNamespace(identifier=group_identifier)
                )
            ),
        )

        AuthorizationService.add_permissions_from_group_permissions(
            [{"name": "reviewer", "users": [], "permissions": []}],
            group_permissions_only=True,
        )

        assert app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] == "everybody"
        assert app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] == "spiff_public"
        assert "tenant-a:everybody" in captured_group_identifiers
        assert "tenant-a:reviewer" in captured_group_identifiers
