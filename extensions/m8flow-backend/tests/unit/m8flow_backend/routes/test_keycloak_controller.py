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

from m8flow_backend.routes.keycloak_controller import (  # noqa: E402
    create_realm,
    create_user_in_realm,
    delete_tenant_realm,
    get_tenant_login_url,
    tenant_login,
)


class TestCreateRealm:
    """Tests for create_realm (POST /tenant-realms)."""

    @patch("m8flow_backend.routes.keycloak_controller.create_tenant_if_not_exists")
    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_success(self, mock_create_realm, mock_create_tenant):
        mock_create_realm.return_value = {
            "realm": "tenant-b",
            "displayName": "Tenant B",
            "keycloak_realm_id": "uuid-tenant-b-123",
        }
        body = {"realm_id": "tenant-b", "display_name": "Tenant B"}
        result, status = create_realm(body)
        assert status == 201
        assert result["realm"] == "tenant-b"
        assert result["displayName"] == "Tenant B"
        assert result["id"] == "uuid-tenant-b-123"
        assert result["keycloak_realm_id"] == "uuid-tenant-b-123"
        mock_create_realm.assert_called_once_with(
            realm_id="tenant-b",
            display_name="Tenant B",
        )
        mock_create_tenant.assert_called_once_with(
            "uuid-tenant-b-123",
            name="Tenant B",
            slug="tenant-b",
        )

    @patch("m8flow_backend.routes.keycloak_controller.create_tenant_if_not_exists")
    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_success_no_display_name(self, mock_create_realm, mock_create_tenant):
        mock_create_realm.return_value = {
            "realm": "tenant-c",
            "displayName": "tenant-c",
            "keycloak_realm_id": "uuid-tenant-c-456",
        }
        body = {"realm_id": "tenant-c"}
        result, status = create_realm(body)
        assert status == 201
        assert result["id"] == "uuid-tenant-c-456"
        mock_create_realm.assert_called_once_with(realm_id="tenant-c", display_name=None)
        mock_create_tenant.assert_called_once_with(
            "uuid-tenant-c-456",
            name="tenant-c",
            slug="tenant-c",
        )

    def test_create_realm_missing_realm_id(self):
        result, status = create_realm({})
        assert status == 400
        assert "realm_id" in result["detail"]

    def test_create_realm_empty_realm_id(self):
        result, status = create_realm({"realm_id": "   "})
        assert status == 400
        assert "realm_id" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_http_409(self, mock_create_realm):
        resp = MagicMock()
        resp.status_code = 409
        resp.text = "Realm already exists"
        mock_create_realm.side_effect = requests.exceptions.HTTPError(response=resp)
        result, status = create_realm({"realm_id": "tenant-b"})
        assert status == 409
        assert "already exists" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_http_500(self, mock_create_realm):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal error"
        mock_create_realm.side_effect = requests.exceptions.HTTPError(response=resp)
        result, status = create_realm({"realm_id": "tenant-b"})
        assert status == 500
        assert "Internal error" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_value_error(self, mock_create_realm):
        mock_create_realm.side_effect = ValueError("Invalid realm_id")
        result, status = create_realm({"realm_id": "tenant-b"})
        assert status == 400
        assert "Invalid realm_id" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.create_realm_from_template")
    def test_create_realm_file_not_found(self, mock_create_realm):
        mock_create_realm.side_effect = FileNotFoundError("Template not found")
        result, status = create_realm({"realm_id": "tenant-b"})
        assert status == 400
        assert "Template" in result["detail"]


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
    @patch("m8flow_backend.routes.keycloak_controller.realm_exists")
    def test_get_tenant_login_url_success(self, mock_realm_exists, mock_auth_url):
        mock_realm_exists.return_value = True
        mock_auth_url.return_value = "http://keycloak/realms/tenant-a/protocol/openid-connect/auth"
        result, status = get_tenant_login_url("tenant-a")
        assert status == 200
        assert result["login_url"] == "http://keycloak/realms/tenant-a/protocol/openid-connect/auth"
        assert result["realm"] == "tenant-a"
        mock_realm_exists.assert_called_once_with("tenant-a")
        mock_auth_url.assert_called_once_with("tenant-a")

    @patch("m8flow_backend.routes.keycloak_controller.realm_exists")
    def test_get_tenant_login_url_realm_not_found(self, mock_realm_exists):
        mock_realm_exists.return_value = False
        result, status = get_tenant_login_url("missing-tenant")
        assert status == 404
        assert "Tenant realm not found" in result["detail"]

    def test_get_tenant_login_url_missing_tenant(self):
        result, status = get_tenant_login_url("")
        assert status == 400
        assert "tenant" in result["detail"].lower()
        result2, status2 = get_tenant_login_url("   ")
        assert status2 == 400


