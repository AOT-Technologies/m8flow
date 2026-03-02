"""Unit tests for tenant controller routes.

Tests cover:
- Tenant creation with validation
- Slug uniqueness enforcement
- Get tenant by ID and slug
- Get all tenants (excluding default)
- Update tenant (name, status)
- Soft delete tenant
- Permission checks
- Default tenant protection
- Error handling
"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from flask import Flask, g

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.routes import tenant_controller  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402


@pytest.fixture
def app():
    """Create Flask app with in-memory database for testing."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = Mock()
    user.username = "admin"
    user.id = 1
    return user


class TestTenantController:
    """Test suite for tenant controller routes."""

    def test_create_tenant_success(self, app, mock_admin_user):
        """Test successful tenant creation."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                body = {
                    "id": "test-tenant-1",
                    "name": "Test Tenant",
                    "slug": "test-tenant",
                    "status": "ACTIVE"
                }
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 201
                
                # Verify tenant was created in database
                tenant = M8flowTenantModel.query.filter_by(slug="test-tenant").first()
                assert tenant is not None
                assert tenant.name == "Test Tenant"
                assert tenant.status == TenantStatus.ACTIVE

    def test_create_tenant_without_name_fails(self, app, mock_admin_user):
        """Test that creating tenant without name raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                body = {
                    "slug": "test-tenant"
                }
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 400
                assert response.get_json()["error_code"] == "missing_name"

    def test_create_tenant_without_slug_fails(self, app, mock_admin_user):
        """Test that creating tenant without slug raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                body = {
                    "name": "Test Tenant"
                }
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 400
                assert response.get_json()["error_code"] == "missing_slug"

    def test_create_tenant_duplicate_slug_fails(self, app, mock_admin_user):
        """Test that creating tenant with duplicate slug raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create first tenant
                tenant1 = M8flowTenantModel(
                    id="tenant-1",
                    name="Tenant One",
                    slug="duplicate-slug",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant1)
                db.session.commit()
                
                # Attempt to create second tenant with same slug
                body = {
                    "name": "Tenant Two",
                    "slug": "duplicate-slug"
                }
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 409
                assert response.get_json()["error_code"] == "tenant_slug_exists"

    def test_create_tenant_generates_id_if_not_provided(self, app, mock_admin_user):
        """Test that tenant ID is auto-generated if not provided."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                body = {
                    "name": "Auto ID Tenant",
                    "slug": "auto-id-tenant"
                }
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 201
                
                # Verify tenant has an ID
                tenant = M8flowTenantModel.query.filter_by(slug="auto-id-tenant").first()
                assert tenant is not None
                assert tenant.id is not None
                assert len(tenant.id) > 0

    def test_get_tenant_by_id_success(self, app, mock_admin_user):
        """Test successfully retrieving tenant by ID."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="get-tenant-1",
                    name="Get Tenant",
                    slug="get-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Get tenant by ID
                response = tenant_controller.get_tenant_by_id("get-tenant-1")
                assert response.status_code == 200

    def test_get_tenant_by_id_not_found(self, app, mock_admin_user):
        """Test getting non-existent tenant by ID raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                response = tenant_controller.get_tenant_by_id("non-existent")
                assert response.status_code == 404
                assert response.get_json()["error_code"] == "tenant_not_found"

    def test_get_tenant_by_id_default_forbidden(self, app, mock_admin_user):
        """Test that getting default tenant by ID is forbidden."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                response = tenant_controller.get_tenant_by_id("default")
                assert response.status_code == 403
                assert response.get_json()["error_code"] == "forbidden_tenant"

    def test_get_tenant_by_slug_success(self, app, mock_admin_user):
        """Test successfully retrieving tenant by slug."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="slug-tenant-1",
                    name="Slug Tenant",
                    slug="slug-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Get tenant by slug
                response = tenant_controller.get_tenant_by_slug("slug-tenant")
                assert response.status_code == 200

    def test_get_tenant_by_slug_not_found(self, app, mock_admin_user):
        """Test getting non-existent tenant by slug raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                response = tenant_controller.get_tenant_by_slug("non-existent-slug")
                assert response.status_code == 404
                assert response.get_json()["error_code"] == "tenant_not_found"

    def test_get_all_tenants_excludes_default(self, app, mock_admin_user):
        """Test that get_all_tenants excludes the default tenant."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create default tenant
                default_tenant = M8flowTenantModel(
                    id="default",
                    name="Default Tenant",
                    slug="default",
                    status=TenantStatus.ACTIVE,
                    created_by="system",
                    modified_by="system"
                )
                db.session.add(default_tenant)
                
                # Create regular tenants
                tenant1 = M8flowTenantModel(
                    id="tenant-1",
                    name="Tenant One",
                    slug="tenant-one",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                tenant2 = M8flowTenantModel(
                    id="tenant-2",
                    name="Tenant Two",
                    slug="tenant-two",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant1)
                db.session.add(tenant2)
                db.session.commit()
                
                # Get all tenants
                response = tenant_controller.get_all_tenants()
                assert response.status_code == 200
                
                # Verify default tenant is excluded
                data = response.get_json()
                assert len(data) == 2
                tenant_ids = [t["id"] for t in data]
                assert "default" not in tenant_ids

    def test_update_tenant_name_success(self, app, mock_admin_user):
        """Test successfully updating tenant name."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="update-tenant-1",
                    name="Original Name",
                    slug="update-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Update name
                body = {"name": "Updated Name"}
                response = tenant_controller.update_tenant("update-tenant-1", body)
                assert response.status_code == 200
                
                # Verify update
                updated_tenant = M8flowTenantModel.query.filter_by(id="update-tenant-1").first()
                assert updated_tenant.name == "Updated Name"

    def test_update_tenant_status_success(self, app, mock_admin_user):
        """Test successfully updating tenant status."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="status-tenant-1",
                    name="Status Tenant",
                    slug="status-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Update status
                body = {"status": "INACTIVE"}
                response = tenant_controller.update_tenant("status-tenant-1", body)
                assert response.status_code == 200
                
                # Verify update
                updated_tenant = M8flowTenantModel.query.filter_by(id="status-tenant-1").first()
                assert updated_tenant.status == TenantStatus.INACTIVE

    def test_update_tenant_slug_forbidden(self, app, mock_admin_user):
        """Test that updating tenant slug is forbidden."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="immutable-slug-1",
                    name="Immutable Slug",
                    slug="original-slug",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Attempt to update slug
                body = {"slug": "new-slug"}
                
                response = tenant_controller.update_tenant("immutable-slug-1", body)
                assert response.status_code == 400
                assert response.get_json()["error_code"] == "slug_update_forbidden"

    def test_update_deleted_tenant_forbidden(self, app, mock_admin_user):
        """Test that updating a deleted tenant is forbidden."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create deleted tenant
                tenant = M8flowTenantModel(
                    id="deleted-tenant-1",
                    name="Deleted Tenant",
                    slug="deleted-tenant",
                    status=TenantStatus.DELETED,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Attempt to update
                body = {"name": "New Name"}
                
                response = tenant_controller.update_tenant("deleted-tenant-1", body)
                assert response.status_code == 400
                assert response.get_json()["error_code"] == "tenant_deleted"

    def test_delete_tenant_soft_delete(self, app, mock_admin_user):
        """Test soft deleting a tenant."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="delete-tenant-1",
                    name="Delete Tenant",
                    slug="delete-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Delete tenant
                response = tenant_controller.delete_tenant("delete-tenant-1")
                assert response.status_code == 200
                
                # Verify soft delete
                deleted_tenant = M8flowTenantModel.query.filter_by(id="delete-tenant-1").first()
                assert deleted_tenant is not None  # Still exists in DB
                assert deleted_tenant.status == TenantStatus.DELETED

    def test_delete_already_deleted_tenant_fails(self, app, mock_admin_user):
        """Test that deleting an already deleted tenant raises error."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                # Create deleted tenant
                tenant = M8flowTenantModel(
                    id="already-deleted-1",
                    name="Already Deleted",
                    slug="already-deleted",
                    status=TenantStatus.DELETED,
                    created_by="admin",
                    modified_by="admin"
                )
                db.session.add(tenant)
                db.session.commit()
                
                # Attempt to delete again
                response = tenant_controller.delete_tenant("already-deleted-1")
                assert response.status_code == 400
                assert response.get_json()["error_code"] == "tenant_already_deleted"

    def test_delete_default_tenant_forbidden(self, app, mock_admin_user):
        """Test that deleting default tenant is forbidden."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                response = tenant_controller.delete_tenant("default")
                assert response.status_code == 403
                assert response.get_json()["error_code"] == "forbidden_tenant"

    def test_permission_check_no_user(self, app):
        """Test that operations fail when user is not authenticated."""
        with app.app_context():
            with app.test_request_context("/"):
                # No user in g
                
                body = {"name": "Test", "slug": "test"}
                
                response = tenant_controller.create_tenant(body)
                assert response.status_code == 401
                assert response.get_json()["error_code"] == "not_authenticated"

    def test_permission_check_delete_no_user(self, app):
        """Test that delete fails when user is not authenticated."""
        with app.app_context():
            with app.test_request_context("/"):
                # No user in g
                
                response = tenant_controller.delete_tenant("some-tenant")
                assert response.status_code == 401
                assert response.get_json()["error_code"] == "not_authenticated"

    def test_permission_check_update_no_user(self, app):
        """Test that update fails when user is not authenticated."""
        with app.app_context():
            with app.test_request_context("/"):
                # No user in g
                
                body = {"name": "New Name"}
                response = tenant_controller.update_tenant("some-tenant", body)
                assert response.status_code == 401
                assert response.get_json()["error_code"] == "not_authenticated"
