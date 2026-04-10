from __future__ import annotations

from types import SimpleNamespace

from m8flow_backend.services.tenant_identity_helpers import filter_users_for_current_tenant
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import resolve_user_for_current_tenant


def test_qualify_group_identifier_qualifies_bare_and_preserves_qualified(monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.current_tenant_id_or_none",
        lambda: "tenant-a",
    )

    assert qualify_group_identifier("reviewer") == "tenant-a:reviewer"
    assert qualify_group_identifier("tenant-b:admin") == "tenant-b:admin"


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


def test_resolve_user_for_current_tenant_prefers_unique_exact_match(monkeypatch) -> None:
    alice = SimpleNamespace(username="alice", email="alice@example.com")
    duplicate = SimpleNamespace(username="alice", email="other@example.com")

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_identifier",
        lambda username_or_email, tenant_id=None: [alice, duplicate] if username_or_email == "alice" else [],
    )

    assert resolve_user_for_current_tenant("alice") is None

    monkeypatch.setattr(
        "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_identifier",
        lambda username_or_email, tenant_id=None: [alice] if username_or_email == "alice@example.com" else [],
    )

    assert resolve_user_for_current_tenant("alice@example.com") is alice
