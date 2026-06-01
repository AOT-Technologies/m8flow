"""Unit tests for authorization_service_patch helper behavior."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from m8flow_backend.services import authorization_service_patch
from m8flow_backend.services.authorization_service_patch import _keycloak_realm_roles_as_groups
from m8flow_backend.services.authorization_service_patch import _find_existing_user_for_sign_in
from m8flow_backend.services.authorization_service_patch import _find_existing_user_in_same_realm
from m8flow_backend.services.authorization_service_patch import _display_name_from_user_info
from m8flow_backend.services.authorization_service_patch import _group_identifier_applies_to_active_permission_scope
from m8flow_backend.services.authorization_service_patch import _normalize_keycloak_groups
from m8flow_backend.services.authorization_service_patch import _openid_group_identifiers_from_user_info
from m8flow_backend.services.authorization_service_patch import _normalize_openid_group_identifiers
from m8flow_backend.services.authorization_service_patch import _permission_scoped_groups_for_user
from m8flow_backend.services.authorization_service_patch import _normalize_keycloak_roles
from m8flow_backend.services.authorization_service_patch import _normalized_open_id_group_identifiers
from m8flow_backend.services.authorization_service_patch import _normalized_open_id_local_group_identifiers
from m8flow_backend.services.authorization_service_patch import _normalized_open_id_organizational_group_identifiers
from m8flow_backend.services.authorization_service_patch import _normalized_open_id_permission_role_group_identifiers
from m8flow_backend.services.authorization_service_patch import _normalize_permissions_yaml_config
from m8flow_backend.services.authorization_service_patch import _should_defer_tenant_group_sync
from m8flow_backend.services.authorization_service_patch import _tenant_id_for_user_info
from m8flow_backend.services.authorization_service_patch import _active_permission_scope_tenant_id
from m8flow_backend.services.authorization_service_patch import _permission_scope_tenant
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
        "iss": "http://localhost:6842/realms/issuer-tenant",
    }

    assert _tenant_id_for_user_info(user_info) == "token-tenant"


def test_auth_exclusion_additions_include_current_user_organization_memberships() -> None:
    assert (
        "m8flow_backend.routes.keycloak_controller.get_current_user_organization_memberships"
        in authorization_service_patch.M8FLOW_AUTH_EXCLUSION_ADDITIONS
    )


def test_permission_check_exclusion_additions_include_update_tenant_name() -> None:
    assert (
        "m8flow_backend.routes.keycloak_controller.update_tenant_name"
        in authorization_service_patch.M8FLOW_PERMISSION_CHECK_EXCLUSION_ADDITIONS
    )


def test_auth_exclusion_additions_do_not_include_update_tenant_name() -> None:
    assert (
        "m8flow_backend.routes.keycloak_controller.update_tenant_name"
        not in authorization_service_patch.M8FLOW_AUTH_EXCLUSION_ADDITIONS
    )


def test_apply_excludes_update_tenant_name_from_permission_check(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.authorization_service import AuthorizationService

        monkeypatch.setattr(
            AuthorizationService,
            "get_fully_qualified_api_function_from_request",
            classmethod(
                lambda cls: (
                    "m8flow_backend.routes.keycloak_controller.update_tenant_name",
                    None,
                )
            ),
        )

        with app.test_request_context("/v1.0/m8flow/tenants/tenant-a", method="PUT"):
            assert AuthorizationService.request_is_excluded_from_permission_check() is True


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
    user_info = {"iss": "http://localhost:6842/realms/issuer-tenant"}

    assert _tenant_id_for_user_info(user_info) == "context-tenant"


def test_tenant_id_for_user_info_falls_back_to_issuer_realm(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: None,
    )
    user_info = {"iss": "http://localhost:6842/realms/issuer-tenant"}

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


def test_tenant_id_for_user_info_prefers_non_default_request_tenant_for_shared_realm(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: "7338e743-e0cf-4161-83a4-3b3ff446609b",
    )
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "m8flow")
    user_info = {
        "m8flow_authentication_identifier": "m8flow",
        "iss": "http://localhost:7002/realms/m8flow",
        "organization": {
            "it": {"id": "7338e743-e0cf-4161-83a4-3b3ff446609b", "groups": ["/tenant-admin"]},
            "m8flow": {"id": "fb30cdf7-bae8-45ea-b81f-e10d210ba413", "groups": ["/tenant-admin"]},
        },
    }

    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.tenant_id_from_payload",
        lambda payload: None,
    )

    assert _tenant_id_for_user_info(user_info) == "7338e743-e0cf-4161-83a4-3b3ff446609b"


def test_tenant_id_for_user_info_does_not_treat_public_context_as_tenant_for_shared_realm(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_id_or_none",
        lambda: "public",
    )
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "m8flow")
    user_info = {
        "m8flow_authentication_identifier": "m8flow",
        "iss": "http://localhost:7002/realms/m8flow",
        "organization": {
            "it": {"id": "7338e743-e0cf-4161-83a4-3b3ff446609b"},
            "m8flow": {"id": "fb30cdf7-bae8-45ea-b81f-e10d210ba413"},
        },
    }

    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.tenant_id_from_payload",
        lambda payload: None,
    )

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


def test_should_defer_tenant_group_sync_for_multi_org_shared_realm_login_with_public_context(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "organization": {
            "tenant-a": {"id": "tenant-a-id"},
            "tenant-b": {"id": "tenant-b-id"},
        },
    }

    assert _should_defer_tenant_group_sync(user_info, tenant_id="public") is True


def test_extract_realm_from_issuer() -> None:
    assert extract_realm_from_issuer("http://localhost:6842/realms/test-realm") == "test-realm"  # NOSONAR
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
                "submitter",
            ]
        }
    }

    assert _keycloak_realm_roles_as_groups(user_info) == [
        "super-admin",
        "tenant-admin",
        "admin@tenant-a",
        "editor@tenant-b",
        "submitter",
    ]


def test_keycloak_realm_roles_as_groups_returns_empty_without_roles() -> None:
    assert _keycloak_realm_roles_as_groups({"realm_access": {"roles": "super-admin"}}) == []
    assert _keycloak_realm_roles_as_groups({"realm_access": {}}) == []
    assert _keycloak_realm_roles_as_groups({}) == []


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
        "groups": ["/Administrators", "/Support"],
        "realm_access": {"roles": ["tenant-admin", "editor@tenant-b"]},
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
                "groups": ["/Approvers"],
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == [
        "tenant-a-id:tenant-admin",
        "tenant-a-id:reviewer",
        "tenant-a-id:Approvers",
    ]


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


def test_openid_group_identifiers_from_user_info_derives_tenant_admin_from_org_group(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
                "groups": ["/Administrators"],
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == ["tenant-a-id:tenant-admin", "tenant-a-id:Administrators"]


def test_openid_group_identifiers_from_user_info_derives_roles_from_custom_org_group_attributes(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    monkeypatch.setattr(
        "m8flow_backend.services.keycloak_service.get_organization_group_by_name",
        lambda organization_id, group_name, admin_token=None: {
            "id": "group-manager",
            "name": "Manager",
        },
    )
    monkeypatch.setattr(
        "m8flow_backend.services.keycloak_service.get_organization_group_by_id",
        lambda organization_id, group_id, admin_token=None: {
            "id": "group-manager",
            "name": "Manager",
            "attributes": {
                "m8flow_role_mapping_configured": ["true"],
                "m8flow_role_names": ["editor"],
            },
        },
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
                "groups": ["Manager"],
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == ["tenant-a-id:editor", "tenant-a-id:Manager"]


def test_openid_group_identifiers_from_user_info_ignores_legacy_root_groups_without_org_groups(
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

    assert normalized == []


def test_openid_group_identifiers_from_user_info_keeps_shared_realm_permission_roles_without_root_groups(
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user_info = {
        "m8flow_authentication_identifier": "shared-users",
        "roles": ["tenant-admin", "viewer"],
        "groups": ["Administrators"],
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
            }
        },
    }

    normalized = _openid_group_identifiers_from_user_info(user_info, tenant_id="tenant-a-id")

    assert normalized == ["tenant-a-id:tenant-admin", "tenant-a-id:viewer"]


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


def test_normalize_keycloak_roles_prefers_top_level_roles_claim() -> None:
    user_info = {
        "roles": ["editor", "integrator", "unknown-role", "", None],
        "groups": ["/tenant-admin"],
        "realm_access": {"roles": ["reviewer", "submitter"]},
    }

    assert _normalize_keycloak_roles(user_info) == ["editor", "integrator"]


def test_normalize_keycloak_roles_falls_back_to_realm_access_without_roles_claim() -> None:
    user_info = {
        "groups": ["/tenant-admin", "/Business", "submitter"],
        "realm_access": {"roles": ["integrator", "offline_access"]},
    }

    assert _normalize_keycloak_roles(user_info) == ["integrator"]


def test_normalize_keycloak_groups_canonicalizes_organizational_group_paths() -> None:
    user_info = {"groups": ["/Engineering", "/Business/Finance", "Integrations", "/Engineering", "", None]}

    assert _normalize_keycloak_groups(user_info) == ["/Engineering", "/Business/Finance", "/Integrations"]


def test_normalized_open_id_group_identifiers_uses_separate_roles_and_groups_when_roles_claim_exists() -> None:
    user_info = {
        "groups": ["/Engineering", "/Integrations"],
        "roles": ["editor", "integrator"],
        "realm_access": {"roles": ["tenant-admin"]},
    }

    assert _normalized_open_id_group_identifiers(user_info) == [
        "/Engineering",
        "/Integrations",
        "editor",
        "integrator",
    ]


def test_normalized_open_id_group_identifiers_treats_groups_as_organizational_without_roles_claim() -> None:
    user_info = {
        "groups": ["/tenant-admin", "/group_keycloak", "reviewer"],
        "realm_access": {"roles": ["submitter"]},
    }

    assert _normalized_open_id_group_identifiers(user_info) == [
        "/tenant-admin",
        "/group_keycloak",
        "/reviewer",
        "submitter",
    ]


def test_normalized_open_id_group_identifiers_keeps_plain_group_names_as_organizational_groups() -> None:
    user_info = {
        "groups": ["tenant-admin", "/Engineering", "/reviewer", "default-roles-m8flow"],
    }

    assert _normalized_open_id_group_identifiers(user_info) == [
        "/tenant-admin",
        "/Engineering",
        "/reviewer",
        "/default-roles-m8flow",
    ]


def test_normalized_open_id_role_and_org_group_helpers_stay_separate_for_new_tokens() -> None:
    user_info = {
        "groups": ["/Engineering", "/editor"],
        "roles": ["editor"],
        "realm_access": {"roles": ["reviewer"]},
    }

    assert _normalized_open_id_organizational_group_identifiers(user_info) == ["/Engineering", "/editor"]
    assert _normalized_open_id_permission_role_group_identifiers(user_info) == ["editor"]
    assert _normalized_open_id_local_group_identifiers(
        _normalized_open_id_permission_role_group_identifiers(user_info),
        _normalized_open_id_organizational_group_identifiers(user_info),
        tenant_id="tenant-a",
    ) == ["tenant-a:/Engineering", "tenant-a:/editor", "tenant-a:editor"]


def test_normalized_open_id_organizational_groups_normalize_all_group_values() -> None:
    user_info = {
        "groups": ["editor", "/Engineering", "/editor", "default-roles-m8flow"],
    }

    assert _normalized_open_id_organizational_group_identifiers(user_info) == [
        "/editor",
        "/Engineering",
        "/default-roles-m8flow",
    ]


def test_normalized_open_id_organizational_groups_preserve_bare_org_group_names_for_shared_realm(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "m8flow")
    user_info = {
        "m8flow_authentication_identifier": "m8flow",
        "organization": {
            "m8flow": {
                "id": "tenant-a-id",
                "groups": ["/Manager", "/Designers", "Manager", "/Designers/"],
            }
        },
    }

    assert _normalized_open_id_organizational_group_identifiers(user_info) == [
        "Manager",
        "Designers",
    ]


def test_find_existing_user_in_same_realm_prefers_most_recent_match() -> None:
    users = [
        SimpleNamespace(
            id=1,
            username="editor",
            service="http://localhost:6842/realms/m8flow",
            created_at_in_seconds=100,
            updated_at_in_seconds=100,
        ),
        SimpleNamespace(
            id=6,
            username="editor",
            service="http://localhost:6842/realms/m8flow",
            created_at_in_seconds=200,
            updated_at_in_seconds=250,
        ),
        SimpleNamespace(
            id=7,
            username="editor",
            service="http://localhost:6842/realms/other",
            created_at_in_seconds=300,
            updated_at_in_seconds=300,
        ),
    ]

    match = _find_existing_user_in_same_realm("editor", "http://localhost:6842/realms/m8flow", users=users)

    assert match is users[1]


def test_find_existing_user_for_sign_in_resolves_exact_subject_only() -> None:
    users = [
        SimpleNamespace(
            id=6,
            username="editor",
            service="http://localhost:6842/realms/m8flow",
            service_id="old-subject",
            created_at_in_seconds=200,
            updated_at_in_seconds=250,
        ),
        SimpleNamespace(
            id=7,
            username="editor",
            service="http://localhost:6842/realms/other",
            service_id="other-subject",
            created_at_in_seconds=300,
            updated_at_in_seconds=300,
        ),
    ]

    match = _find_existing_user_for_sign_in(
        username="editor",
        service="http://localhost:6842/realms/m8flow",
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
def test_create_user_from_sign_in_relinks_stale_same_realm_user_subject(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []

    fake_user = SimpleNamespace(
        id=6,
        username="reviewer",
        display_name="reviewer",
        email=None,
        service="http://localhost:7002/realms/m8flow",
        service_id="old-subject",
        groups=[],
    )
    create_user_calls: list[dict[str, str | None]] = []

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        monkeypatch.setattr(authorization_service_patch, "_find_existing_user_for_sign_in", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            authorization_service_patch,
            "_find_existing_user_in_same_realm",
            lambda *args, **kwargs: fake_user,
        )
        monkeypatch.setattr(
            UserService,
            "create_user",
            lambda self, **kwargs: create_user_calls.append(kwargs) or SimpleNamespace(),
        )
        monkeypatch.setattr(db.session, "add", lambda _obj: None)
        monkeypatch.setattr(db.session, "commit", lambda: None)
        monkeypatch.setattr(db.session, "expire", lambda _obj, _attrs: None)
        monkeypatch.setattr(
            AuthorizationService,
            "import_permissions_from_yaml_file",
            classmethod(lambda cls, user_model: None),
        )
        monkeypatch.setattr(
            UserService,
            "update_human_task_assignments_for_user",
            classmethod(lambda cls, user_model, new_group_ids, old_group_ids: None),
        )

        user_info = {
            "iss": "http://localhost:7002/realms/m8flow",
            "sub": "new-subject",
            "preferred_username": "reviewer",
        }
        result = AuthorizationService.create_user_from_sign_in(user_info)

    assert result is fake_user
    assert fake_user.service_id == "new-subject"
    assert create_user_calls == []


def test_user_realm_migration_picks_most_recent_duplicate() -> None:
    migration = _load_user_realm_migration_module()

    rows = [
        {
            "id": 1,
            "username": "editor",
            "service": "http://localhost:6842/realms/m8flow",
            "created_at_in_seconds": 100,
            "updated_at_in_seconds": 100,
        },
        {
            "id": 6,
            "username": "editor",
            "service": "http://localhost:6842/realms/m8flow",
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


def test_parse_permissions_yaml_into_group_info_preserves_global_super_admin_group(monkeypatch) -> None:
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
    super_admin_group = group_permissions_by_name["super-admin"]

    assert {permission["uri"] for permission in everybody_group["permissions"]} == {
        "/frontend-access",
        "/onboarding",
        "/active-users/*",
        "/extensions",
        "/m8flow/organization-memberships",
        "/user-groups/for-current-user",
        "/users/exists/by-username",
        "/debug/version-info",
        "/upsearch-locations",
        "/connector-proxy/typeahead/*",
        "/script-assist/enabled",
    }
    super_admin_permission_uris = {p["uri"] for p in super_admin_group["permissions"]}
    assert "/frontend-access" in super_admin_permission_uris
    assert "/m8flow/tenants*" in super_admin_permission_uris
    assert "/m8flow/templates/*" in super_admin_permission_uris
    assert "/authentications/*" in super_admin_permission_uris
    assert "/secrets/*" in super_admin_permission_uris
    assert "/process-instances/for-me" in super_admin_permission_uris
    assert "/process-instances" in super_admin_permission_uris

    super_admin_actions_by_uri: dict[str, set[str]] = {}
    for permission in super_admin_group["permissions"]:
        super_admin_actions_by_uri.setdefault(permission["uri"], set()).update(permission["actions"])

    assert "create" in super_admin_actions_by_uri["/process-instances/for-me"]
    assert "create" in super_admin_actions_by_uri["/process-instances"]
    assert "update" not in super_admin_actions_by_uri["/tasks/*"]


def test_parse_permissions_yaml_submitter_includes_process_model_read_dependencies(monkeypatch) -> None:
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
    submitter_group = group_permissions_by_name["tenant-a:submitter"]
    submitter_uris = {permission["uri"] for permission in submitter_group["permissions"]}

    assert "/script-assist/*" in submitter_uris
    assert "/service-tasks/*" in submitter_uris
    assert "/service-tasks" in submitter_uris
    assert "/m8flow/templates/process-models/*" in submitter_uris


def test_parse_permissions_yaml_reviewer_is_limited_to_task_access(monkeypatch) -> None:
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
    reviewer_group = group_permissions_by_name["tenant-a:reviewer"]
    reviewer_uris = {permission["uri"] for permission in reviewer_group["permissions"]}

    assert "/tasks" in reviewer_uris
    assert "/tasks/*" in reviewer_uris
    assert "/process-groups" not in reviewer_uris
    assert "/process-models" not in reviewer_uris
    assert "PM:ALL" not in reviewer_uris
    assert "/processes" not in reviewer_uris
    assert "/processes/*" not in reviewer_uris
    assert "/process-instances" not in reviewer_uris
    assert "/process-instances/for-me" not in reviewer_uris
    assert "/process-instances/report-metadata" not in reviewer_uris


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
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

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


def test_reviewer_permissions_from_yaml_include_onboarding_and_tasks_but_not_process_instance_lists(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )

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

        user = UserService.create_user(username="reviewer", service="service", service_id="service-id")
        reviewer_group = UserService.find_or_create_group("org-id:reviewer")
        everybody_group = UserService.find_or_create_group("org-id:everybody")

        UserService.add_user_to_group(user, reviewer_group)
        UserService.add_user_to_group(user, everybody_group)
        AuthorizationService.import_permissions_from_yaml_file(user)

        onboarding_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/onboarding")
        for_me_allowed = AuthorizationService.user_has_permission(user, "create", "/v1.0/process-instances/for-me")
        tasks_collection_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/tasks")
        task_item_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/tasks/123")

    assert onboarding_allowed is True
    assert for_me_allowed is False
    assert tasks_collection_allowed is True
    assert task_item_allowed is True


def test_tenant_admin_permissions_from_yaml_only_grant_page_access_and_tenant_updates(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a", "tenant-a-slug"},
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

        user = UserService.create_user(username="tenant-admin", service="service", service_id="service-id")
        tenant_admin_group = UserService.find_or_create_group("tenant-a:tenant-admin")
        everybody_group = UserService.find_or_create_group("tenant-a:everybody")

        UserService.add_user_to_group(user, tenant_admin_group)
        UserService.add_user_to_group(user, everybody_group)
        AuthorizationService.import_permissions_from_yaml_file(user)

        tenant_management_page_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenant-management",
        )
        members_read_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants/tenant-a/members",
        )
        members_create_allowed = AuthorizationService.user_has_permission(
            user,
            "create",
            "/v1.0/m8flow/tenants/tenant-a/members",
        )
        available_users_read_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants/tenant-a/available-users",
        )
        groups_read_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants/tenant-a/groups",
        )
        groups_create_allowed = AuthorizationService.user_has_permission(
            user,
            "create",
            "/v1.0/m8flow/tenants/tenant-a/groups",
        )
        group_member_update_allowed = AuthorizationService.user_has_permission(
            user,
            "update",
            "/v1.0/m8flow/tenants/tenant-a/groups/Approvers/members/reviewer",
        )
        group_member_delete_allowed = AuthorizationService.user_has_permission(
            user,
            "delete",
            "/v1.0/m8flow/tenants/tenant-a/groups/Approvers/members/reviewer",
        )
        group_role_update_allowed = AuthorizationService.user_has_permission(
            user,
            "update",
            "/v1.0/m8flow/tenants/tenant-a/groups/Approvers/roles/reviewer",
        )
        group_role_delete_allowed = AuthorizationService.user_has_permission(
            user,
            "delete",
            "/v1.0/m8flow/tenants/tenant-a/groups/Approvers/roles/reviewer",
        )
        member_role_update_allowed = AuthorizationService.user_has_permission(
            user,
            "update",
            "/v1.0/m8flow/tenants/tenant-a/members/editor/roles/editor",
        )
        member_role_delete_allowed = AuthorizationService.user_has_permission(
            user,
            "delete",
            "/v1.0/m8flow/tenants/tenant-a/members/editor/roles/editor",
        )
        tenant_list_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants",
        )
        tenant_update_allowed = AuthorizationService.user_has_permission(
            user,
            "update",
            "/v1.0/m8flow/tenants/tenant-a",
        )
        tenant_delete_allowed = AuthorizationService.user_has_permission(
            user,
            "delete",
            "/v1.0/m8flow/tenants/tenant-a",
        )

    assert tenant_management_page_allowed is True
    assert members_read_allowed is False
    assert members_create_allowed is False
    assert available_users_read_allowed is False
    assert groups_read_allowed is False
    assert groups_create_allowed is False
    assert group_member_update_allowed is True
    assert group_member_delete_allowed is False
    assert group_role_update_allowed is True
    assert group_role_delete_allowed is False
    assert member_role_update_allowed is True
    assert member_role_delete_allowed is False
    assert tenant_list_allowed is False
    assert tenant_update_allowed is True
    assert tenant_delete_allowed is False


def test_user_service_all_principals_for_user_includes_global_super_admin_without_tenant_context(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: None)
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: set(),
    )

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.services.user_service import UserService

        user = SimpleNamespace(
            id=42,
            principal=SimpleNamespace(id=100, permission_assignments=[]),
            groups=[
                SimpleNamespace(
                    id=1,
                    identifier="super-admin",
                    principal=SimpleNamespace(id=200, permission_assignments=[]),
                ),
                SimpleNamespace(
                    id=2,
                    identifier="tenant-a:viewer",
                    principal=SimpleNamespace(id=300, permission_assignments=[]),
                ),
            ],
        )

        principals = UserService.all_principals_for_user(user)

    assert [principal.id for principal in principals] == [100, 200]


def test_global_super_admin_permission_matches_normalized_org_management_route(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: None)
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: set(),
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

        user = UserService.create_user(username="super-admin", service="service", service_id="service-id")
        super_admin_group = UserService.find_or_create_group("super-admin")
        UserService.add_user_to_group(user, super_admin_group)

        AuthorizationService.add_permission_from_uri_or_macro(super_admin_group.identifier, "all", "/m8flow/tenants*")
        AuthorizationService.add_permission_from_uri_or_macro(
            super_admin_group.identifier,
            "all",
            "/m8flow/tenant-realms*",
        )

        principals = UserService.all_principals_for_user(user)
        permission_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/m8flow/tenants")
        child_permission_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants/tenant-a/members",
        )

    assert {principal.id for principal in principals} == {user.principal.id, super_admin_group.principal.id}
    assert permission_allowed is True
    assert child_permission_allowed is True


def test_tenant_scoped_user_does_not_automatically_get_global_super_admin_permissions(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "current_tenant_id_or_none", lambda: "tenant-a")
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a", "tenant-a-slug"},
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

        user = UserService.create_user(username="tenant-user", service="service", service_id="service-id")
        tenant_group = UserService.find_or_create_group("tenant-a:tenant-admin")
        super_admin_group = UserService.find_or_create_group("super-admin")

        UserService.add_user_to_group(user, tenant_group)
        AuthorizationService.add_permission_from_uri_or_macro(super_admin_group.identifier, "all", "/m8flow/tenants*")

        permission_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/m8flow/tenants")

    assert permission_allowed is False


def test_master_realm_create_user_from_sign_in_assigns_global_super_admin_group(monkeypatch) -> None:
    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "_master_realm_identifier", lambda: "master")

    with app.app_context():
        from spiffworkflow_backend.models.group import GroupModel
        from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
        from spiffworkflow_backend.models.permission_target import PermissionTargetModel
        from spiffworkflow_backend.models.principal import PrincipalModel
        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
        from spiffworkflow_backend.services.authorization_service import AuthorizationService

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

        user_info = {
            "iss": "http://localhost:7002/realms/master",
            "sub": "subject-123",
            "preferred_username": "super-admin",
            "groups": [
                "create-realm",
                "default-roles-master",
                "super-admin",
                "offline_access",
                "admin",
                "uma_authorization",
            ],
        }

        user = AuthorizationService.create_user_from_sign_in(user_info)
        group_identifiers = sorted(group.identifier for group in user.groups)
        permission_targets = {
            assignment.permission_target.uri for assignment in AuthorizationService.all_permission_assignments_for_user(user)
        }
        permission_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/m8flow/tenants")
        child_permission_allowed = AuthorizationService.user_has_permission(
            user,
            "read",
            "/v1.0/m8flow/tenants/tenant-a/members",
        )
        frontend_access_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/frontend-access")
        tenant_realm_create_allowed = AuthorizationService.user_has_permission(
            user,
            "create",
            "/v1.0/m8flow/tenant-realms",
        )
        # "everybody" permissions must apply for master realm users even though there is no tenant context.
        # SpiffWorkflow automatically adds all users to "everybody"; m8flow must do the same for super-admins.
        everybody_active_users_allowed = AuthorizationService.user_has_permission(
            user, "create", "/v1.0/active-users/ping"
        )
        everybody_extensions_allowed = AuthorizationService.user_has_permission(user, "read", "/v1.0/extensions")

    assert "everybody" in group_identifiers, f"expected 'everybody' in {group_identifiers}"
    assert "super-admin" in group_identifiers
    assert "/m8flow/tenants" in permission_targets
    assert "/frontend-access" in permission_targets
    assert permission_allowed is True
    assert child_permission_allowed is True
    assert frontend_access_allowed is True
    assert tenant_realm_create_allowed is True
    assert everybody_active_users_allowed is True
    assert everybody_extensions_allowed is True


def test_master_realm_create_user_from_sign_in_tolerates_default_group_assignment_race(monkeypatch) -> None:
    from sqlalchemy.exc import IntegrityError

    permissions_path = (
        Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "config" / "permissions" / "m8flow.yml"
    )
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_EXPIRE_ON_COMMIT"] = False
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP"] = "spiff_public"
    app.config["SPIFFWORKFLOW_BACKEND_PERMISSIONS_FILE_ABSOLUTE_PATH"] = str(permissions_path)

    from spiffworkflow_backend.models.db import db

    db.init_app(app)

    monkeypatch.setattr(authorization_service_patch, "_master_realm_identifier", lambda: "master")

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

        original_add_user_to_group = UserService.add_user_to_group.__func__

        def fake_add_user_to_group(cls, user, group):
            if getattr(group, "identifier", None) == "everybody":
                assignment_exists = (
                    UserGroupAssignmentModel.query.filter_by(user_id=user.id, group_id=group.id).first() is not None
                )
                if not assignment_exists:
                    db.session.add(UserGroupAssignmentModel(user_id=user.id, group_id=group.id))
                    db.session.commit()
                raise IntegrityError(
                    "INSERT INTO user_group_assignment (user_id, group_id) VALUES (?, ?)",
                    {"user_id": user.id, "group_id": group.id},
                    Exception("duplicate key value violates unique constraint user_group_assignment_unique"),
                )

            return original_add_user_to_group(cls, user, group)

        monkeypatch.setattr(UserService, "add_user_to_group", classmethod(fake_add_user_to_group))

        user_info = {
            "iss": "http://localhost:7002/realms/master",
            "sub": "subject-123",
            "preferred_username": "super-admin",
            "groups": ["super-admin"],
        }

        user = AuthorizationService.create_user_from_sign_in(user_info)
        group_identifiers = sorted(group.identifier for group in user.groups)

    assert "everybody" in group_identifiers
    assert "super-admin" in group_identifiers


def test_permission_scope_tenant_explicit_none_does_not_fall_through_to_request_tenant(
    monkeypatch,
) -> None:
    """
    Master-realm sign-ins call ``_permission_scope_tenant(None)`` to opt out of any tenant
    qualification.  The resolver must honor that explicit None and NOT fall back to the
    request-context tenant id, otherwise master-realm groups get qualified with an unrelated
    tenant prefix and master-realm users end up enrolled in ``tenant-fallback:everybody`` instead of
    the unqualified ``everybody`` group.
    """
    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_id_or_none",
        lambda: "tenant-fallback",
    )

    # Without an explicit scope, falls back to the request tenant.
    assert _active_permission_scope_tenant_id() == "tenant-fallback"

    # An explicit None scope overrides the fallback.
    with _permission_scope_tenant(None):
        assert _active_permission_scope_tenant_id() is None

    # Scope reset after the with-block.
    assert _active_permission_scope_tenant_id() == "tenant-fallback"

    # An explicit string scope still wins.
    with _permission_scope_tenant("tenant-x"):
        assert _active_permission_scope_tenant_id() == "tenant-x"


def test_group_identifier_applies_to_active_permission_scope_includes_everybody_without_tenant(
    monkeypatch,
) -> None:
    """The bare 'everybody' group must be visible even when there is no tenant context."""
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

    monkeypatch.setattr(
        authorization_service_patch,
        "current_tenant_identifiers",
        lambda tenant_id=None: set(),
    )

    with app.app_context():
        assert _group_identifier_applies_to_active_permission_scope("everybody") is True
        assert _group_identifier_applies_to_active_permission_scope("super-admin") is True
        assert _group_identifier_applies_to_active_permission_scope("tenant-a:editor") is False
        assert _group_identifier_applies_to_active_permission_scope("tenant-admin") is False


def test_shared_realm_create_user_from_sign_in_reuses_existing_same_realm_user(monkeypatch) -> None:
    import sys
    from types import ModuleType

    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []

    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = SimpleNamespace(
        session=SimpleNamespace(
            add=lambda *_args, **_kwargs: None,
            commit=lambda: None,
            expire=lambda *_args, **_kwargs: None,
        )
    )

    fake_user_module = ModuleType("spiffworkflow_backend.models.user")
    fake_user_module.SPIFF_GUEST_USER = "spiff_guest_user"
    fake_user_module.SPIFF_SYSTEM_USER = "spiff_system_user"
    fake_user_module.UserModel = SimpleNamespace(query=SimpleNamespace())

    fake_group_module = ModuleType("spiffworkflow_backend.models.group")
    fake_group_module.SPIFF_GUEST_GROUP = "spiff_guest_group"
    fake_group_module.GroupModel = SimpleNamespace

    fake_permission_assignment_module = ModuleType("spiffworkflow_backend.models.permission_assignment")
    fake_permission_assignment_module.PermissionAssignmentModel = SimpleNamespace

    fake_permission_target_module = ModuleType("spiffworkflow_backend.models.permission_target")
    fake_permission_target_module.PermissionTargetModel = SimpleNamespace

    fake_principal_module = ModuleType("spiffworkflow_backend.models.principal")
    fake_principal_module.MissingPrincipalError = Exception
    fake_principal_module.PrincipalModel = SimpleNamespace

    fake_user_group_assignment_module = ModuleType("spiffworkflow_backend.models.user_group_assignment")
    fake_user_group_assignment_module.UserGroupAssignmentModel = SimpleNamespace

    fake_waiting_module = ModuleType("spiffworkflow_backend.models.user_group_assignment_waiting")
    fake_waiting_module.UserGroupAssignmentWaitingModel = SimpleNamespace

    fake_api_error_module = ModuleType("spiffworkflow_backend.exceptions.api_error")

    class FakeApiError(Exception):
        def __init__(self, error_code: str, message: str, status_code: int):
            super().__init__(message)
            self.error_code = error_code
            self.message = message
            self.status_code = status_code

    fake_api_error_module.ApiError = FakeApiError
    fake_exceptions_package = ModuleType("spiffworkflow_backend.exceptions")
    fake_exceptions_package.api_error = fake_api_error_module

    captured_groups: list[str] = []
    captured_assignments: list[tuple[int, set[int], set[int]]] = []

    class FakeUserService:
        @classmethod
        def add_user_to_group_by_group_identifier(cls, user_model, group_identifier, source_is_open_id=False):
            group = SimpleNamespace(id=len(captured_groups) + 1, identifier=group_identifier)
            captured_groups.append(group_identifier)
            user_model.groups.append(group)
            return group

        @classmethod
        def update_human_task_assignments_for_user(cls, user, new_group_ids, old_group_ids):
            captured_assignments.append((user.id, set(new_group_ids), set(old_group_ids)))

    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_user_service_module.UserService = FakeUserService

    class FakeAuthorizationService:
        @classmethod
        def authentication_exclusion_list(cls):
            return []

        @classmethod
        def add_permission_from_uri_or_macro(cls, group_identifier, permission, target):
            return []

        @classmethod
        def import_permissions_from_yaml_file(cls, user_model):
            return None

    fake_auth_service_module = ModuleType("spiffworkflow_backend.services.authorization_service")
    fake_auth_service_module.AuthorizationService = FakeAuthorizationService

    fake_backend_package = ModuleType("spiffworkflow_backend")
    fake_backend_package.__path__ = [str(Path(__file__).resolve().parents[5] / "spiffworkflow-backend" / "src" / "spiffworkflow_backend")]
    fake_backend_services_package = ModuleType("spiffworkflow_backend.services")
    fake_backend_services_package.__path__ = [
        str(Path(__file__).resolve().parents[5] / "spiffworkflow-backend" / "src" / "spiffworkflow_backend" / "services")
    ]

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend", fake_backend_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services", fake_backend_services_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user", fake_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.group", fake_group_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.permission_assignment",
        fake_permission_assignment_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.permission_target", fake_permission_target_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.principal", fake_principal_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.user_group_assignment",
        fake_user_group_assignment_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.models.user_group_assignment_waiting",
        fake_waiting_module,
    )
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions", fake_exceptions_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(
        sys.modules,
        "spiffworkflow_backend.services.authorization_service",
        fake_auth_service_module,
    )
    monkeypatch.setattr(authorization_service_patch, "_PATCHED", False)

    with app.app_context():
        from spiffworkflow_backend.services.authorization_service import AuthorizationService

        authorization_service_patch.apply()

        existing_user = SimpleNamespace(
            id=7,
            username="admin",
            service="http://localhost:7002/realms/m8flow",
            service_id="legacy-subject",
            email="old@example.com",
            display_name="Old Admin",
            groups=[],
        )
        monkeypatch.setattr(
            authorization_service_patch,
            "_find_existing_user_for_sign_in",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            authorization_service_patch,
            "_find_existing_user_in_same_realm",
            lambda *_args, **_kwargs: existing_user,
        )
        monkeypatch.setattr(
            AuthorizationService,
            "import_permissions_from_yaml_file",
            lambda user_model: None,
        )

        user_info = {
            "iss": "http://localhost:7002/realms/m8flow",
            "sub": "subject-123",
            "preferred_username": "admin",
            "m8flow_tenant_id": "tenant-a-id",
            "groups": ["tenant-admin", "everybody"],
        }

        user = AuthorizationService.create_user_from_sign_in(user_info)
        group_identifiers = sorted(group.identifier for group in user.groups)

    assert user is existing_user
    assert user.service_id == "subject-123"
    assert group_identifiers == ["tenant-a-id:/everybody", "tenant-a-id:/tenant-admin"]
    assert captured_groups == ["tenant-a-id:/tenant-admin", "tenant-a-id:/everybody"]
    assert captured_assignments


def test_openid_group_identifiers_from_user_info_master_realm_filters_builtin_roles(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.authorization_service_patch._master_realm_identifier",
        lambda: "master",
    )

    user_info = {
        "iss": "http://localhost:7002/realms/master",
        "groups": [
            "create-realm",
            "default-roles-master",
            "super-admin",
            "offline_access",
            "admin",
            "uma_authorization",
        ],
    }

    assert _openid_group_identifiers_from_user_info(user_info, tenant_id=None) == ["super-admin"]


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
def test_create_user_from_sign_in_syncs_roles_and_org_groups_separately(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

    fake_user = SimpleNamespace(
        id=42,
        username="editor-user",
        display_name="editor-user",
        email="editor@example.com",
        service="http://localhost:7002/realms/shared",
        service_id="subject-123",
        groups=[],
    )
    captured_group_identifiers: list[tuple[str, bool]] = []
    update_calls: list[tuple[set[int], set[int]]] = []

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        monkeypatch.setattr(authorization_service_patch, "_find_existing_user_for_sign_in", lambda *args, **kwargs: fake_user)
        monkeypatch.setattr(db.session, "add", lambda _obj: None)
        monkeypatch.setattr(db.session, "commit", lambda: None)
        monkeypatch.setattr(db.session, "expire", lambda _obj, _attrs: None)
        monkeypatch.setattr(
            AuthorizationService,
            "import_permissions_from_yaml_file",
            classmethod(lambda cls, user_model: None),
        )

        class _FakeAssignmentQuery:
            def filter_by(self, **kwargs):  # noqa: ANN003
                return self

            def first(self):
                return None

        monkeypatch.setattr(UserGroupAssignmentModel, "query", _FakeAssignmentQuery())
        monkeypatch.setattr(
            UserService,
            "find_or_create_group",
            classmethod(
                lambda cls, group_identifier, source_is_open_id=False: (
                    captured_group_identifiers.append((group_identifier, source_is_open_id))
                    or SimpleNamespace(id=len(captured_group_identifiers), identifier=group_identifier)
                )
            ),
        )
        monkeypatch.setattr(
            UserService,
            "add_user_to_group",
            classmethod(lambda cls, user_model, group_model: user_model.groups.append(group_model)),
        )
        monkeypatch.setattr(UserService, "remove_user_from_group", classmethod(lambda cls, user_model, group_id: None))
        monkeypatch.setattr(
            UserService,
            "update_human_task_assignments_for_user",
            classmethod(
                lambda cls, user_model, new_group_ids, old_group_ids: update_calls.append((new_group_ids, old_group_ids))
            ),
        )

        user_info = {
            TENANT_CLAIM: "tenant-a",
            "iss": "http://localhost:7002/realms/shared",
            "sub": "subject-123",
            "preferred_username": "editor-user",
            "email": "editor@example.com",
            "groups": ["/Engineering", "/editor"],
            "roles": ["editor"],
        }
        result = AuthorizationService.create_user_from_sign_in(user_info)

    assert result is fake_user
    assert captured_group_identifiers == [
        ("tenant-a:/Engineering", True),
        ("tenant-a:/editor", True),
        ("tenant-a:editor", True),
    ]
    assert update_calls == [({1, 2, 3}, set())]


def test_create_user_from_sign_in_groups_only_token_syncs_only_organizational_groups(monkeypatch) -> None:
    app = Flask(__name__)  # NOSONAR - unit test
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"] = True
    app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"] = []
    app.config["SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP"] = "everybody"

    fake_user = SimpleNamespace(
        id=7,
        username="reviewer-user",
        display_name="reviewer-user",
        email="reviewer@example.com",
        service="http://localhost:7002/realms/shared",
        service_id="subject-456",
        groups=[],
    )
    captured_group_identifiers: list[tuple[str, bool]] = []

    with app.app_context():
        authorization_service_patch.apply()
        from spiffworkflow_backend.models.db import db
        from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
        from spiffworkflow_backend.services.authorization_service import AuthorizationService
        from spiffworkflow_backend.services.user_service import UserService

        monkeypatch.setattr(authorization_service_patch, "_find_existing_user_for_sign_in", lambda *args, **kwargs: fake_user)
        monkeypatch.setattr(db.session, "add", lambda _obj: None)
        monkeypatch.setattr(db.session, "commit", lambda: None)
        monkeypatch.setattr(db.session, "expire", lambda _obj, _attrs: None)
        monkeypatch.setattr(
            AuthorizationService,
            "import_permissions_from_yaml_file",
            classmethod(lambda cls, user_model: None),
        )

        class _FakeAssignmentQuery:
            def filter_by(self, **kwargs):  # noqa: ANN003
                return self

            def first(self):
                return None

        monkeypatch.setattr(UserGroupAssignmentModel, "query", _FakeAssignmentQuery())
        monkeypatch.setattr(
            UserService,
            "find_or_create_group",
            classmethod(
                lambda cls, group_identifier, source_is_open_id=False: (
                    captured_group_identifiers.append((group_identifier, source_is_open_id))
                    or SimpleNamespace(id=len(captured_group_identifiers), identifier=group_identifier)
                )
            ),
        )
        monkeypatch.setattr(
            UserService,
            "add_user_to_group",
            classmethod(lambda cls, user_model, group_model: user_model.groups.append(group_model)),
        )
        monkeypatch.setattr(UserService, "remove_user_from_group", classmethod(lambda cls, user_model, group_id: None))
        monkeypatch.setattr(
            UserService,
            "update_human_task_assignments_for_user",
            classmethod(lambda cls, user_model, new_group_ids, old_group_ids: None),
        )

        user_info = {
            TENANT_CLAIM: "tenant-a",
            "iss": "http://localhost:7002/realms/shared",
            "sub": "subject-456",
            "preferred_username": "reviewer-user",
            "email": "reviewer@example.com",
            "groups": ["reviewer", "/Operations"],
        }
        AuthorizationService.create_user_from_sign_in(user_info)

    assert captured_group_identifiers == [
        ("tenant-a:/reviewer", True),
        ("tenant-a:/Operations", True),
    ]
