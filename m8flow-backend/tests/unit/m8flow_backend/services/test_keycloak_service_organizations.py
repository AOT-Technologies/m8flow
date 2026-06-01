from pathlib import Path
import sys
from unittest.mock import MagicMock
from unittest.mock import patch


extension_root = Path(__file__).resolve().parents[4]
extension_src = extension_root / "src"
if str(extension_src) not in sys.path:
    sys.path.insert(0, str(extension_src))


from m8flow_backend.services.keycloak_service import (  # noqa: E402
    add_group_realm_role_mapping,
    add_organization_member,
    add_organization_group_member,
    create_organization,
    ensure_organization_group_role_mappings,
    ensure_organization_role_groups,
    delete_organization,
    get_group_realm_role_mappings,
    get_organization_by_alias,
    get_organization_member_groups,
    get_organization_group_by_name,
    get_organization_member_by_username,
    get_realm_user_by_username,
    list_organization_group_members,
    list_organization_groups,
    organization_group_role_names,
    remove_group_realm_role_mapping,
    remove_organization_group_member,
    search_realm_users,
    search_organization_members,
    set_organization_group_role_names,
    update_organization,
)


@patch("m8flow_backend.services.keycloak_service.ensure_organization_role_groups")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
@patch("m8flow_backend.services.keycloak_service.requests.post")
def test_create_organization_uses_shared_realm_and_returns_created_org(
    mock_post,
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_ensure_organization_role_groups,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_post.return_value = MagicMock(
        status_code=201,
        headers={"Location": "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123"},
    )
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "id": "org-uuid-123",
            "alias": "tenant-a",
            "name": "Tenant A",
            "enabled": True,
        },
    )

    result = create_organization("tenant-a", "Tenant A")

    assert result["id"] == "org-uuid-123"
    assert result["alias"] == "tenant-a"
    assert result["name"] == "Tenant A"

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "http://keycloak/admin/realms/shared-users/organizations"
    assert mock_post.call_args[1]["json"] == {
        "alias": "tenant-a",
        "name": "Tenant A",
        "enabled": True,
    }

    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123"
    )
    mock_ensure_organization_role_groups.assert_called_once_with(
        "org-uuid-123",
        admin_token="master-token",
    )


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_by_alias_filters_exact_alias(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "partial-match", "alias": "tenant-a-extra", "name": "Partial Match"},
            {"id": "exact-match", "alias": "tenant-a", "name": "Tenant A"},
        ],
    )

    result = get_organization_by_alias("tenant-a")

    assert result == {"id": "exact-match", "alias": "tenant-a", "name": "Tenant A"}
    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == "http://keycloak/admin/realms/shared-users/organizations"
    assert mock_get.call_args[1]["params"] == {
        "search": "tenant-a",
        "exact": "true",
        "briefRepresentation": "false",
        "max": "100",
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_by_alias_falls_back_when_exact_search_returns_empty(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: []),
        MagicMock(
            status_code=200,
            json=lambda: [
                {"id": "exact-match", "alias": "tenant-a", "name": "Tenant A"},
                {"id": "partial-match", "alias": "tenant-a-extra", "name": "Partial Match"},
            ],
        ),
    ]

    result = get_organization_by_alias("tenant-a")

    assert result == {"id": "exact-match", "alias": "tenant-a", "name": "Tenant A"}
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0][1]["params"] == {
        "search": "tenant-a",
        "exact": "true",
        "briefRepresentation": "false",
        "max": "100",
    }
    assert mock_get.call_args_list[1][1]["params"] == {
        "search": "tenant-a",
        "exact": "false",
        "briefRepresentation": "false",
        "max": "100",
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_by_alias_falls_back_to_listing_all_when_search_returns_empty(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: []),
        MagicMock(status_code=200, json=lambda: []),
        MagicMock(
            status_code=200,
            json=lambda: [
                {"id": "tenant-b", "alias": "tenant-b", "name": "Tenant B"},
                {"id": "tenant-a", "alias": "tenant-a", "name": "Tenant A"},
            ],
        ),
    ]

    result = get_organization_by_alias("tenant-a")

    assert result == {"id": "tenant-a", "alias": "tenant-a", "name": "Tenant A"}
    assert mock_get.call_count == 3
    assert mock_get.call_args_list[2][1]["params"] == {
        "briefRepresentation": "false",
        "max": "100",
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_member_by_username_filters_exact_username(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "editor"},
            {"id": "user-2", "username": "editorial"},
        ],
    )

    result = get_organization_member_by_username("org-uuid-123", "editor")

    assert result == {"id": "user-1", "username": "editor"}
    assert mock_get.call_args[0][0] == "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/members"
    assert mock_get.call_args[1]["params"] == {
        "search": "editor",
        "exact": "true",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_member_by_username_falls_back_when_exact_search_returns_empty(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: []),
        MagicMock(
            status_code=200,
            json=lambda: [
                {"id": "user-1", "username": "editor"},
                {"id": "user-2", "username": "editorial"},
            ],
        ),
    ]

    result = get_organization_member_by_username("org-uuid-123", "editor")

    assert result == {"id": "user-1", "username": "editor"}
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0][1]["params"] == {
        "search": "editor",
        "exact": "true",
        "max": 100,
    }
    assert mock_get.call_args_list[1][1]["params"] == {
        "search": "editor",
        "exact": "false",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_realm_user_by_username_filters_exact_username(
    mock_get,
    mock_keycloak_url,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "editor"},
            {"id": "user-2", "username": "editorial"},
        ],
    )

    result = get_realm_user_by_username("m8flow", "editor")

    assert result == {"id": "user-1", "username": "editor"}
    assert mock_get.call_args[0][0] == "http://keycloak/admin/realms/m8flow/users"
    assert mock_get.call_args[1]["params"] == {
        "username": "editor",
        "exact": "true",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_search_realm_users_uses_search_query(
    mock_get,
    mock_keycloak_url,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "editor"},
            {"id": "user-2", "username": "editorial"},
            "skip-me",
        ],
    )

    result = search_realm_users("m8flow", "edit", exact=False)

    assert result == [
        {"id": "user-1", "username": "editor"},
        {"id": "user-2", "username": "editorial"},
    ]
    assert mock_get.call_args[0][0] == "http://keycloak/admin/realms/m8flow/users"
    assert mock_get.call_args[1]["params"] == {
        "search": "edit",
        "exact": "false",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_search_organization_members_uses_search_query(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "editor"},
            {"id": "user-2", "username": "editorial"},
            "skip-me",
        ],
    )

    result = search_organization_members("org-uuid-123", "edit", exact=False)

    assert result == [
        {"id": "user-1", "username": "editor"},
        {"id": "user-2", "username": "editorial"},
    ]
    assert mock_get.call_args[0][0] == "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/members"
    assert mock_get.call_args[1]["params"] == {
        "search": "edit",
        "exact": "false",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_search_organization_members_can_list_all_members_without_search(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "editor"},
            {"id": "user-2", "username": "reviewer"},
        ],
    )

    result = search_organization_members("org-uuid-123", "", exact=False)

    assert result == [
        {"id": "user-1", "username": "editor"},
        {"id": "user-2", "username": "reviewer"},
    ]
    assert mock_get.call_args[1]["params"] == {"max": 100}


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_member_groups_reads_member_groups_endpoint(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "group-1", "name": "editor"},
            {"id": "group-2", "name": "reviewer"},
        ],
    )

    result = get_organization_member_groups("org-uuid-123", "user-1")

    assert result == [
        {"id": "group-1", "name": "editor"},
        {"id": "group-2", "name": "reviewer"},
    ]
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/members/user-1/groups"
    )
    assert mock_get.call_args[1]["params"] == {
        "briefRepresentation": "true",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_list_organization_groups_reads_top_level_groups_endpoint(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "group-1", "name": "Administrators", "path": "/Administrators"},
            "skip-me",
        ],
    )

    result = list_organization_groups("org-uuid-123")

    assert result == [
        {"id": "group-1", "name": "Administrators", "path": "/Administrators"},
    ]
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups"
    )
    assert mock_get.call_args[1]["params"] == {
        "briefRepresentation": "true",
        "populateHierarchy": "false",
        "subGroupsCount": "false",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_list_organization_group_members_reads_group_members_endpoint(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "user-1", "username": "admin"},
            {"id": "user-2", "username": "reviewer"},
        ],
    )

    result = list_organization_group_members("org-uuid-123", "group-1")

    assert result == [
        {"id": "user-1", "username": "admin"},
        {"id": "user-2", "username": "reviewer"},
    ]
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-1/members"
    )
    assert mock_get.call_args[1]["params"] == {
        "briefRepresentation": "true",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_group_realm_role_mappings_reads_realm_group_role_mapping_endpoint(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "role-1", "name": "tenant-admin"},
            {"id": "role-2", "name": "default-roles-shared-users"},
        ],
    )

    result = get_group_realm_role_mappings("group-1")

    assert result == [
        {"id": "role-1", "name": "tenant-admin"},
        {"id": "role-2", "name": "default-roles-shared-users"},
    ]
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/groups/group-1/role-mappings/realm/composite"
    )


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_group_realm_role_mappings_reads_organization_group_role_mapping_endpoint(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [{"id": "role-1", "name": "tenant-admin"}],
    )

    result = get_group_realm_role_mappings("group-1", organization_id="org-uuid-123")

    assert result == [{"id": "role-1", "name": "tenant-admin"}]
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-1/role-mappings/realm/composite"
    )


