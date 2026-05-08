from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace
from typing import Any

from flask import Flask

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.services.tenant_identity_helpers import filter_users_for_current_tenant
from m8flow_backend.services.tenant_identity_helpers import active_organization_from_payload
from m8flow_backend.services.tenant_identity_helpers import organization_memberships_from_payload
from m8flow_backend.services.tenant_identity_helpers import organization_group_identifiers_from_payload
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import is_global_permission_group_identifier
from m8flow_backend.services.tenant_identity_helpers import resolve_user_for_current_tenant
from m8flow_backend.services.tenant_identity_helpers import authentication_identifier_from_payload
from m8flow_backend.services.tenant_identity_helpers import single_organization_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_alias_from_payload
from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_slug_for_identifier
from m8flow_backend.services.tenant_identity_helpers import user_belongs_to_current_tenant
from m8flow_backend.tenancy import set_context_tenant_id
from m8flow_backend.tenancy import reset_context_tenant_id


def test_qualify_group_identifier_qualifies_bare_and_preserves_qualified(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        lambda: "tenant-a",
    )

    assert qualify_group_identifier("reviewer") == "tenant-a:reviewer"
    assert qualify_group_identifier("tenant-b:admin") == "tenant-b:admin"


def test_qualify_group_identifier_preserves_global_super_admin_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        lambda: "tenant-a",
    )

    assert qualify_group_identifier("super-admin") == "super-admin"
    assert qualify_group_identifier("default:super-admin") == "super-admin"
    assert is_global_permission_group_identifier("super-admin") is True
    assert is_global_permission_group_identifier("default:super-admin") is True


def test_display_group_identifier_rewrites_tenant_prefix_to_slug(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._tenant_slug_for_identifier",
        lambda tenant_identifier: "tenant-slug" if tenant_identifier == "tenant-id" else None,
    )

    assert display_group_identifier("tenant-id:reviewer") == "tenant-slug:reviewer"


def test_tenant_slug_for_identifier_wraps_private_slug_lookup(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._tenant_slug_for_identifier",
        lambda tenant_identifier: "tenant-slug" if tenant_identifier == "tenant-id" else None,
    )

    assert tenant_slug_for_identifier("tenant-id") == "tenant-slug"
    assert tenant_slug_for_identifier("missing") is None


def test_display_group_identifier_preserves_value_when_slug_lookup_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._tenant_slug_for_identifier",
        lambda tenant_identifier: None,
    )

    assert display_group_identifier("tenant-id:reviewer") == "tenant-id:reviewer"
    assert display_group_identifier("reviewer") == "reviewer"


def test_filter_users_for_current_tenant_accepts_service_realm_and_legacy_suffix(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a", "tenant-a-slug"},
    )
    users = [
        SimpleNamespace(username="alice", service="http://localhost:7002/realms/tenant-a"),
        SimpleNamespace(username="bob@tenant-a", service="http://localhost:7002/realms/other"),
        SimpleNamespace(username="charlie", service="http://localhost:7002/realms/tenant-b"),
    ]

    filtered = filter_users_for_current_tenant(users)

    assert [user.username for user in filtered] == ["alice", "bob@tenant-a"]


def test_user_belongs_to_current_tenant_accepts_tenant_qualified_group_membership(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )
    user = SimpleNamespace(
        username="editor",
        service="http://localhost:7002/realms/m8flow",
        groups=[SimpleNamespace(identifier="tenant-a-id:editor")],
    )

    assert user_belongs_to_current_tenant(user) is True


def test_find_users_for_current_tenant_by_identifier_falls_back_to_shared_realm_provision(monkeypatch) -> None:
    provisioned_user = SimpleNamespace(username="editor", service="http://localhost:7002/realms/m8flow")

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return []

    class FakeUserModel:
        query = FakeQuery()
        username = object()

    fake_user_module = ModuleType("spiffworkflow_backend.models.user")
    fake_user_module.UserModel = FakeUserModel
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user", fake_user_module)
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._provision_shared_realm_user_for_tenant",
        lambda username, tenant_id=None: provisioned_user if username == "editor" else None,
    )

    assert find_users_for_current_tenant_by_identifier("editor") == [provisioned_user]


