"""Unit tests for Keycloak service (_fill_realm_template and template substitution)."""
import sys
from pathlib import Path

# Ensure m8flow_backend is importable
extension_root = Path(__file__).resolve().parents[4]
extension_src = extension_root / "src"
if str(extension_src) not in sys.path:
    sys.path.insert(0, str(extension_src))

from m8flow_backend.services.keycloak_service import _fill_realm_template  # noqa: E402


def test_fill_realm_template_top_level() -> None:
    """Top-level id, realm, displayName are set for the new tenant."""
    template = {
        "id": "spiffworkflow",
        "realm": "spiffworkflow",
        "displayName": "SpiffWorkflow",
    }
    result = _fill_realm_template(template, "tenant-b", "Tenant B", "spiffworkflow")
    assert result["id"] == "tenant-b"
    assert result["realm"] == "tenant-b"
    assert result["displayName"] == "Tenant B"


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
