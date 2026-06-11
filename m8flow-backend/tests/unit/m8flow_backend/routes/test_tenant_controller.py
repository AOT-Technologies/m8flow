"""Unit tests for tenant controller routes.

Tests cover:
- Get tenant by ID and slug
- Get all tenants
- Update tenant (name, status)
- Permission checks
- Error handling
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

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
                now = int(datetime.now(timezone.utc).timestamp())
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="get-tenant-1",
                    name="Get Tenant",
                    slug="get-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin",
                    created_at_in_seconds=now,
                    updated_at_in_seconds=now,
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

    def test_get_tenant_by_id_missing_default_returns_not_found(self, app, mock_admin_user):
        """Legacy default tenant id now behaves like any other missing tenant."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                
                response = tenant_controller.get_tenant_by_id("default")
                assert response.status_code == 404
                assert response.get_json()["error_code"] == "tenant_not_found"

    def test_get_tenant_by_slug_success(self, app, mock_admin_user):
        """Test successfully retrieving tenant by slug."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                now = int(datetime.now(timezone.utc).timestamp())
                
                # Create tenant
                tenant = M8flowTenantModel(
                    id="slug-tenant-1",
                    name="Slug Tenant",
                    slug="slug-tenant",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin",
                    created_at_in_seconds=now,
                    updated_at_in_seconds=now,
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

    def test_get_all_tenants_returns_all_rows(self, app, mock_admin_user):
        """Test that get_all_tenants returns all tenant rows."""
        with app.app_context():
            with app.test_request_context("/"):
                g.user = mock_admin_user
                now = int(datetime.now(timezone.utc).timestamp())
                
                tenant1 = M8flowTenantModel(
                    id="tenant-1",
                    name="Tenant One",
                    slug="tenant-one",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin",
                    created_at_in_seconds=now,
                    updated_at_in_seconds=now,
                )
                tenant2 = M8flowTenantModel(
                    id="tenant-2",
                    name="Tenant Two",
                    slug="tenant-two",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin",
                    created_at_in_seconds=now,
                    updated_at_in_seconds=now,
                )
                db.session.add(tenant1)
                db.session.add(tenant2)
                db.session.commit()
                
                # Get all tenants
                response = tenant_controller.get_all_tenants()
                assert response.status_code == 200
                
                data = response.get_json()
                assert len(data) == 2
                tenant_ids = {t["id"] for t in data}
                assert tenant_ids == {"tenant-1", "tenant-2"}
