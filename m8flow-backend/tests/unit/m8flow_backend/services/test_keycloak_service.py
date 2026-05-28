"""Unit tests for Keycloak service (_fill_realm_template, realm_exists, tenant_login_authorization_url)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# Ensure m8flow_backend is importable
extension_root = Path(__file__).resolve().parents[4]
extension_src = extension_root / "src"
if str(extension_src) not in sys.path:
    sys.path.insert(0, str(extension_src))

from m8flow_backend.services.keycloak_service import (  # noqa: E402
    _fill_realm_template,
    ensure_backend_redirect_uri_in_keycloak_client,
    load_default_organizational_group_paths,
    realm_exists,
    tenant_login_authorization_url,
)


def _flatten_group_paths(groups: list[dict]) -> list[str]:
    paths: list[str] = []

    def _visit(group_items: list[dict]) -> None:
        for group in group_items:
            group_path = group.get("path")
            if isinstance(group_path, str):
                paths.append(group_path)
            sub_groups = group.get("subGroups") or []
            if isinstance(sub_groups, list):
                _visit(sub_groups)

    _visit(groups)
    return paths


def test_fill_realm_template_top_level() -> None:
    """Top-level realm, displayName are set for the new tenant; id is omitted for Keycloak create."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "displayName": "M8Flow Realm",
    }
    result = _fill_realm_template(template, "tenant-b", "Tenant B", "m8flow")
    assert result["realm"] == "tenant-b"
    assert result["displayName"] == "Tenant B"
    assert "id" not in result  # id is popped so Keycloak auto-generates it


def test_fill_realm_template_display_name_defaults_to_realm_id() -> None:
    """When display_name is None, displayName becomes realm_id."""
    template = {"id": "m8flow", "realm": "m8flow", "displayName": "Old"}
    result = _fill_realm_template(template, "tenant-c", None, "m8flow")
    assert result["displayName"] == "tenant-c"


def test_fill_realm_template_realm_roles_container_id() -> None:
    """Realm roles with containerId equal to template name are updated."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "roles": {
            "realm": [
                {"id": "r1", "name": "admin", "containerId": "m8flow"},
                {"id": "r2", "name": "default-roles-m8flow", "containerId": "m8flow"},
            ],
        },
    }
    result = _fill_realm_template(template, "tenant-d", None, "m8flow")
    realm_roles = result["roles"]["realm"]
    assert realm_roles[0]["containerId"] == "tenant-d"
    assert realm_roles[1]["containerId"] == "tenant-d"
    assert realm_roles[1]["name"] == "default-roles-tenant-d"


def test_fill_realm_template_default_role() -> None:
    """defaultRole containerId and name are updated."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "defaultRole": {
            "name": "default-roles-m8flow",
            "containerId": "m8flow",
        },
    }
    result = _fill_realm_template(template, "tenant-e", None, "m8flow")
    assert result["defaultRole"]["containerId"] == "tenant-e"
    assert result["defaultRole"]["name"] == "default-roles-tenant-e"


def test_fill_realm_template_user_realm_roles() -> None:
    """User realmRoles array has default-roles-{realm} updated."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "users": [
            {"username": "admin", "realmRoles": ["default-roles-m8flow", "admin"]},
            {"username": "user1", "realmRoles": ["default-roles-m8flow"]},
        ],
    }
    result = _fill_realm_template(template, "tenant-f", None, "m8flow")
    assert result["users"][0]["realmRoles"] == ["default-roles-tenant-f", "admin"]
    assert result["users"][1]["realmRoles"] == ["default-roles-tenant-f"]


RBAC_REALM_ROLES = ("editor", "tenant-admin", "integrator", "reviewer", "submitter", "viewer")
RBAC_USERNAMES = ("editor", "integrator", "reviewer", "submitter", "tenant-admin", "viewer")


def test_fill_realm_template_rbac_roles_and_users() -> None:
    """Template with RBAC realm roles and users: roles are preserved, default role name is rewritten in user realmRoles."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "roles": {
            "realm": [
                {"id": "def", "name": "default-roles-m8flow", "containerId": "m8flow"},
                *[{"id": r, "name": r, "containerId": "m8flow"} for r in RBAC_REALM_ROLES],
            ],
        },
        "users": [
            {"username": u, "realmRoles": ["default-roles-m8flow", u]} for u in RBAC_USERNAMES
        ],
    }
    result = _fill_realm_template(template, "tenant-x", "Tenant X", "m8flow")
    realm_role_names = [r["name"] for r in result["roles"]["realm"]]
    for role in RBAC_REALM_ROLES:
        assert role in realm_role_names
    assert "default-roles-tenant-x" in realm_role_names
    user_usernames = [u["username"] for u in result["users"]]
    for username in RBAC_USERNAMES:
        assert username in user_usernames
    for user in result["users"]:
        assert "default-roles-tenant-x" in user["realmRoles"]
        assert user["username"] in user["realmRoles"]


