from __future__ import annotations

from types import SimpleNamespace

from spiffworkflow_backend.services import user_service

import m8flow_backend.services.user_service_patch as user_service_patch


def _user_service_originals() -> dict[str, object]:
    return {
        "find_or_create_group": user_service.UserService.find_or_create_group,
        "add_user_to_group_or_add_to_waiting": user_service.UserService.add_user_to_group_or_add_to_waiting,
        "apply_waiting_group_assignments": user_service.UserService.apply_waiting_group_assignments,
        "add_user_to_group": user_service.UserService.add_user_to_group,
        "update_human_task_assignments_for_user": user_service.UserService.update_human_task_assignments_for_user,
        "add_waiting_group_assignment": user_service.UserService.add_waiting_group_assignment,
    }


def _restore_user_service(originals: dict[str, object], monkeypatch) -> None:
    for name, value in originals.items():
        monkeypatch.setattr(user_service.UserService, name, value)
    monkeypatch.setattr(user_service_patch, "_PATCHED", False)


def test_apply_patches_find_or_create_group_with_qualified_identifier(
    monkeypatch,
) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = (
        user_service.UserService.add_user_to_group_or_add_to_waiting
    )
    original_apply_waiting_group_assignments = (
        user_service.UserService.apply_waiting_group_assignments
    )

    captured: dict[str, object] = {}

    @classmethod
    def fake_original_find_or_create_group(
        cls, group_identifier: str, source_is_open_id: bool = False
    ):
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
        group = user_service.UserService.find_or_create_group(
            "reviewer", source_is_open_id=True
        )
    finally:
        monkeypatch.setattr(
            user_service.UserService,
            "find_or_create_group",
            original_find_or_create_group,
        )
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


def test_apply_patches_find_or_create_group_normalizes_open_id_org_group_paths(
    monkeypatch,
) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = (
        user_service.UserService.add_user_to_group_or_add_to_waiting
    )
    original_apply_waiting_group_assignments = (
        user_service.UserService.apply_waiting_group_assignments
    )

    captured: dict[str, object] = {}

    @classmethod
    def fake_original_find_or_create_group(
        cls, group_identifier: str, source_is_open_id: bool = False
    ):
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
        "normalize_organizational_group_identifier",
        lambda group_identifier: (
            "tenant-a:/Engineering"
            if group_identifier == "tenant-a:/Engineering/"
            else group_identifier
        ),
    )
    monkeypatch.setattr(
        user_service_patch,
        "qualify_group_identifier",
        lambda group_identifier: (
            f"tenant-a:{group_identifier}"
            if ":" not in group_identifier
            else group_identifier
        ),
    )

    try:
        user_service_patch.apply()
        group = user_service.UserService.find_or_create_group(
            "tenant-a:/Engineering/", source_is_open_id=True
        )
    finally:
        monkeypatch.setattr(
            user_service.UserService,
            "find_or_create_group",
            original_find_or_create_group,
        )
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

    assert captured["group_identifier"] == "tenant-a:/Engineering"
    assert captured["source_is_open_id"] is True
    assert group.identifier == "tenant-a:/Engineering"


def test_add_user_to_group_or_add_to_waiting_returns_users_from_tenant_scoped_resolver(
    monkeypatch,
) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = (
        user_service.UserService.add_user_to_group_or_add_to_waiting
    )
    original_apply_waiting_group_assignments = (
        user_service.UserService.apply_waiting_group_assignments
    )
    original_add_user_to_group = user_service.UserService.add_user_to_group

    fake_group = SimpleNamespace(identifier="tenant-a:reviewer")
    alice = SimpleNamespace(username="alice")
    bob = SimpleNamespace(username="bob")
    added = []

    @classmethod
    def fake_find_or_create_group(
        cls, group_identifier: str, source_is_open_id: bool = False
    ):
        return fake_group

    @classmethod
    def fake_add_user_to_group(cls, user, group):
        added.append((user.username, group.identifier))

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        user_service_patch,
        "find_users_for_current_tenant_by_identifier",
        lambda username: [alice, bob] if username == "alice" else [],
    )
    monkeypatch.setattr(
        user_service.UserService, "find_or_create_group", fake_find_or_create_group
    )
    monkeypatch.setattr(
        user_service.UserService, "add_user_to_group", fake_add_user_to_group
    )

    try:
        user_service_patch.apply()
        result = user_service.UserService.add_user_to_group_or_add_to_waiting(
            "alice",
            "reviewer",
        )
    finally:
        monkeypatch.setattr(
            user_service.UserService,
            "find_or_create_group",
            original_find_or_create_group,
        )
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
        monkeypatch.setattr(
            user_service.UserService, "add_user_to_group", original_add_user_to_group
        )
        monkeypatch.setattr(user_service_patch, "_PATCHED", False)

    assert result == (
        None,
        [
            {"username": "alice", "group_identifier": "tenant-a:reviewer"},
            {"username": "bob", "group_identifier": "tenant-a:reviewer"},
        ],
    )
    assert added == [("alice", "tenant-a:reviewer"), ("bob", "tenant-a:reviewer")]


