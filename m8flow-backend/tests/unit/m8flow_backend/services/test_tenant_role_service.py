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


def test_rename_tenant_group_preserves_roles_and_resyncs_members(monkeypatch):
    rename_calls: list[tuple[str, str, str, list[str] | None]] = []
    sync_calls: list[tuple[str, str, str, dict[str, dict[str, list[str]]]]] = []

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
        "_organization_group_or_error",
        lambda organization_id, group_name: {
            "id": "group-1",
            "name": group_name,
            "path": f"/{group_name}",
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_name_lookup",
        lambda _organization_id: {
            "approvers": "Approvers",
            "submitters": "Submitters",
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_mapped_roles_for_group",
        lambda group, organization_id=None, group_role_lookup=None, admin_token=None: [
            "reviewer"
        ],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "rename_organization_group",
        lambda organization_id, group_id, group_name, mapped_role_names=None, admin_token=None: (
            rename_calls.append(
                (organization_id, group_id, group_name, list(mapped_role_names or []))
            )
            or {
                "id": group_id,
                "name": group_name,
                "path": f"/{group_name}",
                "attributes": {
                    "m8flow.role_mapping.configured": ["true"],
                    "m8flow.role_names": list(mapped_role_names or []),
                },
            }
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_role_lookup",
        lambda organization_id, admin_token=None, groups=None: {
            "by_group_id": {"group-1": ["reviewer"]},
            "by_group_name": {"qa reviewers": ["reviewer"]},
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_members_for_group",
        lambda tenant, organization_id, group, group_role_lookup=None: sync_calls.append(
            (
                tenant.id,
                organization_id,
                str(group.get("name") or ""),
                group_role_lookup or {},
            )
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda _organization_id, _group_id, admin_token=None: [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_serialize_group",
        lambda organization_id, group, group_role_lookup=None, members_by_group_id=None, admin_token=None: {
            "id": group["id"],
            "name": group["name"],
            "path": group["path"],
            "mapped_roles": ["reviewer"],
            "member_count": 0,
            "members": [],
        },
    )

    renamed_group = tenant_role_service.rename_tenant_group(
        "tenant-1",
        "Approvers",
        "  QA   Reviewers  ",
    )

    assert rename_calls == [("org-1", "group-1", "QA Reviewers", ["reviewer"])]
    assert sync_calls == [
        (
            "tenant-1",
            "org-1",
            "QA Reviewers",
            {
                "by_group_id": {"group-1": ["reviewer"]},
                "by_group_name": {"qa reviewers": ["reviewer"]},
            },
        )
    ]
    assert renamed_group == {
        "id": "group-1",
        "name": "QA Reviewers",
        "path": "/QA Reviewers",
        "mapped_roles": ["reviewer"],
        "member_count": 0,
        "members": [],
    }


def test_delete_tenant_group_removes_group_and_resyncs_members(monkeypatch):
    delete_calls: list[tuple[str, str]] = []
    sync_calls: list[tuple[str, str, str, dict[str, dict[str, list[str]]]]] = []

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
        "_organization_group_or_error",
        lambda organization_id, group_name: {
            "id": "group-1",
            "name": group_name,
            "path": f"/{group_name}",
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda organization_id, group_id, admin_token=None: [
            {"id": "member-1", "username": "reviewer"},
            {"id": "member-2", "username": "submitter"},
        ]
        if organization_id == "org-1" and group_id == "group-1"
        else [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "delete_organization_group",
        lambda organization_id, group_id, admin_token=None: delete_calls.append(
            (organization_id, group_id)
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_role_lookup",
        lambda organization_id, admin_token=None, groups=None: {
            "by_group_id": {},
            "by_group_name": {},
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_sync_local_member_from_keycloak_member",
        lambda tenant, organization_id, member, group_role_lookup=None: sync_calls.append(
            (
                tenant.id,
                organization_id,
                str(member.get("username") or ""),
                group_role_lookup or {},
            )
        )
        or (SimpleNamespace(id=member.get("id")), []),
    )

    deleted_group_name = tenant_role_service.delete_tenant_group(
        "tenant-1",
        "Approvers",
    )

    assert deleted_group_name == "Approvers"
    assert delete_calls == [("org-1", "group-1")]
    assert sync_calls == [
        ("tenant-1", "org-1", "reviewer", {"by_group_id": {}, "by_group_name": {}}),
        ("tenant-1", "org-1", "submitter", {"by_group_id": {}, "by_group_name": {}}),
    ]


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
            "groups": [{"id": "group-1", "name": "Administrators"}],
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


def test_list_tenant_groups_with_members_applies_paging_before_member_lookups(monkeypatch):
    member_lookup_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(
        tenant_role_service,
        "get_master_admin_token",
        lambda: "token-1",
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
        lambda organization_id, admin_token=None, brief_representation=True: [
            {
                "id": "group-b",
                "name": "Bravo",
                "path": "/Bravo",
                "attributes": {},
            },
            {
                "id": "group-a",
                "name": "Alpha",
                "path": "/Alpha",
                "attributes": {},
            },
            {
                "id": "group-c",
                "name": "Charlie",
                "path": "/Charlie",
                "attributes": {},
            },
        ]
        if organization_id == "org-1" and admin_token == "token-1" and brief_representation is False
        else pytest.fail("unexpected organization group list arguments"),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda _group: [],
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

    groups = tenant_role_service.list_tenant_groups_with_members(
        "tenant-1",
        offset=1,
        max_results=1,
    )

    assert member_lookup_calls == [("org-1", "group-b", "token-1")]
    assert groups == [
        {
            "id": "group-b",
            "name": "Bravo",
            "path": "/Bravo",
            "mapped_roles": [],
            "member_count": 1,
            "members": [
                {
                    "id": "group-b-member",
                    "username": "group-b-user",
                    "email": "group-b@example.com",
                    "display_name": None,
                }
            ],
        }
    ]
