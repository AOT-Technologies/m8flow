"""Unit tests for Keycloak API controller (create_realm, tenant_login, create_user_in_realm)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import requests

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import pytest
from flask import Flask, g
from m8flow_backend.routes.keycloak_controller import (  # noqa: E402
    create_realm,
    create_user_in_realm,
    delete_tenant_realm,
    get_tenant_login_url,
    tenant_login,
    update_tenant_name,
)
from spiffworkflow_backend.exceptions.api_error import ApiError

@pytest.fixture
def app():
    """Create a Flask app for testing."""
    _app = Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX"] = "/v1.0"
    return _app

@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.username = "test-user"
    user.id = 1
    user.groups = []
    return user


class TestCreateRealm:
    """Tests for create_realm (POST /tenant-realms)."""

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.create_tenant_if_not_exists")
    @patch("m8flow_backend.routes.keycloak_controller.create_organization")
    def test_create_realm_success(self, mock_create_organization, mock_create_tenant, mock_auth, app, mock_user):
        mock_auth.return_value = True
        mock_create_organization.return_value = {
            "id": "org-uuid-tenant-b-123",
            "alias": "tenant-b",
            "name": "Tenant B",
            "enabled": True,
        }
        body = {"realm_id": "tenant-b", "display_name": "Tenant B"}
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm(body)
            assert status == 201
            assert result["realm"] == "tenant-b"
            assert result["displayName"] == "Tenant B"
            assert result["alias"] == "tenant-b"
            assert result["name"] == "Tenant B"
            assert result["id"] == "org-uuid-tenant-b-123"
            assert result["organization_id"] == "org-uuid-tenant-b-123"
            assert result["keycloak_realm_id"] == "org-uuid-tenant-b-123"
            mock_create_organization.assert_called_once_with(
                alias="tenant-b",
                name="Tenant B",
            )
            mock_create_tenant.assert_called_once_with(
                "org-uuid-tenant-b-123",
                name="Tenant B",
                slug="tenant-b",
            )

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.create_tenant_if_not_exists")
    @patch("m8flow_backend.routes.keycloak_controller.create_organization")
    def test_create_realm_accepts_slug_and_name_fields(
        self,
        mock_create_organization,
        mock_create_tenant,
        mock_auth,
        app,
        mock_user,
    ):
        mock_auth.return_value = True
        mock_create_organization.return_value = {
            "id": "org-uuid-tenant-c-456",
            "alias": "tenant-c",
            "name": "Tenant C",
            "enabled": True,
        }
        body = {"slug": "tenant-c", "name": "Tenant C"}
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm(body)
            assert status == 201
            assert result["id"] == "org-uuid-tenant-c-456"
            mock_create_organization.assert_called_once_with(alias="tenant-c", name="Tenant C")
            mock_create_tenant.assert_called_once_with(
                "org-uuid-tenant-c-456",
                name="Tenant C",
                slug="tenant-c",
            )

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    def test_create_realm_missing_realm_id(self, mock_auth, app, mock_user):
        mock_auth.return_value = True
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm({})
            assert status == 400
            assert "realm_id or slug" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    def test_create_realm_empty_realm_id(self, mock_auth, app, mock_user):
        mock_auth.return_value = True
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm({"realm_id": "   "})
            assert status == 400
            assert "realm_id or slug" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.create_organization")
    def test_create_realm_http_409(self, mock_create_organization, mock_auth, app, mock_user):
        mock_auth.return_value = True
        resp = MagicMock()
        resp.status_code = 409
        resp.text = "Organization already exists"
        mock_create_organization.side_effect = requests.exceptions.HTTPError(response=resp)
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm({"realm_id": "tenant-b"})
            assert status == 409
            assert "already exists" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.create_organization")
    def test_create_realm_http_500(self, mock_create_organization, mock_auth, app, mock_user):
        mock_auth.return_value = True
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal error"
        mock_create_organization.side_effect = requests.exceptions.HTTPError(response=resp)
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm({"realm_id": "tenant-b"})
            assert status == 500
            assert "Internal error" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.create_organization")
    def test_create_realm_value_error(self, mock_create_organization, mock_auth, app, mock_user):
        mock_auth.return_value = True
        mock_create_organization.side_effect = ValueError("Invalid alias")
        with app.test_request_context():
            g.user = mock_user
            result, status = create_realm({"realm_id": "tenant-b"})
            assert status == 400
            assert "Invalid alias" in result["detail"]


class TestTenantLogin:
    """Tests for tenant_login (POST /tenant-login)."""

    @patch("m8flow_backend.routes.keycloak_controller.tenant_login_svc")
    def test_tenant_login_success(self, mock_login):
        mock_login.return_value = {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "expires_in": 1800,
            "token_type": "Bearer",
        }
        body = {"realm": "tenant-a", "username": "user1", "password": "secret"}
        result, status = tenant_login(body)
        assert status == 200
        assert result["access_token"] == "eyJ..."
        mock_login.assert_called_once_with(
            realm="tenant-a",
            username="user1",
            password="secret",
        )

    @patch("m8flow_backend.routes.keycloak_controller.tenant_login_svc")
    def test_tenant_login_password_optional(self, mock_login):
        mock_login.return_value = {"access_token": "eyJ..."}
        body = {"realm": "tenant-a", "username": "user1"}
        result, status = tenant_login(body)
        assert status == 200
        mock_login.assert_called_once_with(realm="tenant-a", username="user1", password="")

    def test_tenant_login_missing_realm(self):
        result, status = tenant_login({"username": "user1", "password": "x"})
        assert status == 400
        assert "realm" in result["detail"]

    def test_tenant_login_missing_username(self):
        result, status = tenant_login({"realm": "tenant-a", "password": "x"})
        assert status == 400
        assert "username" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.tenant_login_svc")
    def test_tenant_login_http_401(self, mock_login):
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        mock_login.side_effect = requests.exceptions.HTTPError(response=resp)
        result, status = tenant_login({"realm": "tenant-a", "username": "u", "password": "p"})
        assert status == 401
        assert "Invalid credentials" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.tenant_login_svc")
    def test_tenant_login_value_error(self, mock_login):
        mock_login.side_effect = ValueError("Keystore not found")
        result, status = tenant_login({"realm": "tenant-a", "username": "u", "password": "p"})
        assert status == 400
        assert "Keystore" in result["detail"]


class TestCreateUserInRealm:
    """Tests for create_user_in_realm (POST /realms/{realm}/users)."""

    @patch("m8flow_backend.routes.keycloak_controller.create_user_in_realm_svc")
    def test_create_user_success(self, mock_create_user):
        mock_create_user.return_value = "a1b2c3d4-uuid"
        body = {"username": "newuser", "password": "secret", "email": "u@example.com"}
        result, status = create_user_in_realm("tenant-a", body)
        assert status == 201
        assert result["user_id"] == "a1b2c3d4-uuid"
        assert "/admin/realms/tenant-a/users/a1b2c3d4-uuid" in result["location"]
        mock_create_user.assert_called_once_with(
            realm="tenant-a",
            username="newuser",
            password="secret",
            email="u@example.com",
        )

    @patch("m8flow_backend.routes.keycloak_controller.create_user_in_realm_svc")
    def test_create_user_no_email(self, mock_create_user):
        mock_create_user.return_value = "uuid-123"
        body = {"username": "newuser", "password": "secret"}
        result, status = create_user_in_realm("tenant-b", body)
        assert status == 201
        mock_create_user.assert_called_once_with(
            realm="tenant-b",
            username="newuser",
            password="secret",
            email=None,
        )

    def test_create_user_missing_realm(self):
        result, status = create_user_in_realm("", {"username": "u", "password": "p"})
        assert status == 400
        assert "realm" in result["detail"]

    def test_create_user_missing_username(self):
        result, status = create_user_in_realm("tenant-a", {"password": "p"})
        assert status == 400
        assert "username" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_user_in_realm_svc")
    def test_create_user_http_409(self, mock_create_user):
        resp = MagicMock()
        resp.status_code = 409
        resp.text = "User exists"
        mock_create_user.side_effect = requests.exceptions.HTTPError(response=resp)
        result, status = create_user_in_realm("tenant-a", {"username": "u", "password": "p"})
        assert status == 409
        assert "already exists" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_user_in_realm_svc")
    def test_create_user_value_error(self, mock_create_user):
        mock_create_user.side_effect = ValueError("Realm not found")
        result, status = create_user_in_realm("tenant-a", {"username": "u", "password": "p"})
        assert status == 400
        assert "Realm" in result["detail"]


class TestGetTenantLoginUrl:
    """Tests for get_tenant_login_url (GET /tenant-login-url)."""

    @patch("m8flow_backend.routes.keycloak_controller.tenant_login_authorization_url")
    @patch("m8flow_backend.routes.keycloak_controller.TenantService.check_tenant_exists")
    def test_get_tenant_login_url_success(self, mock_check_tenant_exists, mock_auth_url, monkeypatch):
        monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
        mock_check_tenant_exists.return_value = {"exists": True, "tenant_id": "tenant-a-id"}
        mock_auth_url.return_value = "http://keycloak/realms/shared-users/protocol/openid-connect/auth"
        result, status = get_tenant_login_url("tenant-a")
        assert status == 200
        assert result["login_url"] == "http://keycloak/realms/shared-users/protocol/openid-connect/auth"
        assert result["realm"] == "shared-users"
        assert result["authentication_identifier"] == "shared-users"
        assert result["tenant_id"] == "tenant-a-id"
        mock_check_tenant_exists.assert_called_once_with("tenant-a")
        mock_auth_url.assert_called_once_with("shared-users")

    @patch("m8flow_backend.routes.keycloak_controller.TenantService.check_tenant_exists")
    def test_get_tenant_login_url_realm_not_found(self, mock_check_tenant_exists):
        mock_check_tenant_exists.return_value = {"exists": False}
        result, status = get_tenant_login_url("missing-tenant")
        assert status == 404
        assert "Tenant not found" in result["detail"]

    def test_get_tenant_login_url_missing_tenant(self):
        result, status = get_tenant_login_url("")
        assert status == 400
        assert "tenant" in result["detail"].lower()
        result2, status2 = get_tenant_login_url("   ")
        assert status2 == 400


class TestDeleteTenantRealm:
    """Tests for delete_tenant_realm (DELETE /tenant-realms/{realm_id}). Path realm_id is realm name (slug)."""

    @patch("m8flow_backend.routes.keycloak_controller.get_master_admin_token")
    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.delete_organization")
    def test_delete_tenant_realm_success(self, mock_delete_organization, mock_auth, mock_get_token, app, mock_user):
        mock_auth.return_value = True
        mock_get_token.return_value = "master-token"
        tenant_mock = MagicMock()
        tenant_mock.id = "organization-uuid-123"
        tenant_mock.slug = "tenant-a"
        with app.test_request_context():
            g.user = mock_user
            with patch(
                "m8flow_backend.routes.keycloak_controller.db"
            ) as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = (
                    tenant_mock
                )
                result, status = delete_tenant_realm("tenant-a")
            assert status == 200
            assert "deleted successfully" in result["message"]
            mock_delete_organization.assert_called_once_with(
                "organization-uuid-123",
                admin_token="master-token",
            )
            mock_db.session.delete.assert_called_once_with(tenant_mock)
            mock_db.session.commit.assert_called_once()

    @patch("m8flow_backend.routes.keycloak_controller.get_master_admin_token")
    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.get_organization_by_alias")
    @patch("m8flow_backend.routes.keycloak_controller.delete_organization")
    def test_delete_tenant_realm_no_tenant_row_still_deletes_keycloak(
        self,
        mock_delete_organization,
        mock_get_organization_by_alias,
        mock_auth,
        mock_get_token,
        app,
        mock_user,
    ):
        mock_auth.return_value = True
        mock_get_token.return_value = "master-token"
        mock_get_organization_by_alias.return_value = {
            "id": "organization-uuid-456",
            "alias": "missing-slug",
            "name": "Missing Slug",
        }
        with app.test_request_context():
            g.user = mock_user
            with patch(
                "m8flow_backend.routes.keycloak_controller.db"
            ) as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = None
                result, status = delete_tenant_realm("missing-slug")
            assert status == 200
            mock_get_organization_by_alias.assert_called_once_with(
                "missing-slug",
                admin_token="master-token",
            )
            mock_delete_organization.assert_called_once_with(
                "organization-uuid-456",
                admin_token="master-token",
            )
            mock_db.session.delete.assert_not_called()
            mock_db.session.commit.assert_not_called()

    def test_delete_tenant_realm_no_auth(self, app):
        with app.test_request_context():
            # g.user is not set
            with pytest.raises(ApiError) as exc:
                delete_tenant_realm("tenant-a")
            assert exc.value.status_code == 401
            assert exc.value.error_code == "not_authenticated"

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    def test_delete_tenant_realm_forbidden(self, mock_auth, app, mock_user):
        mock_auth.return_value = False
        with app.test_request_context():
            g.user = mock_user
            with pytest.raises(ApiError) as exc:
                delete_tenant_realm("tenant-a")
            assert exc.value.status_code == 403
            assert exc.value.error_code == "forbidden"

    @patch("m8flow_backend.routes.keycloak_controller.get_master_admin_token")
    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.delete_organization")
    def test_delete_tenant_realm_keycloak_failure_does_not_touch_postgres(
        self, mock_delete_organization, mock_auth, mock_get_token, app, mock_user
    ):
        """When Keycloak delete_organization raises, we do not delete from Postgres (inverted order)."""
        mock_auth.return_value = True
        mock_get_token.return_value = "master-token"
        tenant_mock = MagicMock()
        tenant_mock.id = "organization-uuid-123"
        tenant_mock.slug = "tenant-a"
        err = requests.HTTPError("502 Bad Gateway")
        err.response = MagicMock(status_code=502, text="Bad Gateway")
        mock_delete_organization.side_effect = err
        with app.test_request_context():
            g.user = mock_user
            with patch("m8flow_backend.routes.keycloak_controller.db") as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = tenant_mock
                result, status = delete_tenant_realm("tenant-a")
        assert status == 502
        mock_db.session.delete.assert_not_called()
        mock_db.session.commit.assert_not_called()


class TestUpdateTenantName:
    """Tests for update_tenant_name (PUT /tenants/{tenant_id})."""

    @patch("m8flow_backend.routes.keycloak_controller.get_master_admin_token")
    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    @patch("m8flow_backend.routes.keycloak_controller.update_organization")
    def test_update_tenant_name_success(
        self,
        mock_update_organization,
        mock_auth,
        mock_get_token,
        app,
        mock_user,
    ):
        mock_auth.return_value = True
        mock_get_token.return_value = "master-token"
        tenant_mock = MagicMock()
        tenant_mock.id = "organization-uuid-123"
        tenant_mock.slug = "tenant-a"
        tenant_mock.name = "Tenant A"

        with app.test_request_context():
            g.user = mock_user
            with patch("m8flow_backend.routes.keycloak_controller.db") as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = tenant_mock
                result, status = update_tenant_name("organization-uuid-123", {"name": "Tenant A+"})

        assert status == 200
        assert result["message"] == "Tenant name updated successfully"
        assert result["name"] == "Tenant A+"
        mock_update_organization.assert_called_once_with(
            "organization-uuid-123",
            alias="tenant-a",
            name="Tenant A+",
            admin_token="master-token",
        )
        assert tenant_mock.name == "Tenant A+"

    @patch("m8flow_backend.routes.keycloak_controller.AuthorizationService.user_has_permission")
    def test_update_tenant_name_missing_name(self, mock_auth, app, mock_user):
        mock_auth.return_value = True
        with app.test_request_context():
            g.user = mock_user
            result, status = update_tenant_name("organization-uuid-123", {"name": "   "})
        assert status == 400
        assert "name is required" in result["detail"]