def test_find_users_for_current_tenant_by_username_prefix_includes_shared_realm_org_members(monkeypatch) -> None:
    from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_username_prefix

    local_user = SimpleNamespace(id=1, username="editor")
    provisioned_user = SimpleNamespace(id=2, username="editorial")

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return [local_user]

    class FakeUsernameField:
        def like(self, _pattern):
            return self

    class FakeUserModel:
        query = FakeQuery()
        username = FakeUsernameField()

    fake_user_module = ModuleType("spiffworkflow_backend.models.user")
    fake_user_module.UserModel = FakeUserModel
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user", fake_user_module)
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.filter_users_for_current_tenant",
        lambda users, tenant_id=None: list(users),
    )
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._organization_id_for_tenant",
        lambda tenant_id=None: "org-uuid-123",
    )
    fake_keycloak_service = ModuleType("m8flow_backend.services.keycloak_service")
    fake_keycloak_service.search_organization_members = lambda organization_id, search, exact=False: [
        {"id": "user-2", "username": "editorial"},
        {"id": "user-3", "username": "reviewer"},
    ]
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.keycloak_service", fake_keycloak_service)
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._upsert_local_shared_realm_member",
        lambda member: provisioned_user if member.get("username") == "editorial" else None,
    )

    users = find_users_for_current_tenant_by_username_prefix("edit")

    assert [user.username for user in users] == ["editor", "editorial"]


def test_organization_id_for_tenant_prefers_canonical_tenant_id(monkeypatch) -> None:
    from m8flow_backend.services import tenant_identity_helpers as helpers

    fake_keycloak_service = ModuleType("m8flow_backend.services.keycloak_service")
    fake_keycloak_service.get_organization_by_id = (
        lambda organization_id, admin_token=None: {"id": "org-uuid", "alias": "tenant-slug"}
        if organization_id == "tenant-uuid"
        else None
    )
    fake_keycloak_service.get_organization_by_alias = (
        lambda alias, admin_token=None: {"id": "org-legacy", "alias": alias} if alias == "tenant-slug" else None
    )
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.keycloak_service", fake_keycloak_service)
    monkeypatch.setattr(helpers, "_tenant_slug_for_identifier", lambda tenant_identifier: "tenant-slug")
    monkeypatch.setattr(helpers, "current_tenant_id_or_none", lambda: "tenant-uuid")

    assert helpers._organization_id_for_tenant() == "org-uuid"


def test_current_tenant_id_or_none_ignores_default_and_public_context() -> None:
    default_token = set_context_tenant_id("default")
    public_token = None
    try:
        assert current_tenant_id_or_none() is None
        public_token = set_context_tenant_id("public")
        assert current_tenant_id_or_none() is None
    finally:
        if public_token is not None:
            reset_context_tenant_id(public_token)
        reset_context_tenant_id(default_token)


def test_current_tenant_id_or_none_prefers_real_request_tenant() -> None:
    app = Flask(__name__)

    with app.test_request_context("/v1.0/tasks"):
        from flask import g

        g.m8flow_tenant_id = "tenant-real-id"
        assert current_tenant_id_or_none() == "tenant-real-id"


