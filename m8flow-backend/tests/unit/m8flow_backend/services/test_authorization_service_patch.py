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
from m8flow_backend.services.authorization_service_patch import _group_identifier_applies_to_active_permission_scope
from m8flow_backend.services.authorization_service_patch import _normalize_keycloak_groups
from m8flow_backend.services.authorization_service_patch import _openid_group_identifiers_from_user_info
from m8flow_backend.services.authorization_service_patch import _normalize_openid_group_identifiers
from m8flow_backend.services.authorization_service_patch import _permission_scoped_groups_for_user
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


def test_openid_group_identifiers_from_user_info_prefers_active_org_groups_in_shared_realm(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "groups": ["viewer"],
        "realm_access": {"roles": ["tenant-admin", "editor@tenant-b"]},
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
                "groups": ["/editor"],
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == ["tenant-a-id:editor"]


def test_openid_group_identifiers_from_user_info_selects_current_org_from_multi_org_payload(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-b-id", "tenant-b"},
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "organization": {
            "tenant-a": {"id": "tenant-a-id", "groups": ["/viewer"]},
            "tenant-b": {"id": "tenant-b-id", "groups": ["/reviewer"]},
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-b-id")

    assert normalized == ["tenant-b-id:reviewer"]


def test_openid_group_identifiers_from_user_info_falls_back_to_legacy_groups_without_org_groups(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "groups": ["viewer"],
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == ["tenant-a-id:viewer"]


def test_group_identifier_applies_to_active_permission_scope_accepts_current_tenant_and_global_group(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    assert _group_identifier_applies_to_active_permission_scope("super-admin", tenant_id="tenant-a-id") is True
    assert _group_identifier_applies_to_active_permission_scope("tenant-a-id:editor", tenant_id="tenant-a-id") is True
    assert _group_identifier_applies_to_active_permission_scope("tenant-a:viewer", tenant_id="tenant-a-id") is True


def test_group_identifier_applies_to_active_permission_scope_rejects_other_tenants_and_bare_roles(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"} if tenant_id else set(),
    )

    assert _group_identifier_applies_to_active_permission_scope("tenant-b-id:editor", tenant_id="tenant-a-id") is False
    assert _group_identifier_applies_to_active_permission_scope("editor", tenant_id="tenant-a-id") is False
    assert _group_identifier_applies_to_active_permission_scope("tenant-a-id:editor", tenant_id=None) is False


def test_permission_scoped_groups_for_user_filters_to_active_tenant_and_global_groups(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user = SimpleNamespace(
        groups=[
            SimpleNamespace(identifier="tenant-a-id:editor"),
            SimpleNamespace(identifier="tenant-b-id:viewer"),
            SimpleNamespace(identifier="super-admin"),
            SimpleNamespace(identifier="tenant-admin"),
        ]
    )

    groups = _permission_scoped_groups_for_user(user, tenant_id="tenant-a-id")

    assert [group.identifier for group in groups] == [
        "tenant-a-id:editor",
        "super-admin",
    ]


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


def test_all_permission_assignments_for_user_includes_frontend_access_for_active_tenant(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "org-id")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"org-id", "org-alias"},
    )

    with app.app_context():
        from spiffworkflow_backend.models.group import GroupModel
        from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
        from spiffworkflow_backend.models.permission_target import PermissionTargetModel
        from spiffworkflow_backend.models.principal import PrincipalModel
        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        _ = (
            GroupModel,
            PermissionAssignmentModel,
            PermissionTargetModel,
            PrincipalModel,
            UserModel,
            UserGroupAssignmentModel,
        )

        db.create_all()

        authorization_service_patch.apply()

        user = UserService.create_user(username="user-one", service="service", service_id="service-id")
        org_group = UserService.find_or_create_group("org-id:everybody")
        other_group = UserService.find_or_create_group("other-id:everybody")

        UserService.add_user_to_group(user, org_group)
        UserService.add_user_to_group(user, other_group)

        AuthorizationService.add_permission_from_uri_or_macro(org_group.identifier, "read", "/frontend-access")
        AuthorizationService.add_permission_from_uri_or_macro(other_group.identifier, "read", "/frontend-access")

        permission_assignments = AuthorizationService.all_permission_assignments_for_user(user)

    assert [assignment.permission_target.uri for assignment in permission_assignments] == ["/frontend-access"]
    assert [assignment.permission for assignment in permission_assignments] == ["read"]
    assert [assignment.grant_type for assignment in permission_assignments] == ["permit"]


def test_user_service_all_principals_for_user_filters_cross_tenant_groups(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a-id")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.user_service import UserService

        user = SimpleNamespace(
            id=42,
            principal=SimpleNamespace(name="user-principal"),
            groups=[
                SimpleNamespace(id=1, identifier="tenant-a-id:editor", principal=SimpleNamespace(name="tenant-a-principal")),
                SimpleNamespace(id=2, identifier="tenant-b-id:viewer", principal=SimpleNamespace(name="tenant-b-principal")),
                SimpleNamespace(id=3, identifier="super-admin", principal=SimpleNamespace(name="super-admin-principal")),
                SimpleNamespace(id=4, identifier="editor", principal=SimpleNamespace(name="bare-editor-principal")),
            ],
        )

        principals = UserService.all_principals_for_user(user)

    assert [principal.name for principal in principals] == [
        "user-principal",
        "tenant-a-principal",
        "super-admin-principal",
    ]


def test_user_service_all_principals_for_user_includes_current_tenant_admin_and_everybody_principals(
    monkeypatch,
) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "org-id")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"org-id", "org-alias"},
    )

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.user_service import UserService

        user = SimpleNamespace(
            id=42,
            principal=SimpleNamespace(name="user-principal"),
            groups=[
                SimpleNamespace(
                    identifier="org-id:tenant-admin",
                    principal=SimpleNamespace(name="tenant-admin-principal"),
                ),
                SimpleNamespace(
                    identifier="org-id:everybody",
                    principal=SimpleNamespace(name="everybody-principal"),
                ),
                SimpleNamespace(
                    identifier="org-other:tenant-admin",
                    principal=SimpleNamespace(name="other-principal"),
                ),
            ],
        )

        principals = UserService.all_principals_for_user(user)

    assert [principal.name for principal in principals] == [
        "user-principal",
        "tenant-admin-principal",
        "everybody-principal",
    ]


def test_user_service_get_permission_targets_for_user_filters_cross_tenant_groups(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a-id")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.user_service import UserService

        def assignment(target: str, permission: str) -> SimpleNamespace:
            return SimpleNamespace(
                permission_target_id=target,
                permission=permission,
                grant_type="permit",
            )

        user = SimpleNamespace(
            id=42,
            principal=SimpleNamespace(permission_assignments=[assignment("user-target", "read")]),
            groups=[
                SimpleNamespace(
                    id=1,
                    identifier="tenant-a-id:editor",
                    principal=SimpleNamespace(permission_assignments=[assignment("tenant-a-target", "update")]),
                ),
                SimpleNamespace(
                    id=2,
                    identifier="tenant-b-id:viewer",
                    principal=SimpleNamespace(permission_assignments=[assignment("tenant-b-target", "read")]),
                ),
                SimpleNamespace(
                    id=3,
                    identifier="super-admin",
                    principal=SimpleNamespace(permission_assignments=[assignment("global-target", "delete")]),
                ),
            ],
        )

        permission_targets = UserService.get_permission_targets_for_user(user)

    assert permission_targets == {
        ("user-target", "read", "permit"),
        ("tenant-a-target", "update", "permit"),
        ("global-target", "delete", "permit"),
    }


def test_user_service_get_permission_targets_for_user_excludes_other_tenant_permissions(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "org-id-b")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"org-id-b", "org-b"},
    )

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.user_service import UserService

        def assignment(target: str, permission: str) -> SimpleNamespace:
            return SimpleNamespace(
                permission_target_id=target,
                permission=permission,
                grant_type="permit",
            )

        user = SimpleNamespace(
            id=42,
            principal=SimpleNamespace(permission_assignments=[assignment("user-target", "read")]),
            groups=[
                SimpleNamespace(
                    id=1,
                    identifier="org-id-a:tenant-admin",
                    principal=SimpleNamespace(permission_assignments=[assignment("org-a-target", "update")]),
                ),
                SimpleNamespace(
                    id=2,
                    identifier="org-id-b:tenant-admin",
                    principal=SimpleNamespace(permission_assignments=[assignment("org-b-target", "update")]),
                ),
            ],
        )

        permission_targets = UserService.get_permission_targets_for_user(user)

    assert permission_targets == {
        ("user-target", "read", "permit"),
        ("org-b-target", "update", "permit"),
    }