@patch("m8flow_backend.services.keycloak_service.get_realm_role_by_name")
@patch("m8flow_backend.services.keycloak_service.get_group_realm_role_mappings")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.post")
def test_add_group_realm_role_mapping_posts_role_payload_once(
    mock_post,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_group_realm_role_mappings,
    mock_get_realm_role_by_name,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_group_realm_role_mappings.return_value = []
    mock_get_realm_role_by_name.return_value = {"id": "role-1", "name": "reviewer"}
    mock_post.return_value = MagicMock(status_code=204)

    add_group_realm_role_mapping("group-1", "reviewer")

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/groups/group-1/role-mappings/realm"
    )
    assert mock_post.call_args[1]["json"] == [{"id": "role-1", "name": "reviewer"}]


@patch("m8flow_backend.services.keycloak_service.get_realm_role_by_name")
@patch("m8flow_backend.services.keycloak_service.get_group_realm_role_mappings")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.post")
def test_add_group_realm_role_mapping_posts_to_organization_group_role_mapping_endpoint(
    mock_post,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_group_realm_role_mappings,
    mock_get_realm_role_by_name,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_group_realm_role_mappings.return_value = []
    mock_get_realm_role_by_name.return_value = {"id": "role-1", "name": "reviewer"}
    mock_post.return_value = MagicMock(status_code=204)

    add_group_realm_role_mapping("group-1", "reviewer", organization_id="org-uuid-123")

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-1/role-mappings/realm"
    )
    assert mock_post.call_args[1]["json"] == [{"id": "role-1", "name": "reviewer"}]