def test_upsert_local_shared_realm_member_reuses_existing_shared_realm_user(monkeypatch) -> None:
    from m8flow_backend.services import tenant_identity_helpers as helpers

    existing_user = SimpleNamespace(
        id=7,
        username="admin",
        service="http://localhost:7002/realms/m8flow",
        service_id="legacy-member-id",
        email="old@example.com",
        display_name="Old Admin",
        updated_at_in_seconds=10,
        created_at_in_seconds=5,
    )
    fake_query = SimpleNamespace(
        filter=lambda *_args, **_kwargs: fake_query,
        first=lambda: None,
        all=lambda: [existing_user],
    )
    fake_user_module = ModuleType("spiffworkflow_backend.models.user")
    fake_user_module.UserModel = SimpleNamespace(query=fake_query, service=object(), service_id=object(), username=object())

    add_calls: list[Any] = []
    commit_calls: list[int] = []
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = SimpleNamespace(
        session=SimpleNamespace(
            add=lambda user: add_calls.append(user),
            commit=lambda: commit_calls.append(1),
            rollback=lambda: None,
        )
    )

    create_user_calls: list[tuple[Any, ...]] = []
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_user_service_module.UserService = SimpleNamespace(
        create_user=lambda *args, **kwargs: create_user_calls.append((args, kwargs))
    )

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user", fake_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setattr(
        helpers,
        "_shared_realm_service_issuer",
        lambda: "http://localhost:7002/realms/m8flow",
    )

    result = helpers._upsert_local_shared_realm_member(
        {
            "id": "member-1",
            "username": "admin",
            "email": "admin@example.com",
            "firstName": "Admin",
            "lastName": "User",
        }
    )

    assert result is existing_user
    assert existing_user.service_id == "member-1"
    assert existing_user.email == "admin@example.com"
    assert existing_user.display_name == "Admin User"
    assert len(add_calls) == 1
    assert len(commit_calls) == 1
    assert create_user_calls == []


def test_upsert_local_shared_realm_member_reuses_existing_user_even_if_realm_metadata_is_stale(
    monkeypatch,
) -> None:
    from m8flow_backend.services import tenant_identity_helpers as helpers

    existing_user = SimpleNamespace(
        id=7,
        username="admin",
        service="http://localhost:7002/realms/master",
        service_id="legacy-member-id",
        email="old@example.com",
        display_name="Old Admin",
        updated_at_in_seconds=10,
        created_at_in_seconds=5,
    )
    fake_query = SimpleNamespace(
        filter=lambda *_args, **_kwargs: fake_query,
        first=lambda: None,
        all=lambda: [existing_user],
    )
    fake_user_module = ModuleType("spiffworkflow_backend.models.user")
    fake_user_module.UserModel = SimpleNamespace(query=fake_query, service=object(), service_id=object(), username=object())

    add_calls: list[Any] = []
    commit_calls: list[int] = []
    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = SimpleNamespace(
        session=SimpleNamespace(
            add=lambda user: add_calls.append(user),
            commit=lambda: commit_calls.append(1),
            rollback=lambda: None,
        )
    )

    create_user_calls: list[tuple[Any, ...]] = []
    fake_user_service_module = ModuleType("spiffworkflow_backend.services.user_service")
    fake_user_service_module.UserService = SimpleNamespace(
        create_user=lambda *args, **kwargs: create_user_calls.append((args, kwargs))
    )

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.user", fake_user_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.user_service", fake_user_service_module)
    monkeypatch.setattr(
        helpers,
        "_shared_realm_service_issuer",
        lambda: "http://localhost:7002/realms/m8flow",
    )

    result = helpers._upsert_local_shared_realm_member(
        {
            "id": "member-1",
            "username": "admin",
            "email": "admin@example.com",
            "firstName": "Admin",
            "lastName": "User",
        }
    )

    assert result is existing_user
    assert existing_user.service == "http://localhost:7002/realms/m8flow"
    assert existing_user.service_id == "member-1"
    assert existing_user.email == "admin@example.com"
    assert existing_user.display_name == "Admin User"
    assert len(add_calls) == 1
    assert len(commit_calls) == 1
    assert create_user_calls == []


def test_resolve_user_for_current_tenant_prefers_unique_exact_username_match(monkeypatch) -> None:
    alice = SimpleNamespace(username="alice", email="alice@example.com")
    duplicate = SimpleNamespace(username="alice", email="other@example.com")

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_identifier",
        lambda username_or_email, tenant_id=None: [alice, duplicate] if username_or_email == "alice" else [],
    )

    assert resolve_user_for_current_tenant("alice") is None

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_identifier",
        lambda username, tenant_id=None: [alice] if username == "alice@example.com" else [],
    )

    assert resolve_user_for_current_tenant("alice@example.com") is None


