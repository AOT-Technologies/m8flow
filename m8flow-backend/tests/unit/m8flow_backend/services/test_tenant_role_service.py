from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType
from types import SimpleNamespace
from typing import Any


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
        "tenant-admin",
        "editor",
        "integrator",
        "reviewer",
        "viewer",
    )
    fake_keycloak_service_module.add_organization_group_member = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_by_id = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_by_alias = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_member_by_username = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.get_organization_member_groups = lambda *_args, **_kwargs: []
    fake_keycloak_service_module.remove_organization_group_member = lambda *_args, **_kwargs: None
    fake_keycloak_service_module.search_organization_members = lambda *_args, **_kwargs: []

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
        lambda organization_id, member_id: (
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
    synced_assignments: list[tuple[int, set[int], set[int]]] = []
    group = SimpleNamespace(id=42, identifier="tenant-it-id:editor")
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
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_tenant_role_group",
        lambda role_name, tenant_id: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_ensure_local_assignment",
        lambda user, role_group, tenant_id: True,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id: ["editor"],
    )
    monkeypatch.setattr(
        tenant_role_service.UserService,
        "update_human_task_assignments_for_user",
        lambda user, new_group_ids, old_group_ids: synced_assignments.append(
            (user.id, set(new_group_ids), set(old_group_ids))
        ),
    )

    result = tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == ["editor"]
    assert synced_assignments == [(9, {42}, set())]


def test_assign_tenant_role_imports_yaml_permissions_within_tenant_scope(monkeypatch):
    """Granting a role must also enroll the user in the tenant's everybody group via YAML import."""
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group = SimpleNamespace(id=42, identifier="tenant-it-id:editor")
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
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(tenant_role_service, "_tenant_role_group", lambda role_name, tenant_id: group)
    monkeypatch.setattr(tenant_role_service, "_ensure_local_assignment", lambda user, role_group, tenant_id: True)
    monkeypatch.setattr(tenant_role_service, "_normalized_member_roles", lambda organization_id, member_id: ["editor"])

    auth_patch = sys.modules["m8flow_backend.services.authorization_service_patch"]
    auth_service = sys.modules["spiffworkflow_backend.services.authorization_service"]
    auth_patch._permission_scope_tenant_calls.clear()
    auth_service._yaml_imports.clear()

    tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    # YAML permissions must be imported exactly once, with the user, inside a permission scope
    # whose tenant id matches the target tenant — that is what creates :everybody and enrolls the user.
    assert auth_service._yaml_imports == [local_user]
    assert auth_patch._permission_scope_tenant_calls == ["tenant-it-id"]


def test_assign_tenant_role_returns_requested_role_even_if_keycloak_roles_are_stale(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group = SimpleNamespace(id=42, identifier="tenant-it-id:editor")
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
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_tenant_role_group",
        lambda role_name, tenant_id: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_ensure_local_assignment",
        lambda user, role_group, tenant_id: True,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id: [],
    )

    result = tenant_role_service.assign_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == ["editor"]


def test_remove_tenant_role_syncs_keycloak_and_local_assignment(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    synced_assignments: list[tuple[int, set[int], set[int]]] = []
    group = SimpleNamespace(id=42, identifier="tenant-it-id:editor")
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
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_tenant_role_group",
        lambda role_name, tenant_id: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_delete_local_assignment",
        lambda user, role_group, tenant_id: True,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id: [],
    )
    monkeypatch.setattr(
        tenant_role_service.UserService,
        "update_human_task_assignments_for_user",
        lambda user, new_group_ids, old_group_ids: synced_assignments.append(
            (user.id, set(new_group_ids), set(old_group_ids))
        ),
    )

    result = tenant_role_service.remove_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == []
    assert synced_assignments == [(9, set(), {42})]


def test_remove_tenant_role_returns_updated_roles_even_if_keycloak_readback_is_stale(monkeypatch):
    tenant_role_service = _load_tenant_role_service(monkeypatch)
    group = SimpleNamespace(id=42, identifier="tenant-it-id:editor")
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
        "upsert_local_shared_realm_member",
        lambda input_member: local_user,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_tenant_role_group",
        lambda role_name, tenant_id: group,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_delete_local_assignment",
        lambda user, role_group, tenant_id: True,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id: ["editor"],
    )

    result = tenant_role_service.remove_tenant_role("tenant-it-id", "editor", "editor")

    assert result["roles"] == []
