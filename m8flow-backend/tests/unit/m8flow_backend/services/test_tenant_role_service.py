from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace
from typing import Any

import pytest


def _load_tenant_role_service(monkeypatch):
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

    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = SimpleNamespace(
        session=SimpleNamespace(
            add=lambda *_args, **_kwargs: None,
            commit=lambda: None,
            delete=lambda *_args, **_kwargs: None,
        )
    )

    fake_uga_module = ModuleType("spiffworkflow_backend.models.user_group_assignment")

    class FakeUserGroupAssignmentModel:
        query = SimpleNamespace(filter_by=lambda **_kwargs: SimpleNamespace(first=lambda: None))

        def __init__(self, **kwargs):
            self.id = kwargs.get("id", 1)
            self.user_id = kwargs.get("user_id")
            self.group_id = kwargs.get("group_id")
            self.m8f_tenant_id = kwargs.get("m8f_tenant_id")

    fake_uga_module.UserGroupAssignmentModel = FakeUserGroupAssignmentModel

    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")

    class FakeUserService:
        @classmethod
        def find_or_create_group(cls, identifier, source_is_open_id=False):
            return SimpleNamespace(id=1, identifier=identifier, source_is_open_id=source_is_open_id)

        @classmethod
        def update_human_task_assignments_for_user(cls, *_args, **_kwargs):
            return None

    fake_user_service_module.UserService = FakeUserService

    fake_tenant_service_module = ModuleType("m8flow_backend.services.tenant_service")

    class FakeTenantService:
        @staticmethod
        def get_tenant_by_id(tenant_id):
            return SimpleNamespace(id=tenant_id, slug="it", name="Information Technology")

    fake_tenant_service_module.TenantService = FakeTenantService

    fake_keycloak_service_module = ModuleType("m8flow_backend.services.keycloak_service")
    fake_keycloak_service_module.DEFAULT_ORGANIZATION_ROLE_GROUP_NAMES = (
        "Approvers",
        "Designers",
        "Administrators",
        "Support",
        "Submitters",
        "Viewers",
    )
    fake_keycloak_service_module.add_organization_member = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.add_organization_group_member = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_by_id = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_by_alias = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_group_by_id = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_member_by_username = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_member_groups = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.get_realm_user_by_username = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.list_organization_group_members = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.list_organization_groups = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.organization_group_role_names = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.remove_organization_group_member = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.search_realm_users = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.search_organization_members = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.set_organization_group_role_names = lambda *_args, **_kwargs: {}
    fake_keycloak_service_module.shared_realm_name = lambda: "m8flow"

    fake_tenant_identity_helpers_module = ModuleType("m8flow_backend.services.tenant_identity_helpers")
    fake_tenant_identity_helpers_module.qualify_group_identifier = (
        lambda group_identifier, tenant_id=None: f"{tenant_id}:{group_identifier}" if tenant_id else group_identifier
    )
    fake_tenant_identity_helpers_module.upsert_local_shared_realm_member = lambda *_args, **_kwargs: None

    fake_auth_patch_module = ModuleType("m8flow_backend.services.authorization_service_patch")
    auth_patch_scope_calls: list[str | None] = []

    from contextlib import contextmanager

    @contextmanager
    def _fake_permission_scope_tenant(tenant_id):
        auth_patch_scope_calls.append(tenant_id)
        yield

    fake_auth_patch_module._permission_scope_tenant = _fake_permission_scope_tenant
    fake_auth_patch_module._permission_scope_tenant_calls = auth_patch_scope_calls

    fake_auth_service_module = ModuleType("spiffworkflow_backend.services.authorization_service")
    yaml_imports: list[Any] = []

    class FakeAuthorizationService:
        @classmethod
        def import_permissions_from_yaml_file(cls, user_model):
            yaml_imports.append(user_model)
            return None

    fake_auth_service_module.AuthorizationService = FakeAuthorizationService
    fake_auth_service_module._yaml_imports = yaml_imports

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions", fake_exceptions_package)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.exceptions.api_error", fake_api_error_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user_group_assignment", fake_uga_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.authorization_service", fake_auth_service_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.tenant_service", fake_tenant_service_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.keycloak_service", fake_keycloak_service_module)
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_identity_helpers",
        fake_tenant_identity_helpers_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.authorization_service_patch",
        fake_auth_patch_module,
    )

    sys.modules.pop("m8flow_backend.services.tenant_role_service", None)
    return import_module("m8flow_backend.services.tenant_role_service")