def test_tenant_claim_helpers_use_built_in_organization_claim_when_present() -> None:
    payload = {
        "m8flow_tenant_id": "legacy-realm-id",
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
            }
        }
    }

    assert tenant_id_from_payload(payload) == "tenant-a-id"
    assert tenant_alias_from_payload(payload) == "tenant-a"


def test_tenant_claim_helpers_support_list_form_organization_claim() -> None:
    payload = {
        "organization": ["tenant-a"],
    }

    assert organization_memberships_from_payload(payload) == [("tenant-a", {})]
    assert single_organization_from_payload(payload) == ("tenant-a", {})
    assert tenant_id_from_payload(payload) == "tenant-a"
    assert tenant_alias_from_payload(payload) == "tenant-a"


def test_active_organization_from_payload_selects_current_tenant_from_multi_org_payload(monkeypatch) -> None:
    payload = {
        "organization": {
            "tenant-a": {"id": "tenant-a-id", "groups": ["/editor"]},
            "tenant-b": {"id": "tenant-b-id", "groups": ["/reviewer"]},
        }
    }

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-b-id", "tenant-b"},
    )

    assert active_organization_from_payload(payload, tenant_id="tenant-b-id") == (
        "tenant-b",
        {"id": "tenant-b-id", "groups": ["/reviewer"]},
    )


def test_organization_group_identifiers_from_payload_normalizes_active_org_groups(monkeypatch) -> None:
    payload = {
        "organization": {
            "tenant-a": {
                "id": "tenant-a-id",
                "groups": ["/editor", "/review/reviewer", "/editor/", "", None],
            }
        }
    }

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_identifiers",
        lambda tenant_id=None: {"tenant-a-id", "tenant-a"},
    )

    assert organization_group_identifiers_from_payload(payload, tenant_id="tenant-a-id") == [
        "editor",
        "reviewer",
    ]


def test_tenant_claim_helpers_map_org_uuid_to_local_tenant_id(monkeypatch) -> None:
    payload = {
        "organization": {
            "m8flow": {
                "id": "370465d2-9b78-4c8b-9d82-c9a4818b747f",
            }
        }
    }

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._canonical_tenant_id_from_identifiers",
        lambda *identifiers: "m8flow" if "m8flow" in identifiers else None,
    )

    assert tenant_id_from_payload(payload) == "m8flow"


def test_tenant_claim_helpers_fail_closed_for_ambiguous_multi_org_payload() -> None:
    payload = {
        "organization": {
            "tenant-a": {"id": "tenant-a-id"},
            "tenant-b": {"id": "tenant-b-id"},
        }
    }

    assert organization_memberships_from_payload(payload) == [
        ("tenant-a", {"id": "tenant-a-id"}),
        ("tenant-b", {"id": "tenant-b-id"}),
    ]
    assert single_organization_from_payload(payload) is None
    assert tenant_id_from_payload(payload) is None
    assert tenant_alias_from_payload(payload) is None


def test_tenant_claim_helpers_fail_closed_for_ambiguous_multi_org_list_payload() -> None:
    payload = {
        "organization": ["tenant-a", "tenant-b"],
    }

    assert organization_memberships_from_payload(payload) == [
        ("tenant-a", {}),
        ("tenant-b", {}),
    ]
    assert single_organization_from_payload(payload) is None
    assert tenant_id_from_payload(payload) is None
    assert tenant_alias_from_payload(payload) is None


def test_authentication_identifier_prefers_explicit_claims_over_legacy_tenant_name() -> None:
    payload = {
        "m8flow_authentication_identifier": "shared-users",
        "m8flow_realm_name": "shared-users",
        "m8flow_tenant_name": "Tenant A",
        "realm_name": "legacy-realm",
    }

    assert authentication_identifier_from_payload(payload) == "shared-users"