def test_fill_realm_template_client_urls() -> None:
    """Client baseUrl, redirectUris contain /realms/{realm}/ and /admin/{realm}/ updated."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "clients": [
            {
                "clientId": "account",
                "baseUrl": "/realms/m8flow/account/",
                "redirectUris": ["/realms/m8flow/account/*"],
            },
            {
                "clientId": "security-admin-console",
                "baseUrl": "/admin/m8flow/console/",
                "redirectUris": ["/admin/m8flow/console/*"],
            },
        ],
    }
    result = _fill_realm_template(template, "tenant-g", None, "m8flow")
    assert result["clients"][0]["baseUrl"] == "/realms/tenant-g/account/"
    assert result["clients"][0]["redirectUris"] == ["/realms/tenant-g/account/*"]
    assert result["clients"][1]["baseUrl"] == "/admin/tenant-g/console/"
    assert result["clients"][1]["redirectUris"] == ["/admin/tenant-g/console/*"]


def test_fill_realm_template_does_not_mutate_original() -> None:
    """Template is deep-copied; original is unchanged."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "roles": {"realm": [{"containerId": "m8flow", "name": "admin"}]},
    }
    original_id = template["id"]
    original_role_container = template["roles"]["realm"][0]["containerId"]
    _fill_realm_template(template, "tenant-h", None, "m8flow")
    assert template["id"] == original_id
    assert template["roles"]["realm"][0]["containerId"] == original_role_container


def test_fill_realm_template_client_attributes() -> None:
    """Client attributes containing realm URLs are updated."""
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "clients": [
            {
                "clientId": "test",
                "attributes": {
                    "post.logout.redirect.uris": "https://example.com/realms/m8flow/account",
                },
            },
        ],
    }
    result = _fill_realm_template(template, "tenant-i", None, "m8flow")
    assert "/realms/tenant-i/account" in result["clients"][0]["attributes"]["post.logout.redirect.uris"]


def test_load_default_organizational_group_paths() -> None:
    assert load_default_organizational_group_paths() == [
        "/Approvers",
        "/Designers",
        "/Administrators",
        "/Support",
        "/Submitters",
        "/Viewers",
    ]


@patch("m8flow_backend.services.keycloak_service.load_default_organizational_group_paths")
def test_fill_realm_template_merges_default_organizational_groups(mock_default_groups) -> None:
    mock_default_groups.return_value = ["/Designers", "/Approvers", "/Support", "/Submitters", "/Viewers"]
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "groups": [
            {"name": "Administrators", "path": "/Administrators", "subGroups": []},
        ],
    }

    result = _fill_realm_template(template, "tenant-j", None, "m8flow")

    assert _flatten_group_paths(result["groups"]) == [
        "/Administrators",
        "/Designers",
        "/Approvers",
        "/Support",
        "/Submitters",
        "/Viewers",
    ]
    assert _flatten_group_paths(template["groups"]) == ["/Administrators"]


def test_fill_realm_template_injects_runtime_redirects_for_backend_client(monkeypatch) -> None:
    """Backend tenant client gets backend/frontend URLs from env instead of placeholder-only defaults."""
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_URL", raising=False)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_URL", "http://192.168.1.105:8000")
    monkeypatch.setenv("M8FLOW_BACKEND_URL_FOR_FRONTEND", "http://192.168.1.105:8001")
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "clients": [
            {
                "clientId": "m8flow-backend",
                "redirectUris": [
                    "http://localhost:6840/*",
                    "https://replace-me-with-m8flow-backend-host-and-path/*",
                ],
                "webOrigins": [],
                "attributes": {
                    "post.logout.redirect.uris": (
                        "https://replace-me-with-m8flow-frontend-host-and-path/*##http://localhost:6841/*"
                    ),
                },
            }
        ],
    }

    result = _fill_realm_template(template, "tenant-runtime", None, "m8flow")
    client = result["clients"][0]

    assert "http://192.168.1.105:8000/*" in client["redirectUris"]
    assert "http://192.168.1.105:8001/*" in client["redirectUris"]
    assert "http://192.168.1.105:8000" in client["webOrigins"]
    assert "http://192.168.1.105:8001" in client["webOrigins"]
    assert (
        client["attributes"]["post.logout.redirect.uris"]
        == "http://192.168.1.105:8001/*##http://localhost:6841/*##http://192.168.1.105:8000/*"
    )


