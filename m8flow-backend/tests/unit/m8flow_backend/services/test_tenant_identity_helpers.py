from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.services.tenant_identity_helpers import filter_users_for_current_tenant
from m8flow_backend.services.tenant_identity_helpers import organization_memberships_from_payload
from m8flow_backend.services.tenant_identity_helpers import find_users_for_current_tenant_by_identifier
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import resolve_user_for_current_tenant
from m8flow_backend.services.tenant_identity_helpers import authentication_identifier_from_payload
from m8flow_backend.services.tenant_identity_helpers import single_organization_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_alias_from_payload
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from m8flow_backend.services.tenant_identity_helpers import user_belongs_to_current_tenant


def test_qualify_group_identifier_qualifies_bare_and_preserves_qualified(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        lambda: "tenant-a",
    )

    assert qualify_group_identifier("reviewer") == "tenant-a:reviewer"
    assert qualify_group_identifier("tenant-b:admin") == "tenant-b:admin"


def test_display_group_identifier_rewrites_tenant_prefix_to_slug(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers._tenant_slug_for_identifier",
        lambda tenant_identifier: "tenant-slug" if tenant_identifier == "tenant-id" else None,
    )

    assert display_group_identifier("tenant-id:reviewer") == "tenant-slug:reviewer"


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