class TestDeleteTenantRealm:
    """Tests for delete_tenant_realm (DELETE /tenant-realms/{realm_id}). Path realm_id is realm name (slug)."""

    @patch("m8flow_backend.routes.keycloak_controller.delete_realm")
    @patch("m8flow_backend.routes.keycloak_controller.verify_admin_token")
    def test_delete_tenant_realm_success(self, mock_verify, mock_delete_realm):
        from flask import Flask
        app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
        mock_verify.return_value = True
        tenant_mock = MagicMock()
        tenant_mock.id = "keycloak-uuid-123"
        with app.test_request_context(headers={"Authorization": "Bearer valid-token"}):
            with patch(
                "m8flow_backend.routes.keycloak_controller.db"
            ) as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = (
                    tenant_mock
                )
                result, status = delete_tenant_realm("tenant-a")
            assert status == 200
            assert "deleted successfully" in result["message"]
            mock_delete_realm.assert_called_once_with("tenant-a", admin_token="valid-token")
            mock_db.session.delete.assert_called_once_with(tenant_mock)
            mock_db.session.commit.assert_called_once()

    @patch("m8flow_backend.routes.keycloak_controller.delete_realm")
    @patch("m8flow_backend.routes.keycloak_controller.verify_admin_token")
    def test_delete_tenant_realm_no_tenant_row_still_deletes_keycloak(
        self, mock_verify, mock_delete_realm
    ):
        from flask import Flask
        app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
        mock_verify.return_value = True
        with app.test_request_context(headers={"Authorization": "Bearer valid-token"}):
            with patch(
                "m8flow_backend.routes.keycloak_controller.db"
            ) as mock_db:
                mock_db.session.query.return_value.filter.return_value.one_or_none.return_value = None
                result, status = delete_tenant_realm("missing-slug")
            assert status == 200
            mock_delete_realm.assert_called_once_with("missing-slug", admin_token="valid-token")
            mock_db.session.delete.assert_not_called()
            mock_db.session.commit.assert_not_called()

    def test_delete_tenant_realm_no_auth(self):
        from flask import Flask
        app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
        with app.test_request_context(headers={}):
            result, status = delete_tenant_realm("tenant-a")
        assert status == 401
        assert "Authorization" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.verify_admin_token")
    def test_delete_tenant_realm_invalid_token(self, mock_verify):
        from flask import Flask
        app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
        mock_verify.return_value = False
        with app.test_request_context(headers={"Authorization": "Bearer bad-token"}):
            result, status = delete_tenant_realm("tenant-a")
        assert status == 401
        assert "Invalid" in result["detail"]

    @patch("m8flow_backend.routes.keycloak_controller.delete_realm")
    @patch("m8flow_backend.routes.keycloak_controller.verify_admin_token")
    def test_delete_tenant_realm_keycloak_failure_does_not_touch_postgres(
        self, mock_verify, mock_delete_realm
    ):
        """When Keycloak delete_realm raises, we do not delete from Postgres (inverted order)."""
        from flask import Flask
        app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
        mock_verify.return_value = True
        err = requests.HTTPError("502 Bad Gateway")
        err.response = MagicMock(status_code=502, text="Bad Gateway")
        mock_delete_realm.side_effect = err
        with app.test_request_context(headers={"Authorization": "Bearer valid-token"}):
            with patch("m8flow_backend.routes.keycloak_controller.db") as mock_db:
                result, status = delete_tenant_realm("tenant-a")
        assert status == 502
        mock_db.session.delete.assert_not_called()
        mock_db.session.commit.assert_not_called()