def test_fill_realm_template_injects_runtime_redirects_for_frontend_client(monkeypatch) -> None:
    """Frontend tenant client gets the configured frontend origin added."""
    monkeypatch.setenv("M8FLOW_BACKEND_URL_FOR_FRONTEND", "http://192.168.1.105:8001")
    template = {
        "id": "m8flow",
        "realm": "m8flow",
        "clients": [
            {
                "clientId": "spiffworkflow-frontend",
                "redirectUris": [],
                "webOrigins": [],
                "attributes": {},
            }
        ],
    }

    result = _fill_realm_template(template, "tenant-ui", None, "m8flow")
    client = result["clients"][0]

    assert client["redirectUris"] == ["http://192.168.1.105:8001/*"]
    assert client["webOrigins"] == ["http://192.168.1.105:8001"]
    assert client["attributes"]["post.logout.redirect.uris"] == "http://192.168.1.105:8001/*"


@patch("m8flow_backend.services.keycloak_service.spoke_client_id")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
@patch("m8flow_backend.services.keycloak_service.requests.post")
@patch("m8flow_backend.services.keycloak_service.requests.put")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_ensure_backend_redirect_uri_in_keycloak_client_reconciles_legacy_roles_groups_mapper(
    mock_get,
    mock_put,
    mock_post,
    mock_delete,
    mock_token,
    mock_keycloak_url,
    mock_spoke_client_id,
    monkeypatch,
) -> None:
    monkeypatch.setenv("M8FLOW_BACKEND_URL", "http://192.168.1.105:8000")
    monkeypatch.setenv("M8FLOW_BACKEND_URL_FOR_FRONTEND", "http://192.168.1.105:8001")

    mock_spoke_client_id.return_value = "m8flow-backend"
    mock_keycloak_url.return_value = "http://localhost:7002"
    mock_token.return_value = "admin-token"

    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: [{"id": "client-123"}], raise_for_status=lambda: None),
        MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": "legacy-mapper",
                    "name": "groups",
                    "protocolMapper": "oidc-usermodel-realm-role-mapper",
                    "config": {"claim.name": "groups"},
                }
            ],
            raise_for_status=lambda: None,
        ),
        MagicMock(
            status_code=200,
            json=lambda: [{"id": "profile-scope-123", "name": "profile"}],
            raise_for_status=lambda: None,
        ),
        MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": "profile-groups-mapper",
                    "name": "groups",
                    "protocolMapper": "oidc-normalized-group-membership-mapper",
                    "config": {"claim.name": "groups"},
                }
            ],
            raise_for_status=lambda: None,
        ),
        MagicMock(
            status_code=200,
            json=lambda: {
                "id": "client-123",
                "redirectUris": ["http://192.168.1.105:8000/*", "http://192.168.1.105:8001/*"],
                "webOrigins": ["http://192.168.1.105:8000", "http://192.168.1.105:8001"],
                "attributes": {"post.logout.redirect.uris": "http://192.168.1.105:8001/*"},
            },
            raise_for_status=lambda: None,
        ),
    ]
    mock_delete.return_value = MagicMock(status_code=204, raise_for_status=lambda: None)
    mock_post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)

    ensure_backend_redirect_uri_in_keycloak_client("tenant-a")

    assert mock_delete.call_count == 2
    deleted_urls = [call.args[0] for call in mock_delete.call_args_list]
    assert any(url.endswith("/clients/client-123/protocol-mappers/models/legacy-mapper") for url in deleted_urls)
    assert any(url.endswith("/client-scopes/profile-scope-123/protocol-mappers/models/profile-groups-mapper") for url in deleted_urls)
    assert mock_post.call_count == 1
    roles_mapper_payload = mock_post.call_args_list[0].kwargs["json"]
    assert roles_mapper_payload["name"] == "roles"
    assert roles_mapper_payload["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert roles_mapper_payload["config"]["claim.name"] == "roles"
    mock_put.assert_not_called()


@patch("m8flow_backend.services.keycloak_service.spoke_client_id")
@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.get_master_admin_token")
@patch("m8flow_backend.services.keycloak_service.requests.delete")
@patch("m8flow_backend.services.keycloak_service.requests.post")
@patch("m8flow_backend.services.keycloak_service.requests.put")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_ensure_backend_redirect_uri_in_keycloak_client_reconciles_mappers_without_backend_url(
    mock_get,
    mock_put,
    mock_post,
    mock_delete,
    mock_token,
    mock_keycloak_url,
    mock_spoke_client_id,
    monkeypatch,
) -> None:
    monkeypatch.delenv("M8FLOW_BACKEND_URL", raising=False)
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_URL", raising=False)
    monkeypatch.setenv("M8FLOW_BACKEND_URL_FOR_FRONTEND", "http://192.168.1.105:8001")

    mock_spoke_client_id.return_value = "m8flow-backend"
    mock_keycloak_url.return_value = "http://localhost:7002"
    mock_token.return_value = "admin-token"

    mock_get.side_effect = [
        MagicMock(status_code=200, json=lambda: [{"id": "client-123"}], raise_for_status=lambda: None),
        MagicMock(status_code=200, json=lambda: [], raise_for_status=lambda: None),
        MagicMock(
            status_code=200,
            json=lambda: [{"id": "profile-scope-123", "name": "profile"}],
            raise_for_status=lambda: None,
        ),
        MagicMock(status_code=200, json=lambda: [], raise_for_status=lambda: None),
    ]
    mock_post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)

    ensure_backend_redirect_uri_in_keycloak_client("tenant-a")

    mock_delete.assert_not_called()
    assert mock_post.call_count == 1
    assert mock_post.call_args_list[0].kwargs["json"]["name"] == "roles"
    mock_put.assert_not_called()


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_realm_exists_true(mock_get, mock_keycloak_url) -> None:
    """realm_exists returns True when Keycloak returns 200 from public discovery endpoint."""
    mock_keycloak_url.return_value = "http://localhost:6842"
    mock_get.return_value = MagicMock(status_code=200)
    assert realm_exists("tenant-a") is True
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "/realms/tenant-a/.well-known/openid-configuration" in call_url


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_realm_exists_false_404(mock_get, mock_keycloak_url) -> None:
    """realm_exists returns False when Keycloak returns 404."""
    mock_keycloak_url.return_value = "http://localhost:6842"
    mock_get.return_value = MagicMock(status_code=404)
    assert realm_exists("missing-realm") is False


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
def test_realm_exists_false_on_exception(mock_keycloak_url) -> None:
    """realm_exists returns False when request raises."""
    mock_keycloak_url.side_effect = Exception("network error")
    assert realm_exists("tenant-a") is False


def test_realm_exists_empty_realm() -> None:
    """realm_exists returns False for empty or whitespace realm."""
    assert realm_exists("") is False
    assert realm_exists("   ") is False


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
def test_tenant_login_authorization_url(mock_keycloak_url) -> None:
    """tenant_login_authorization_url returns Keycloak auth endpoint for realm."""
    mock_keycloak_url.return_value = "http://localhost:6842"
    url = tenant_login_authorization_url("tenant-a")
    assert url == "http://localhost:6842/realms/tenant-a/protocol/openid-connect/auth"


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
def test_tenant_login_authorization_url_strips_realm(mock_keycloak_url) -> None:
    """tenant_login_authorization_url strips realm whitespace."""
    mock_keycloak_url.return_value = "http://keycloak"
    url = tenant_login_authorization_url("  tenant-b  ")
    assert url == "http://keycloak/realms/tenant-b/protocol/openid-connect/auth"


def test_tenant_login_authorization_url_empty_raises() -> None:
    """tenant_login_authorization_url raises ValueError for empty realm."""
    with pytest.raises(ValueError, match="realm is required"):
        tenant_login_authorization_url("")
    with pytest.raises(ValueError, match="realm is required"):
        tenant_login_authorization_url("   ")
