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
    realm_exists,
    tenant_login_authorization_url,
)


def test_fill_realm_template_top_level() -> None:
    """Top-level realm, displayName are set for the new tenant; id is omitted for Keycloak create."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "displayName": "SpiffWorkflow",
    }
    result = _fill_realm_template(template, "tenant-b", "Tenant B", "spiffworkflow")
    assert result["realm"] == "tenant-b"
    assert result["displayName"] == "Tenant B"
    assert "id" not in result  # id is popped so Keycloak auto-generates it


def test_fill_realm_template_display_name_defaults_to_realm_id() -> None:
    """When display_name is None, displayName becomes realm_id."""
    template = {"id": "spiffworkflow", "realm": "spiffworkflow", "displayName": "Old"}
    result = _fill_realm_template(template, "tenant-c", None, "spiffworkflow")
    assert result["displayName"] == "tenant-c"


def test_fill_realm_template_realm_roles_container_id() -> None:
    """Realm roles with containerId equal to template name are updated."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "roles": {
            "realm": [
                {"id": "r1", "name": "admin", "containerId": "spiffworkflow"},
                {"id": "r2", "name": "default-roles-spiffworkflow", "containerId": "spiffworkflow"},
            ],
        },
    }
    result = _fill_realm_template(template, "tenant-d", None, "spiffworkflow")
    realm_roles = result["roles"]["realm"]
    assert realm_roles[0]["containerId"] == "tenant-d"
    assert realm_roles[1]["containerId"] == "tenant-d"
    assert realm_roles[1]["name"] == "default-roles-tenant-d"


def test_fill_realm_template_default_role() -> None:
    """defaultRole containerId and name are updated."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "defaultRole": {
            "name": "default-roles-spiffworkflow",
            "containerId": "spiffworkflow",
        },
    }
    result = _fill_realm_template(template, "tenant-e", None, "spiffworkflow")
    assert result["defaultRole"]["containerId"] == "tenant-e"
    assert result["defaultRole"]["name"] == "default-roles-tenant-e"


def test_fill_realm_template_user_realm_roles() -> None:
    """User realmRoles array has default-roles-{realm} updated."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "users": [
            {"username": "admin", "realmRoles": ["default-roles-spiffworkflow", "admin"]},
            {"username": "user1", "realmRoles": ["default-roles-spiffworkflow"]},
        ],
    }
    result = _fill_realm_template(template, "tenant-f", None, "spiffworkflow")
    assert result["users"][0]["realmRoles"] == ["default-roles-tenant-f", "admin"]
    assert result["users"][1]["realmRoles"] == ["default-roles-tenant-f"]


RBAC_REALM_ROLES = ("editor", "super-admin", "tenant-admin", "integrator", "reviewer", "viewer")
RBAC_USERNAMES = ("editor", "integrator", "reviewer", "super-admin", "tenant-admin", "viewer")


def test_fill_realm_template_rbac_roles_and_users() -> None:
    """Template with RBAC realm roles and users: roles are preserved, default role name is rewritten in user realmRoles."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "roles": {
            "realm": [
                {"id": "def", "name": "default-roles-spiffworkflow", "containerId": "spiffworkflow"},
                *[{"id": r, "name": r, "containerId": "spiffworkflow"} for r in RBAC_REALM_ROLES],
            ],
        },
        "users": [
            {"username": u, "realmRoles": ["default-roles-spiffworkflow", u]} for u in RBAC_USERNAMES
        ],
    }
    result = _fill_realm_template(template, "tenant-x", "Tenant X", "spiffworkflow")
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
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "clients": [
            {
                "clientId": "account",
                "baseUrl": "/realms/spiffworkflow/account/",
                "redirectUris": ["/realms/spiffworkflow/account/*"],
            },
            {
                "clientId": "security-admin-console",
                "baseUrl": "/admin/spiffworkflow/console/",
                "redirectUris": ["/admin/spiffworkflow/console/*"],
            },
        ],
    }
    result = _fill_realm_template(template, "tenant-g", None, "spiffworkflow")
    assert result["clients"][0]["baseUrl"] == "/realms/tenant-g/account/"
    assert result["clients"][0]["redirectUris"] == ["/realms/tenant-g/account/*"]
    assert result["clients"][1]["baseUrl"] == "/admin/tenant-g/console/"
    assert result["clients"][1]["redirectUris"] == ["/admin/tenant-g/console/*"]


def test_fill_realm_template_does_not_mutate_original() -> None:
    """Template is deep-copied; original is unchanged."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "roles": {"realm": [{"containerId": "spiffworkflow", "name": "admin"}]},
    }
    original_id = template["id"]
    original_role_container = template["roles"]["realm"][0]["containerId"]
    _fill_realm_template(template, "tenant-h", None, "spiffworkflow")
    assert template["id"] == original_id
    assert template["roles"]["realm"][0]["containerId"] == original_role_container


def test_fill_realm_template_client_attributes() -> None:
    """Client attributes containing realm URLs are updated."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "clients": [
            {
                "clientId": "test",
                "attributes": {
                    "post.logout.redirect.uris": "https://example.com/realms/spiffworkflow/account",
                },
            },
        ],
    }
    result = _fill_realm_template(template, "tenant-i", None, "spiffworkflow")
    assert "/realms/tenant-i/account" in result["clients"][0]["attributes"]["post.logout.redirect.uris"]


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_realm_exists_true(mock_get, mock_keycloak_url) -> None:
    """realm_exists returns True when Keycloak returns 200 from public discovery endpoint."""
    mock_keycloak_url.return_value = "http://localhost:7002"
    mock_get.return_value = MagicMock(status_code=200)
    assert realm_exists("tenant-a") is True
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "/realms/tenant-a/.well-known/openid-configuration" in call_url


@patch("m8flow_backend.services.keycloak_service.keycloak_url")
@patch("m8flow_backend.services.keycloak_service.requests.get")
def test_realm_exists_false_404(mock_get, mock_keycloak_url) -> None:
    """realm_exists returns False when Keycloak returns 404."""
    mock_keycloak_url.return_value = "http://localhost:7002"
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
    mock_keycloak_url.return_value = "http://localhost:7002"
    url = tenant_login_authorization_url("tenant-a")
    assert url == "http://localhost:7002/realms/tenant-a/protocol/openid-connect/auth"


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