def test_apply_waiting_group_assignments_only_applies_current_tenant_groups(
    monkeypatch,
) -> None:
    original_find_or_create_group = user_service.UserService.find_or_create_group
    original_add_user_to_group_or_add_to_waiting = (
        user_service.UserService.add_user_to_group_or_add_to_waiting
    )
    original_apply_waiting_group_assignments = (
        user_service.UserService.apply_waiting_group_assignments
    )
    original_add_user_to_group = user_service.UserService.add_user_to_group

    exact_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-a:reviewer")
    )
    other_tenant_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-b:reviewer")
    )
    wildcard_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-a:admin"),
        pattern_from_wildcard_username=lambda: r"^ali.*",
    )
    email_only_wildcard_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-a:viewer"),
        pattern_from_wildcard_username=lambda: r".*@example\.com$",
    )
    query_results = [
        [exact_assignment, other_tenant_assignment],
        [wildcard_assignment, email_only_wildcard_assignment],
    ]

    captured_usernames: list[list[str | None]] = []

    class FakeField:
        def in_(self, values):
            captured_usernames.append(list(values))
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
    def fake_find_or_create_group(
        cls, group_identifier: str, source_is_open_id: bool = False
    ):
        return SimpleNamespace(identifier=group_identifier)

    @classmethod
    def fake_add_user_to_group(cls, target_user, group):
        added.append((target_user.username, group.identifier))

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        user_service_patch, "current_tenant_identifiers", lambda: {"tenant-a"}
    )
    monkeypatch.setattr(
        user_service.UserGroupAssignmentWaitingModel, "username", FakeField()
    )
    monkeypatch.setattr(
        user_service, "UserGroupAssignmentWaitingModel", FakeWaitingModel
    )
    monkeypatch.setattr(
        user_service.UserService, "find_or_create_group", fake_find_or_create_group
    )
    monkeypatch.setattr(
        user_service.UserService, "add_user_to_group", fake_add_user_to_group
    )
    monkeypatch.setattr(
        user_service_patch.db.session,
        "delete",
        lambda assignment: deleted.append(assignment),
    )
    monkeypatch.setattr(
        user_service_patch.db.session, "commit", lambda: committed.append(True)
    )

    try:
        user_service_patch.apply()
        user_service.UserService.apply_waiting_group_assignments(user)
    finally:
        monkeypatch.setattr(
            user_service.UserService,
            "find_or_create_group",
            original_find_or_create_group,
        )
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
        monkeypatch.setattr(
            user_service.UserService, "add_user_to_group", original_add_user_to_group
        )
        monkeypatch.setattr(user_service_patch, "_PATCHED", False)

    assert added == [
        ("alice", "tenant-a:reviewer"),
        ("alice", "tenant-a:admin"),
    ]
    assert deleted == [exact_assignment]
    assert committed == [True]
    assert captured_usernames == [["alice"]]


def test_add_user_to_group_or_add_to_waiting_parks_assignment_when_no_local_user(
    monkeypatch,
) -> None:
    originals = _user_service_originals()
    fake_group = SimpleNamespace(identifier="tenant-a:reviewer")
    waiting_calls: list[tuple[str, object]] = []

    @classmethod
    def fake_find_or_create_group(
        cls, group_identifier: str, source_is_open_id: bool = False
    ):
        return fake_group

    @classmethod
    def fake_add_waiting_group_assignment(cls, username: str, group):
        waiting_calls.append((username, group.identifier))
        return ("waiting", username)

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        user_service_patch,
        "find_users_for_current_tenant_by_identifier",
        lambda username: [],
    )
    monkeypatch.setattr(
        user_service.UserService, "find_or_create_group", fake_find_or_create_group
    )
    monkeypatch.setattr(
        user_service.UserService,
        "add_waiting_group_assignment",
        fake_add_waiting_group_assignment,
    )

    try:
        user_service_patch.apply()
        result = user_service.UserService.add_user_to_group_or_add_to_waiting(
            "alice", "reviewer"
        )
    finally:
        _restore_user_service(originals, monkeypatch)

    assert result == ("waiting", "alice")
    assert waiting_calls == [("alice", "tenant-a:reviewer")]


