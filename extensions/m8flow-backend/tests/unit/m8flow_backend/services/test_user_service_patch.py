from __future__ import annotations

from types import SimpleNamespace

from spiffworkflow_backend.services import user_service

import m8flow_backend.services.user_service_patch as user_service_patch


def test_apply_patches_find_or_create_group_with_qualified_identifier(monkeypatch) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = user_service.UserService.add_user_to_group_or_add_to_waiting
    original_apply_waiting_group_assignments = user_service.UserService.apply_waiting_group_assignments

    captured: dict[str, object] = {}

    @classmethod
    def fake_original_find_or_create_group(cls, group_identifier: str, source_is_open_id: bool = False):
        captured["group_identifier"] = group_identifier
        captured["source_is_open_id"] = source_is_open_id
        return SimpleNamespace(identifier=group_identifier)

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        user_service.UserService,
        "find_or_create_group",
        fake_original_find_or_create_group,
    )
    monkeypatch.setattr(
        user_service_patch,
        "qualify_group_identifier",
        lambda group_identifier: f"tenant-a:{group_identifier}",
    )

    try:
        user_service_patch.apply()
        group = user_service.UserService.find_or_create_group("reviewer", source_is_open_id=True)
    finally:
        monkeypatch.setattr(user_service.UserService, "find_or_create_group", original_find_or_create_group)
        monkeypatch.setattr(
            user_service.UserService,
            "add_user_to_group_or_add_to_waiting",
            original_add_user_to_group_or_add_to_waiting,
        )
        monkeypatch.setattr(
            user_service.UserService,
            "apply_waiting_group_assignments",
            original_apply_waiting_group_assignments,
        )
        monkeypatch.setattr(user_service_patch, "_PATCHED", False)

    assert captured["group_identifier"] == "tenant-a:reviewer"
    assert captured["source_is_open_id"] is True
    assert group.identifier == "tenant-a:reviewer"


def test_add_user_to_group_or_add_to_waiting_returns_users_from_tenant_scoped_resolver(monkeypatch) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = user_service.UserService.add_user_to_group_or_add_to_waiting
    original_apply_waiting_group_assignments = user_service.UserService.apply_waiting_group_assignments
    original_add_user_to_group = user_service.UserService.add_user_to_group

    fake_group = SimpleNamespace(identifier="tenant-a:reviewer")
    alice = SimpleNamespace(username="alice")
    bob = SimpleNamespace(username="bob")
    added = []

    @classmethod
    def fake_find_or_create_group(cls, group_identifier: str, source_is_open_id: bool = False):
        return fake_group

    @classmethod
    def fake_add_user_to_group(cls, user, group):
        added.append((user.username, group.identifier))

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        user_service_patch,
        "find_users_for_current_tenant_by_identifier",
        lambda username_or_email: [alice, bob] if username_or_email == "alice@example.com" else [],
    )
    monkeypatch.setattr(user_service.UserService, "find_or_create_group", fake_find_or_create_group)
    monkeypatch.setattr(user_service.UserService, "add_user_to_group", fake_add_user_to_group)

    try:
        user_service_patch.apply()
        result = user_service.UserService.add_user_to_group_or_add_to_waiting(
            "alice@example.com",
            "reviewer",
        )
    finally:
        monkeypatch.setattr(user_service.UserService, "find_or_create_group", original_find_or_create_group)
        monkeypatch.setattr(
            user_service.UserService,
            "add_user_to_group_or_add_to_waiting",
            original_add_user_to_group_or_add_to_waiting,
        )
        monkeypatch.setattr(
            user_service.UserService,
            "apply_waiting_group_assignments",
            original_apply_waiting_group_assignments,
        )
        monkeypatch.setattr(user_service.UserService, "add_user_to_group", original_add_user_to_group)
        monkeypatch.setattr(user_service_patch, "_PATCHED", False)

    assert result == (
        None,
        [
            {"username": "alice", "group_identifier": "tenant-a:reviewer"},
            {"username": "bob", "group_identifier": "tenant-a:reviewer"},
        ],
    )
    assert added == [("alice", "tenant-a:reviewer"), ("bob", "tenant-a:reviewer")]


def test_apply_waiting_group_assignments_only_applies_current_tenant_groups(monkeypatch) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = user_service.UserService.add_user_to_group_or_add_to_waiting
    original_apply_waiting_group_assignments = user_service.UserService.apply_waiting_group_assignments
    original_add_user_to_group = user_service.UserService.add_user_to_group

    exact_assignment = SimpleNamespace(group=SimpleNamespace(identifier="tenant-a:reviewer"))
    other_tenant_assignment = SimpleNamespace(group=SimpleNamespace(identifier="tenant-b:reviewer"))
    wildcard_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-a:admin"),
        pattern_from_wildcard_username=lambda: r"^ali.*",
    )
    query_results = [
        [exact_assignment, other_tenant_assignment],
        [wildcard_assignment],
    ]

    class FakeField:
        def in_(self, _values):
            return self

        def regexp_match(self, _pattern):
            return self

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return query_results.pop(0)

    class FakeWaitingModel:
        username = FakeField()

        def __init__(self):
            self.query = FakeQuery()

    added = []
    deleted = []
    committed = []
    user = SimpleNamespace(username="alice", email="alice@example.com")

    @classmethod
    def fake_find_or_create_group(cls, group_identifier: str, source_is_open_id: bool = False):
        return SimpleNamespace(identifier=group_identifier)

    @classmethod
    def fake_add_user_to_group(cls, target_user, group):
        added.append((target_user.username, group.identifier))

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(user_service_patch, "current_tenant_identifiers", lambda: {"tenant-a"})
    monkeypatch.setattr(user_service.UserGroupAssignmentWaitingModel, "username", FakeField())
    monkeypatch.setattr(user_service, "UserGroupAssignmentWaitingModel", FakeWaitingModel)
    monkeypatch.setattr(user_service.UserService, "find_or_create_group", fake_find_or_create_group)
    monkeypatch.setattr(user_service.UserService, "add_user_to_group", fake_add_user_to_group)
    monkeypatch.setattr(user_service_patch.db.session, "delete", lambda assignment: deleted.append(assignment))
    monkeypatch.setattr(user_service_patch.db.session, "commit", lambda: committed.append(True))

    try:
        user_service_patch.apply()
        user_service.UserService.apply_waiting_group_assignments(user)
    finally:
        monkeypatch.setattr(user_service.UserService, "find_or_create_group", original_find_or_create_group)
        monkeypatch.setattr(
            user_service.UserService,
            "add_user_to_group_or_add_to_waiting",
            original_add_user_to_group_or_add_to_waiting,
        )
        monkeypatch.setattr(
            user_service.UserService,
            "apply_waiting_group_assignments",
            original_apply_waiting_group_assignments,
        )
        monkeypatch.setattr(user_service.UserService, "add_user_to_group", original_add_user_to_group)
        monkeypatch.setattr(user_service_patch, "_PATCHED", False)

    assert added == [
        ("alice", "tenant-a:reviewer"),
        ("alice", "tenant-a:admin"),
    ]
    assert deleted == [exact_assignment]
    assert committed == [True]
