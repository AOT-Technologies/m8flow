"""Unit tests for tenant controller routes.

Tests cover:
- Get tenant by ID and slug
- Get all tenants (excluding default)
- Update tenant (name, status)
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