def test_list_tenant_members_with_roles_uses_organization_memberships(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "search_organization_members",
        lambda organization_id, search, exact=False, max_results=100: [
            {"id": "member-2", "username": "reviewer", "email": "reviewer@example.com"},
            {"id": "member-1", "username": "editor", "email": "editor@example.com"},
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id, group_role_lookup=None: (
            ["reviewer"] if member_id == "member-2" else ["editor", "viewer"]
        ),
    )

    result = tenant_role_service.list_tenant_members_with_roles("tenant-it-id")

    assert result == [
        {
            "id": "member-1",
            "username": "editor",
            "email": "editor@example.com",
            "display_name": None,
            "roles": ["editor", "viewer"],
        },
        {
            "id": "member-2",
            "username": "reviewer",
            "email": "reviewer@example.com",
            "display_name": None,
            "roles": ["reviewer"],
        },
    ]


def test_list_available_tenant_users_excludes_existing_members(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "search_organization_members",
        lambda organization_id, search, exact=False, max_results=100: [
            {"id": "member-1", "username": "editor", "email": "editor@example.com"}
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "search_realm_users",
        lambda realm, search, exact=False, max_results=100: [
            {"id": "user-1", "username": "editor", "email": "editor@example.com"},
            {"id": "user-2", "username": "reviewer", "email": None},
        ],
    )

    result = tenant_role_service.list_available_tenant_users("tenant-it-id")

    assert result == [
        {
            "id": "user-2",
            "username": "reviewer",
            "email": None,
            "display_name": None,
        }
    ]


def test_list_tenant_groups_with_members_reflects_group_members_and_dynamic_role_mappings(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id: [
            {"id": "group-1", "name": "Administrators", "path": "/Administrators"},
            {"id": "group-2", "name": "Custom Review", "path": "/Custom Review"},
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda organization_id, group_id: (
            [{"id": "member-1", "username": "admin", "email": "admin@example.com"}]
            if group_id == "group-1"
            else [{"id": "member-2", "username": "reviewer", "email": None}]
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda group: (
            ["tenant-admin"]
            if group.get("name") == "Administrators"
            else ["reviewer"]
        ),
    )

    result = tenant_role_service.list_tenant_groups_with_members("tenant-it-id")

    assert result == [
        {
            "id": "group-1",
            "name": "Administrators",
            "path": "/Administrators",
            "mapped_roles": ["tenant-admin"],
            "member_count": 1,
            "members": [
                {
                    "id": "member-1",
                    "username": "admin",
                    "email": "admin@example.com",
                    "display_name": None,
                }
            ],
        },
        {
            "id": "group-2",
            "name": "Custom Review",
            "path": "/Custom Review",
            "mapped_roles": ["reviewer"],
            "member_count": 1,
            "members": [
                {
                    "id": "member-2",
                    "username": "reviewer",
                    "email": None,
                    "display_name": None,
                }
            ],
        },
    ]


def test_add_tenant_member_adds_existing_user_assigns_groups_and_syncs_locally(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    organization_member_additions: list[tuple[str, str]] = []
    group_membership_additions: list[tuple[str, str, str]] = []
    synced_roles: list[tuple[int, str, list[str]]] = []
    yaml_imports: list[tuple[int, str]] = []
    member_lookup_calls = {"count": 0}
    member = {
        "id": "member-1",
        "username": "reviewer",
        "email": "reviewer@example.com",
    }
    local_user = SimpleNamespace(id=9, username="reviewer")

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id: [{"id": "group-1", "name": "Approvers", "path": "/Approvers"}],
    )

    def _lookup_member(_organization_id, _username):
        member_lookup_calls["count"] += 1
        return None if member_lookup_calls["count"] == 1 else member

    monkeypatch.setattr(tenant_role_service, "get_organization_member_by_username", _lookup_member)
    monkeypatch.setattr(
        tenant_role_service,
        "get_realm_user_by_username",
        lambda realm, username: {"id": "user-1", "username": username, "email": "reviewer@example.com"},
    )
    monkeypatch.setattr(
        tenant_role_service,
        "add_organization_member",
        lambda organization_id, user_id: organization_member_additions.append((organization_id, user_id)),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "add_organization_group_member",
        lambda organization_id, group_name, member_id: group_membership_additions.append(
            (organization_id, group_name, member_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id, group_role_lookup=None: ["reviewer"],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_role_assignments",
        lambda user, tenant_id, roles: synced_roles.append((user.id, tenant_id, roles)),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_ensure_tenant_yaml_permissions_and_everybody_membership",
        lambda user, tenant_id: yaml_imports.append((user.id, tenant_id)),
    )

    result = tenant_role_service.add_tenant_member(
        "tenant-it-id",
        username="reviewer",
        group_names=["Approvers"],
    )

    assert result == {
        "id": "member-1",
        "username": "reviewer",
        "email": "reviewer@example.com",
        "display_name": None,
        "roles": ["reviewer"],
    }
    assert organization_member_additions == [("org-it", "user-1")]
    assert group_membership_additions == [("org-it", "Approvers", "member-1")]
    assert synced_roles == [(9, "tenant-it-id", ["reviewer"])]
    assert yaml_imports == [(9, "tenant-it-id")]


def test_add_tenant_member_requires_existing_keycloak_user(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(tenant_role_service, "list_organization_groups", lambda organization_id: [])
    monkeypatch.setattr(tenant_role_service, "get_organization_member_by_username", lambda organization_id, username: None)
    monkeypatch.setattr(tenant_role_service, "get_realm_user_by_username", lambda realm, username: None)

    with pytest.raises(Exception) as exc_info:
        tenant_role_service.add_tenant_member(
            "tenant-it-id",
            username="reviewer",
        )

    assert getattr(exc_info.value, "error_code", "") == "tenant_member_not_found"


def test_add_tenant_group_member_syncs_group_membership_and_local_roles(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group_membership_additions: list[tuple[str, str, str]] = []
    synced_roles: list[tuple[int, str, list[str]]] = []
    yaml_imports: list[tuple[int, str]] = []
    member = {"id": "member-1", "username": "reviewer", "email": "reviewer@example.com"}
    local_user = SimpleNamespace(id=9, username="reviewer")

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id: [{"id": "group-1", "name": "Approvers", "path": "/Approvers"}],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "add_organization_group_member",
        lambda organization_id, group_name, member_id: group_membership_additions.append(
            (organization_id, group_name, member_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id, group_role_lookup=None: ["reviewer"],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_role_assignments",
        lambda user, tenant_id, roles: synced_roles.append((user.id, tenant_id, roles)),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_ensure_tenant_yaml_permissions_and_everybody_membership",
        lambda user, tenant_id: yaml_imports.append((user.id, tenant_id)),
    )

    result = tenant_role_service.add_tenant_group_member("tenant-it-id", "reviewer", "Approvers")

    assert result["roles"] == ["reviewer"]
    assert group_membership_additions == [("org-it", "Approvers", "member-1")]
    assert synced_roles == [(9, "tenant-it-id", ["reviewer"])]
    assert yaml_imports == [(9, "tenant-it-id")]


def test_remove_tenant_group_member_syncs_group_membership_and_local_roles(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group_membership_removals: list[tuple[str, str, str]] = []
    synced_roles: list[tuple[int, str, list[str]]] = []
    yaml_imports: list[tuple[int, str]] = []
    member = {"id": "member-1", "username": "reviewer", "email": "reviewer@example.com"}
    local_user = SimpleNamespace(id=9, username="reviewer")

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id: [{"id": "group-1", "name": "Approvers", "path": "/Approvers"}],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "remove_organization_group_member",
        lambda organization_id, group_name, member_id: group_membership_removals.append(
            (organization_id, group_name, member_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id, group_role_lookup=None: [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_role_assignments",
        lambda user, tenant_id, roles: synced_roles.append((user.id, tenant_id, roles)),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_ensure_tenant_yaml_permissions_and_everybody_membership",
        lambda user, tenant_id: yaml_imports.append((user.id, tenant_id)),
    )

    result = tenant_role_service.remove_tenant_group_member("tenant-it-id", "reviewer", "Approvers")

    assert result["roles"] == []
    assert group_membership_removals == [("org-it", "Approvers", "member-1")]
    assert synced_roles == [(9, "tenant-it-id", [])]
    assert yaml_imports == [(9, "tenant-it-id")]


def test_assign_tenant_group_role_maps_role_and_syncs_group_members(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    mapped_roles: list[tuple[str, tuple[str, ...]]] = []
    synced_members: list[tuple[str, str, dict[str, dict[str, list[str]]]]] = []

    tenant = SimpleNamespace(id="tenant-it-id", slug="it", name="Information Technology")
    group = {"id": "group-1", "name": "Approvers", "path": "/Approvers"}
    role_lookup = {
        "by_group_id": {"group-1": ["reviewer"]},
        "by_group_name": {"approvers": ["reviewer"]},
    }

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (tenant, {"id": "org-it", "alias": "it"}, "org-it"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_or_error",
        lambda organization_id, group_name: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "set_organization_group_role_names",
        lambda organization_id, group_id, role_names: (
            mapped_roles.append((group_id, tuple(role_names)))
            or {"id": group_id, "name": "Approvers", "path": "/Approvers"}
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_mapped_roles_for_group",
        lambda input_group, organization_id=None, group_role_lookup=None: [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_role_lookup",
        lambda organization_id: role_lookup,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_members_for_group",
        lambda tenant_obj, organization_id, input_group, group_role_lookup=None: synced_members.append(
            (tenant_obj.id, organization_id, group_role_lookup)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_serialize_group",
        lambda organization_id, input_group, group_role_lookup=None: {
            "id": "group-1",
            "name": "Approvers",
            "path": "/Approvers",
            "mapped_roles": ["reviewer"],
            "member_count": 1,
            "members": [{"id": "member-1", "username": "reviewer", "email": None, "display_name": None}],
        },
    )

    result = tenant_role_service.assign_tenant_group_role("tenant-it-id", "Approvers", "reviewer")

    assert result["mapped_roles"] == ["reviewer"]
    assert mapped_roles == [("group-1", ("reviewer",))]
    assert synced_members == [("tenant-it-id", "org-it", role_lookup)]


def test_remove_tenant_group_role_unmaps_role_and_syncs_group_members(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    removed_roles: list[tuple[str, tuple[str, ...]]] = []
    synced_members: list[tuple[str, str, dict[str, dict[str, list[str]]]]] = []

    tenant = SimpleNamespace(id="tenant-it-id", slug="it", name="Information Technology")
    group = {"id": "group-1", "name": "Approvers", "path": "/Approvers"}
    role_lookup = {
        "by_group_id": {"group-1": []},
        "by_group_name": {"approvers": []},
    }

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (tenant, {"id": "org-it", "alias": "it"}, "org-it"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_or_error",
        lambda organization_id, group_name: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "set_organization_group_role_names",
        lambda organization_id, group_id, role_names: (
            removed_roles.append((group_id, tuple(role_names)))
            or {"id": group_id, "name": "Approvers", "path": "/Approvers"}
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_mapped_roles_for_group",
        lambda input_group, organization_id=None, group_role_lookup=None: ["reviewer"],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_role_lookup",
        lambda organization_id: role_lookup,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_members_for_group",
        lambda tenant_obj, organization_id, input_group, group_role_lookup=None: synced_members.append(
            (tenant_obj.id, organization_id, group_role_lookup)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_serialize_group",
        lambda organization_id, input_group, group_role_lookup=None: {
            "id": "group-1",
            "name": "Approvers",
            "path": "/Approvers",
            "mapped_roles": [],
            "member_count": 1,
            "members": [{"id": "member-1", "username": "reviewer", "email": None, "display_name": None}],
        },
    )

    result = tenant_role_service.remove_tenant_group_role("tenant-it-id", "Approvers", "reviewer")

    assert result["mapped_roles"] == []
    assert removed_roles == [("group-1", ())]
    assert synced_members == [("tenant-it-id", "org-it", role_lookup)]


def test_organization_for_tenant_prefers_canonical_tenant_id(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    organization_id_calls: list[str] = []
    alias_calls: list[str] = []

    monkeypatch.setattr(
        tenant_role_service.TenantService,
        "get_tenant_by_id",
        lambda tenant_id: SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_by_id",
        lambda organization_id: (
            organization_id_calls.append(organization_id)
            or {"id": "org-it", "alias": "it", "name": "Information Technology"}
            if organization_id == "tenant-it-id"
            else None
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_by_alias",
        lambda alias: alias_calls.append(alias) or None,
    )

    tenant, organization, organization_id = tenant_role_service._organization_for_tenant("tenant-it-id")

    assert tenant.id == "tenant-it-id"
    assert organization["id"] == "org-it"
    assert organization_id == "org-it"
    assert organization_id_calls == ["tenant-it-id"]
    assert alias_calls == []


def test_organization_for_tenant_falls_back_to_alias(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    organization_id_calls: list[str] = []
    alias_calls: list[str] = []

    monkeypatch.setattr(
        tenant_role_service.TenantService,
        "get_tenant_by_id",
        lambda tenant_id: SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_by_id",
        lambda organization_id: organization_id_calls.append(organization_id) or None,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_by_alias",
        lambda alias: (
            alias_calls.append(alias)
            or {"id": "org-it", "alias": "it", "name": "Information Technology"}
            if alias == "it"
            else None
        ),
    )

    tenant, organization, organization_id = tenant_role_service._organization_for_tenant("tenant-it-id")

    assert tenant.id == "tenant-it-id"
    assert organization["id"] == "org-it"
    assert organization_id == "org-it"
    assert organization_id_calls == ["tenant-it-id"]
    assert alias_calls == ["it"]


def test_assign_tenant_role_syncs_keycloak_and_local_assignment(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group_membership_additions: list[tuple[str, str, str]] = []
    local_user = SimpleNamespace(id=9, username="editor")
    member = {"id": "member-1", "username": "editor", "email": "editor@example.com"}

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "add_organization_group_member",
        lambda organization_id, group_name, member_id: group_membership_additions.append(
            (organization_id, group_name, member_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant_obj, organization_id, input_member, group_role_lookup=None: (local_user, ["editor"]),
    )

    result = tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == ["editor"]
    assert group_membership_additions == [("org-it", "Designers", "member-1")]


def test_assign_tenant_role_imports_yaml_permissions_within_tenant_scope(monkeypatch):
    """Granting a role must also enroll the user in the tenant's everybody group via YAML import."""
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    local_user = SimpleNamespace(id=9, username="editor")
    member = {"id": "member-1", "username": "editor", "email": "editor@example.com"}

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )

    auth_patch = sys.modules["m8flow_backend.services.authorization_service_patch"]
    auth_service = sys.modules["spiffworkflow_backend.services.authorization_service"]
    auth_patch._permission_scope_tenant_calls.clear()
    auth_service._yaml_imports.clear()

    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant_obj, organization_id, input_member, group_role_lookup=None: (
            auth_patch._permission_scope_tenant_calls.append(tenant_obj.id)
            or auth_service._yaml_imports.append(local_user)
            or (local_user, ["editor"])
        ),
    )

    tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    # YAML permissions must be imported exactly once, with the user, inside a permission scope
    # whose tenant id matches the target tenant — that is what creates :everybody and enrolls the user.
    assert auth_service._yaml_imports == [local_user]
    assert auth_patch._permission_scope_tenant_calls == ["tenant-it-id"]


def test_assign_tenant_role_returns_requested_role_even_if_keycloak_roles_are_stale(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    local_user = SimpleNamespace(id=9, username="editor")
    member = {"id": "member-1", "username": "editor", "email": "editor@example.com"}

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant_obj, organization_id, input_member, group_role_lookup=None: (local_user, []),
    )

    result = tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == []


def test_remove_tenant_role_syncs_keycloak_and_local_assignment(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    removed_group_memberships: list[tuple[str, str, str]] = []
    local_user = SimpleNamespace(id=9, username="editor")
    member = {"id": "member-1", "username": "editor", "email": "editor@example.com"}

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "remove_organization_group_member",
        lambda organization_id, group_name, member_id: removed_group_memberships.append(
            (organization_id, group_name, member_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant_obj, organization_id, input_member, group_role_lookup=None: (local_user, []),
    )

    result = tenant_role_service.remove_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == []
    assert removed_group_memberships == [
        ("org-it", "Designers", "member-1"),
        ("org-it", "editor", "member-1"),
    ]


def test_remove_tenant_role_returns_updated_roles_even_if_keycloak_readback_is_stale(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    local_user = SimpleNamespace(id=9, username="editor")
    member = {"id": "member-1", "username": "editor", "email": "editor@example.com"}

    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="it", name="Information Technology"),
            {"id": "org-it", "alias": "it"},
            "org-it",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username: member,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant_obj, organization_id, input_member, group_role_lookup=None: (local_user, ["viewer"]),
    )

    result = tenant_role_service.remove_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == ["viewer"]