@patch("m8flow_backend.services.keycloak_service.get_group_realm_role_mappings")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
def test_remove_group_realm_role_mapping_deletes_existing_payload(
    mock_delete,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_group_realm_role_mappings,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_group_realm_role_mappings.return_value = [
        {"id": "role-1", "name": "reviewer"},
        {"id": "role-2", "name": "viewer"},
    ]
    mock_delete.return_value = MagicMock(status_code=204)

    remove_group_realm_role_mapping("group-1", "reviewer")

    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/groups/group-1/role-mappings/realm"
    )
    assert mock_delete.call_args[1]["json"] == [{"id": "role-1", "name": "reviewer"}]


@patch("m8flow_backend.services.keycloak_service.get_group_realm_role_mappings")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
def test_remove_group_realm_role_mapping_deletes_from_organization_group_role_mapping_endpoint(
    mock_delete,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_group_realm_role_mappings,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_group_realm_role_mappings.return_value = [
        {"id": "role-1", "name": "reviewer"},
        {"id": "role-2", "name": "viewer"},
    ]
    mock_delete.return_value = MagicMock(status_code=204)

    remove_group_realm_role_mapping("group-1", "reviewer", organization_id="org-uuid-123")

    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-1/role-mappings/realm"
    )
    assert mock_delete.call_args[1]["json"] == [{"id": "role-1", "name": "reviewer"}]


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_get_organization_group_by_name_filters_exact_top_level_group(
    mock_get,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: [
            {"id": "group-1", "name": "editor", "path": "/editor"},
            {"id": "group-2", "name": "editor", "path": "/engineering/editor"},
            {"id": "group-3", "name": "reviewer", "path": "/reviewer"},
        ],
    )

    result = get_organization_group_by_name("org-uuid-123", "editor")

    assert result == {"id": "group-1", "name": "editor", "path": "/editor"}
    assert mock_get.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups"
    )
    assert mock_get.call_args[1]["params"] == {
        "search": "editor",
        "exact": "true",
        "briefRepresentation": "true",
        "populateHierarchy": "false",
        "subGroupsCount": "false",
        "max": 100,
    }