def test_apply_waiting_group_assignments_applies_all_when_no_tenant_scope(
    monkeypatch,
) -> None:
    originals = _user_service_originals()
    exact_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-a:reviewer")
    )
    other_tenant_assignment = SimpleNamespace(
        group=SimpleNamespace(identifier="tenant-b:reviewer")
    )
    query_results = [[exact_assignment, other_tenant_assignment], []]

    class FakeField:
        def in_(self, values):
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

    @classmethod
    def fake_add_user_to_group(cls, target_user, group):
        added.append((target_user.username, group.identifier))

    user = SimpleNamespace(username="alice")
    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(user_service_patch, "current_tenant_identifiers", lambda: set())
    monkeypatch.setattr(
        user_service.UserGroupAssignmentWaitingModel, "username", FakeField()
    )
    monkeypatch.setattr(
        user_service, "UserGroupAssignmentWaitingModel", FakeWaitingModel
    )
    monkeypatch.setattr(
        user_service.UserService, "add_user_to_group", fake_add_user_to_group
    )
    monkeypatch.setattr(
        user_service_patch.db.session,
        "delete",
        lambda assignment: deleted.append(assignment),
    )
    monkeypatch.setattr(user_service_patch.db.session, "commit", lambda: None)

    try:
        user_service_patch.apply()
        user_service.UserService.apply_waiting_group_assignments(user)
    finally:
        _restore_user_service(originals, monkeypatch)

    assert added == [("alice", "tenant-a:reviewer"), ("alice", "tenant-b:reviewer")]
    assert deleted == [exact_assignment, other_tenant_assignment]


def test_update_human_task_assignments_copies_tenant_id_skips_duplicates_and_scopes_delete(
    monkeypatch,
) -> None:
    from contextlib import nullcontext

    from m8flow_backend.models.human_task_user import HumanTaskUserAddedBy

    originals = _user_service_originals()
    added: list[object] = []
    deleted: list[object] = []
    htu_filter_batches: list[tuple] = []

    existing_assignment = SimpleNamespace(human_task_id=1)
    already_assigned_task = SimpleNamespace(id=1, m8f_tenant_id="tenant-a")
    new_task = SimpleNamespace(id=2, m8f_tenant_id="tenant-a")
    row_to_delete = SimpleNamespace(id="delete-me")

    class TenantColumn:
        def __eq__(self, other):
            return ("m8f_tenant_id", other)

    class HumanTaskUserQuery:
        def __init__(self) -> None:
            self.phase = 0

        def filter(self, *args, **_kwargs):
            htu_filter_batches.append(args)
            return self

        def join(self, *_args, **_kwargs):
            return self

        def all(self):
            self.phase += 1
            if self.phase == 1:
                return [existing_assignment]
            return [row_to_delete]

    class HumanTaskQuery:
        def outerjoin(self, *_args, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def distinct(self, *_args, **_kwargs):
            return self

        def all(self):
            return [already_assigned_task, new_task]

    class FakeHumanTaskUserModel:
        query = HumanTaskUserQuery()
        m8f_tenant_id = TenantColumn()
        user_id = SimpleNamespace()
        added_by = SimpleNamespace()

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeHumanTaskModel:
        query = HumanTaskQuery()
        m8f_tenant_id = TenantColumn()
        id = SimpleNamespace()
        lane_assignment_id = SimpleNamespace(in_=lambda values: values)
        completed = False

    class FakeSession:
        no_autoflush = nullcontext()

        def add(self, obj):
            added.append(obj)

        def delete(self, obj):
            deleted.append(obj)

        def commit(self):
            return None

    monkeypatch.setattr(user_service_patch, "_PATCHED", False)
    monkeypatch.setattr(
        "m8flow_backend.models.human_task_user.HumanTaskUserModel",
        FakeHumanTaskUserModel,
    )
    monkeypatch.setattr(
        "m8flow_backend.models.human_task.HumanTaskModel", FakeHumanTaskModel
    )
    monkeypatch.setattr(user_service_patch.db, "session", FakeSession())

    try:
        user_service_patch.apply()
        user_service.UserService.update_human_task_assignments_for_user(
            SimpleNamespace(id=9),
            {10},
            {11},
        )
    finally:
        _restore_user_service(originals, monkeypatch)

    assert len(added) == 1
    assert added[0].user_id == 9
    assert added[0].human_task_id == 2
    assert added[0].m8f_tenant_id == "tenant-a"
    assert added[0].added_by == HumanTaskUserAddedBy.lane_assignment.value
    assert deleted == [row_to_delete]
    delete_filters = htu_filter_batches[-1]
    assert any("m8f_tenant_id" in str(expr) for expr in delete_filters)
