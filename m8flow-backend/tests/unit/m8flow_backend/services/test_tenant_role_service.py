from types import SimpleNamespace

import pytest
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.services import tenant_role_service


def _stub_create_group_dependencies(monkeypatch, *, existing_group_names=None):
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id, admin_token=None: (
            SimpleNamespace(id=tenant_id, slug="tenant-slug"),
            {"id": "org-1"},
            "org-1",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_name_lookup",
        lambda _organization_id, groups=None: {
            name.casefold(): name for name in (existing_group_names or [])
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda _organization_id, _group_id, admin_token=None: [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_group_by_id",
        lambda _organization_id, _group_id, admin_token=None: None,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda _group: [],
    )


def test_create_tenant_group_normalizes_whitespace_before_creation(monkeypatch):
    _stub_create_group_dependencies(monkeypatch)
    created_group_names: list[str] = []

    monkeypatch.setattr(
        tenant_role_service,
        "create_organization_group",
        lambda _organization_id, group_name: created_group_names.append(group_name)
        or {
            "id": "group-1",
            "name": group_name,
            "path": f"/{group_name}",
        },
    )

    created_group = tenant_role_service.create_tenant_group(
        "tenant-1",
        "  QA   Reviewers  ",
    )

    assert created_group_names == ["QA Reviewers"]
    assert created_group["name"] == "QA Reviewers"


def test_create_tenant_group_rejects_special_characters():
    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "Bad %#@! group")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_group"
    assert (
        exc_info.value.message
        == "Group name can only contain letters, numbers, spaces, hyphens, and "
        "underscores, and must start and end with a letter or number."
    )


def test_create_tenant_group_rejects_overly_long_name():
    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "a" * 65)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_group"
    assert exc_info.value.message == "Group name must be 64 characters or fewer."


def test_create_tenant_group_detects_duplicate_after_normalization(monkeypatch):
    _stub_create_group_dependencies(
        monkeypatch,
        existing_group_names=["QA   Reviewers"],
    )

    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "  qa reviewers  ")

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "group_exists"
    assert (
        exc_info.value.message
        == "Group 'qa reviewers' already exists in the tenant organization."
    )