@patch("m8flow_backend.services.keycloak_service.ensure_organization_group_role_mappings")
@patch("m8flow_backend.services.keycloak_service.create_organization_group")
@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_name")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
def test_ensure_organization_role_groups_creates_missing_groups_only(
    mock_get_master_admin_token,
    mock_get_organization_group_by_name,
    mock_create_organization_group,
    mock_ensure_organization_group_role_mappings,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_get_organization_group_by_name.side_effect = [
        {"id": "group-admin", "name": "tenant-admin", "path": "/tenant-admin"},
        None,
        None,
    ]
    mock_create_organization_group.side_effect = [
        {"id": "group-editor", "name": "editor", "path": "/editor"},
        {"id": "group-viewer", "name": "viewer", "path": "/viewer"},
    ]

    result = ensure_organization_role_groups(
        "org-uuid-123",
        group_names=("tenant-admin", "editor", "viewer"),
    )

    assert result == [
        {"id": "group-admin", "name": "tenant-admin", "path": "/tenant-admin"},
        {"id": "group-editor", "name": "editor", "path": "/editor"},
        {"id": "group-viewer", "name": "viewer", "path": "/viewer"},
    ]
    assert mock_get_organization_group_by_name.call_count == 3
    mock_create_organization_group.assert_any_call(
        "org-uuid-123",
        "editor",
        admin_token="master-token",
    )
    mock_create_organization_group.assert_any_call(
        "org-uuid-123",
        "viewer",
        admin_token="master-token",
    )
    mock_ensure_organization_group_role_mappings.assert_called_once_with(
        "org-uuid-123",
        admin_token="master-token",
    )


@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_name")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.put")
def test_add_organization_group_member_targets_group_member_endpoint(
    mock_put,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_organization_group_by_name,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_organization_group_by_name.return_value = {"id": "group-editor", "name": "editor"}
    mock_put.return_value = MagicMock(status_code=204)

    add_organization_group_member("org-uuid-123", "editor", "user-1")

    mock_put.assert_called_once()
    assert mock_put.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-editor/members/user-1"
    )


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.post")
def test_add_organization_member_targets_member_collection_endpoint(
    mock_post,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_post.return_value = MagicMock(status_code=201)

    add_organization_member("org-uuid-123", "user-1")

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/members"
    )
    assert mock_post.call_args[1]["json"] == "user-1"


def test_organization_group_role_names_prefers_explicit_attribute_configuration():
    assert organization_group_role_names(
        {
            "id": "group-1",
            "name": "Administrators",
            "attributes": {
                "m8flow_role_mapping_configured": ["true"],
                "m8flow_role_names": ["reviewer", "viewer"],
            },
        }
    ) == ["reviewer", "viewer"]


def test_organization_group_role_names_falls_back_to_default_group_mapping_when_unconfigured():
    assert organization_group_role_names(
        {
            "id": "group-1",
            "name": "Administrators",
            "attributes": {},
        }
    ) == ["tenant-admin"]


@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_id")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.put")
def test_set_organization_group_role_names_updates_group_attributes(
    mock_put,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_organization_group_by_id,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_put.return_value = MagicMock(status_code=204)
    mock_get_organization_group_by_id.side_effect = [
        {
            "id": "group-1",
            "name": "Approvers",
            "attributes": {},
        },
        {
            "id": "group-1",
            "name": "Approvers",
            "attributes": {
                "m8flow_role_mapping_configured": ["true"],
                "m8flow_role_names": ["reviewer"],
            },
        },
    ]

    result = set_organization_group_role_names("org-uuid-123", "group-1", ["reviewer"])

    assert result["attributes"]["m8flow_role_names"] == ["reviewer"]
    mock_put.assert_called_once()
    assert mock_put.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-1"
    )
    assert mock_put.call_args[1]["json"] == {
        "name": "Approvers",
        "attributes": {
            "m8flow_role_mapping_configured": ["true"],
            "m8flow_role_names": ["reviewer"],
        },
    }


@patch("m8flow_backend.services.keycloak_service.set_organization_group_role_names")
@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_id")
@patch("m8flow_backend.services.keycloak_service.list_organization_groups")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
def test_ensure_organization_group_role_mappings_seeds_defaults_only_when_unconfigured(
    mock_get_master_admin_token,
    mock_list_organization_groups,
    mock_get_organization_group_by_id,
    mock_set_organization_group_role_names,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_list_organization_groups.return_value = [
        {"id": "group-admin", "name": "Administrators"},
        {"id": "group-custom", "name": "Custom Review"},
    ]
    mock_get_organization_group_by_id.side_effect = [
        {"id": "group-admin", "name": "Administrators", "attributes": {}},
        {
            "id": "group-custom",
            "name": "Custom Review",
            "attributes": {"m8flow_role_mapping_configured": ["true"]},
        },
    ]

    ensure_organization_group_role_mappings("org-uuid-123")

    mock_set_organization_group_role_names.assert_called_once_with(
        "org-uuid-123",
        "group-admin",
        ["tenant-admin"],
        admin_token="master-token",
    )


@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_name")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.put")
def test_add_organization_group_member_ignores_conflict_when_member_already_assigned(
    mock_put,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_organization_group_by_name,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_organization_group_by_name.return_value = {"id": "group-editor", "name": "editor"}
    mock_put.return_value = MagicMock(status_code=409, raise_for_status=MagicMock())

    add_organization_group_member("org-uuid-123", "editor", "user-1")

    mock_put.assert_called_once()
    mock_put.return_value.raise_for_status.assert_not_called()


@patch("m8flow_backend.services.keycloak_service.get_organization_group_by_name")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
def test_remove_organization_group_member_targets_group_member_endpoint(
    mock_delete,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
    mock_get_organization_group_by_name,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_get_organization_group_by_name.return_value = {"id": "group-editor", "name": "editor"}
    mock_delete.return_value = MagicMock(status_code=204)

    remove_organization_group_member("org-uuid-123", "editor", "user-1")

    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123/groups/group-editor/members/user-1"
    )


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.shared_realm_name")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.put")
def test_update_organization_uses_shared_realm(
    mock_put,
    mock_keycloak_url,
    mock_shared_realm_name,
    mock_get_master_admin_token,
):
    mock_get_master_admin_token.return_value = "master-token"
    mock_shared_realm_name.return_value = "shared-users"
    mock_keycloak_url.return_value = "http://keycloak"
    mock_put.return_value = MagicMock(status_code=204)

    update_organization("org-uuid-123", alias="tenant-a", name="Tenant A+")

    mock_put.assert_called_once()
    assert mock_put.call_args[0][0] == (
        "http://keycloak/admin/realms/shared-users/organizations/org-uuid-123"
    )
    assert mock_put.call_args[1]["json"] == {
        "id": "org-uuid-123",
        "alias": "tenant-a",
        "name": "Tenant A+",
        "enabled": True,
    }


@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
def test_delete_organization_404_is_idempotent(mock_delete, mock_get_master_admin_token):
    mock_get_master_admin_token.return_value = "master-token"
    mock_delete.return_value = MagicMock(status_code=404)

    delete_organization("org-uuid-123")

    mock_delete.assert_called_once()