def test_list_tenant_members_with_roles_reuses_one_admin_token(monkeypatch):
    admin_token_calls: list[str] = []
    list_groups_calls: list[tuple[str, str | None, bool]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "get_master_admin_token",
        lambda: admin_token_calls.append("called") or "token-1",
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id, admin_token=None: (
            SimpleNamespace(id=tenant_id, slug="tenant-slug"),
            {"id": "org-1"},
            "org-1",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id, admin_token=None, brief_representation=True: list_groups_calls.append(
            (organization_id, admin_token, brief_representation)
        )
        or [
            {
                "id": "group-1",
                "name": "Administrators",
                "attributes": {},
            }
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda _group: ["tenant-admin"],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_group_by_id",
        lambda *_args, **_kwargs: pytest.fail(
            "full group list should avoid extra group-by-id lookups"
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "search_organization_members",
        lambda organization_id, search, *, exact=False, admin_token=None, max_results=100, first_result=0: [
            {
                "id": "member-1",
                "username": "admin",
                "email": "admin@example.com",
            }
        ]
        if organization_id == "org-1"
        and search == "admin"
        and exact is False
        and admin_token == "token-1"
        and max_results == 100
        and first_result == 10
        else pytest.fail("unexpected organization member search arguments"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_groups",
        lambda organization_id, member_id, admin_token=None: [
            {"id": "group-1", "name": "Administrators"}
        ]
        if organization_id == "org-1"
        and member_id == "member-1"
        and admin_token == "token-1"
        else pytest.fail("unexpected organization member-groups arguments"),
    )

    members = tenant_role_service.list_tenant_members_with_roles(
        "tenant-1",
        search="admin",
        offset=10,
    )

    assert admin_token_calls == ["called"]
    assert list_groups_calls == [("org-1", "token-1", False)]
    assert members == [
        {
            "id": "member-1",
            "username": "admin",
            "email": "admin@example.com",
            "display_name": None,
            "roles": ["tenant-admin"],
        }
    ]


def test_list_available_tenant_users_filters_existing_members_and_applies_paging(monkeypatch):
    admin_token_calls: list[str] = []
    realm_search_calls: list[tuple[str, str, int, int, str | None]] = []
    membership_lookup_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "get_master_admin_token",
        lambda: admin_token_calls.append("called") or "token-1",
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id, admin_token=None: (
            SimpleNamespace(id=tenant_id, slug="tenant-slug"),
            {"id": "org-1"},
            "org-1",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "search_realm_users",
        lambda realm, search, *, exact=False, admin_token=None, max_results=100, first_result=0: realm_search_calls.append(
            (realm, search, max_results, first_result, admin_token)
        )
        or (
            [
                {"id": "user-1", "username": "admin", "email": "admin@example.com"},
                {"id": "user-2", "username": "editor", "email": "editor@example.com"},
                {"id": "user-3", "username": "reviewer", "email": "reviewer@example.com"},
                *[
                    {
                        "id": f"user-{index}",
                        "username": f"member-{index}",
                        "email": f"member-{index}@example.com",
                    }
                    for index in range(4, 26)
                ],
            ]
            if first_result == 0
            else [
                {"id": "user-4", "username": "viewer", "email": "viewer@example.com"},
                {"id": "user-5", "username": "writer", "email": "writer@example.com"},
                {"id": "user-6", "username": "worker", "email": "worker@example.com"},
            ]
            if first_result == 25
            else []
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_member_by_username",
        lambda organization_id, username, admin_token=None: membership_lookup_calls.append(
            (organization_id, username, admin_token)
        )
        or (
            {"id": f"member-{username}", "username": username}
            if username in {"admin", "reviewer"} or username.startswith("member-")
            else None
        ),
    )

    available_users = tenant_role_service.list_available_tenant_users(
        "tenant-1",
        search="er",
        offset=1,
        max_results=3,
    )

    assert admin_token_calls == ["called"]
    assert realm_search_calls == [
        (tenant_role_service.shared_realm_name(), "er", 25, 0, "token-1"),
        (tenant_role_service.shared_realm_name(), "er", 25, 25, "token-1"),
    ]
    assert len(membership_lookup_calls) == 28
    assert {
        ("org-1", "admin", "token-1"),
        ("org-1", "editor", "token-1"),
        ("org-1", "reviewer", "token-1"),
        ("org-1", "viewer", "token-1"),
        ("org-1", "worker", "token-1"),
        ("org-1", "writer", "token-1"),
    }.issubset(set(membership_lookup_calls))
    assert available_users == [
        {
            "id": "user-4",
            "username": "viewer",
            "email": "viewer@example.com",
            "display_name": None,
        },
        {
            "id": "user-5",
            "username": "writer",
            "email": "writer@example.com",
            "display_name": None,
        },
        {
            "id": "user-6",
            "username": "worker",
            "email": "worker@example.com",
            "display_name": None,
        },
    ]


def test_organization_group_members_lookup_batches_group_member_requests(monkeypatch):
    member_lookup_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda organization_id, group_id, admin_token=None: member_lookup_calls.append(
            (organization_id, group_id, admin_token)
        )
        or [
            {
                "id": f"{group_id}-member",
                "username": f"{group_id}-user",
                "email": f"{group_id}@example.com",
            }
        ],
    )

    members_by_group_id = tenant_role_service._organization_group_members_lookup(
        "org-1",
        [
            {"id": "group-1", "name": "Administrators"},
            {"id": "group-2", "name": "Editors"},
        ],
        admin_token="token-1",
    )

    assert sorted(member_lookup_calls) == [
        ("org-1", "group-1", "token-1"),
        ("org-1", "group-2", "token-1"),
    ]
    assert members_by_group_id == {
        "group-1": [
            {
                "id": "group-1-member",
                "username": "group-1-user",
                "email": "group-1@example.com",
                "display_name": None,
            }
        ],
        "group-2": [
            {
                "id": "group-2-member",
                "username": "group-2-user",
                "email": "group-2@example.com",
                "display_name": None,
            }
        ],
    }


def test_tenant_member_roles_lookup_batches_member_role_requests(monkeypatch):
    member_role_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "_normalized_member_roles",
        lambda organization_id, member_id, *, group_role_lookup=None, admin_token=None: member_role_calls.append(
            (organization_id, member_id, admin_token)
        )
        or ([f"role-{member_id}"] if group_role_lookup == {"by_group_id": {}, "by_group_name": {}} else []),
    )

    roles_by_member_id = tenant_role_service._tenant_member_roles_lookup(
        "org-1",
        [
            {"id": "member-1", "username": "admin"},
            {"id": "member-2", "username": "editor"},
        ],
        group_role_lookup={"by_group_id": {}, "by_group_name": {}},
        admin_token="token-1",
    )

    assert sorted(member_role_calls) == [
        ("org-1", "member-1", "token-1"),
        ("org-1", "member-2", "token-1"),
    ]
    assert roles_by_member_id == {
        "member-1": ["role-member-1"],
        "member-2": ["role-member-2"],
    }


def test_list_tenant_groups_with_members_reuses_one_admin_token(monkeypatch):
    admin_token_calls: list[str] = []
    list_groups_calls: list[tuple[str, str | None, bool]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "get_master_admin_token",
        lambda: admin_token_calls.append("called") or "token-1",
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id, admin_token=None: (
            SimpleNamespace(id=tenant_id, slug="tenant-slug"),
            {"id": "org-1"},
            "org-1",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_groups",
        lambda organization_id, admin_token=None, brief_representation=True: list_groups_calls.append(
            (organization_id, admin_token, brief_representation)
        )
        or [
            {
                "id": "group-1",
                "name": "Administrators",
                "path": "/Administrators",
                "attributes": {},
            }
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda _group: ["tenant-admin"],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_group_by_id",
        lambda *_args, **_kwargs: pytest.fail(
            "full group list should avoid extra group-by-id lookups"
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda organization_id, group_id, admin_token=None: [
            {"id": "member-1", "username": "admin", "email": "admin@example.com"}
        ]
        if organization_id == "org-1"
        and group_id == "group-1"
        and admin_token == "token-1"
        else pytest.fail("unexpected organization group-members arguments"),
    )

    groups = tenant_role_service.list_tenant_groups_with_members("tenant-1")

    assert admin_token_calls == ["called"]
    assert list_groups_calls == [("org-1", "token-1", False)]
    assert groups == [
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
        }
    ]
