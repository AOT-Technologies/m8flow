"""Unit tests for M8flowTenantModel.

Tests cover:
- Model creation with required fields
- Slug uniqueness enforcement at database level
- Status enum validation (ACTIVE, INACTIVE, DELETED)
- Timestamp auto-population (created_at_in_seconds, updated_at_in_seconds)
- Bookkeeping fields (created_by, modified_by)
- Database constraints and validation
"""
import sys
import time
from pathlib import Path
from datetime import datetime

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

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
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners  # noqa: E402


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
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


class TestM8flowTenantModel:
    """Test suite for M8flowTenantModel."""

    def test_create_tenant_with_all_required_fields(self, app):
        """Test creating a tenant with all required fields."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="test-tenant-1",
                name="Test Tenant",
                slug="test-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Verify tenant was created
            saved_tenant = M8flowTenantModel.query.filter_by(id="test-tenant-1").first()
            assert saved_tenant is not None
            assert saved_tenant.name == "Test Tenant"
            assert saved_tenant.slug == "test-tenant"
            assert saved_tenant.status == TenantStatus.ACTIVE
            assert saved_tenant.created_by == "admin"
            assert saved_tenant.modified_by == "admin"

    def test_slug_uniqueness_constraint(self, app):
        """Test that slug uniqueness is enforced at database level."""
        with app.app_context():
            # Create first tenant
            tenant1 = M8flowTenantModel(
                id="tenant-1",
                name="Tenant One",
                slug="unique-slug",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant1)
            db.session.commit()
            
            # Attempt to create second tenant with same slug
            tenant2 = M8flowTenantModel(
                id="tenant-2",
                name="Tenant Two",
                slug="unique-slug",  # Duplicate slug
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant2)
            
            # Should raise IntegrityError due to unique constraint
            with pytest.raises(IntegrityError):
                db.session.commit()
            
            db.session.rollback()

    def test_tenant_status_enum_values(self, app):
        """Test that all status enum values are supported."""
        with app.app_context():
            # Test ACTIVE status
            tenant_active = M8flowTenantModel(
                id="tenant-active",
                name="Active Tenant",
                slug="active-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant_active)
            db.session.commit()
            assert tenant_active.status == TenantStatus.ACTIVE
            
            # Test INACTIVE status
            tenant_inactive = M8flowTenantModel(
                id="tenant-inactive",
                name="Inactive Tenant",
                slug="inactive-tenant",
                status=TenantStatus.INACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant_inactive)
            db.session.commit()
            assert tenant_inactive.status == TenantStatus.INACTIVE
            
            # Test DELETED status
            tenant_deleted = M8flowTenantModel(
                id="tenant-deleted",
                name="Deleted Tenant",
                slug="deleted-tenant",
                status=TenantStatus.DELETED,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant_deleted)
            db.session.commit()
            assert tenant_deleted.status == TenantStatus.DELETED

    def test_status_transition_active_to_inactive(self, app):
        """Test transitioning tenant status from ACTIVE to INACTIVE."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="tenant-transition",
                name="Transition Tenant",
                slug="transition-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Transition to INACTIVE
            tenant.status = TenantStatus.INACTIVE
            tenant.modified_by = "admin-2"
            db.session.commit()
            
            # Verify transition
            updated_tenant = M8flowTenantModel.query.filter_by(id="tenant-transition").first()
            assert updated_tenant.status == TenantStatus.INACTIVE
            assert updated_tenant.modified_by == "admin-2"

    def test_status_transition_to_deleted(self, app):
        """Test soft delete by transitioning status to DELETED."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="tenant-to-delete",
                name="To Delete Tenant",
                slug="to-delete-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Soft delete
            tenant.status = TenantStatus.DELETED
            tenant.modified_by = "admin"
            db.session.commit()
            
            # Verify soft delete
            deleted_tenant = M8flowTenantModel.query.filter_by(id="tenant-to-delete").first()
            assert deleted_tenant is not None  # Still exists in DB
            assert deleted_tenant.status == TenantStatus.DELETED

    def test_timestamps_auto_populated(self, app):
        """Test that created_at_in_seconds and updated_at_in_seconds are auto-populated."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="tenant-timestamps",
                name="Timestamp Tenant",
                slug="timestamp-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Verify timestamps are set and are ints
            assert tenant.created_at_in_seconds is not None
            assert isinstance(tenant.created_at_in_seconds, int)
            assert tenant.created_at_in_seconds > 0

            assert tenant.updated_at_in_seconds is not None
            assert isinstance(tenant.updated_at_in_seconds, int)
            assert tenant.updated_at_in_seconds > 0

            # Verify timestamps are recent (within last minute)
            from datetime import timedelta

            now_seconds = int(round(time.time()))
            time_diff_seconds = int(timedelta(minutes=1).total_seconds())
            assert abs(tenant.created_at_in_seconds - now_seconds) < time_diff_seconds
            assert abs(tenant.updated_at_in_seconds - now_seconds) < time_diff_seconds

    def test_bookkeeping_fields_required(self, app):
        """Test that created_by and modified_by fields are required."""
        with app.app_context():
            # Attempt to create tenant without created_by
            tenant = M8flowTenantModel(
                id="tenant-no-created-by",
                name="No Created By",
                slug="no-created-by",
                status=TenantStatus.ACTIVE,
                modified_by="admin"
            )
            db.session.add(tenant)
            
            # Should raise IntegrityError due to NOT NULL constraint
            with pytest.raises(IntegrityError):
                db.session.commit()
            
            db.session.rollback()

    def test_tenant_repr(self, app):
        """Test the string representation of tenant model."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="tenant-repr",
                name="Repr Tenant",
                slug="repr-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            
            expected_repr = "<M8flowTenantModel(name=Repr Tenant, slug=repr-tenant, status=TenantStatus.ACTIVE)>"
            assert repr(tenant) == expected_repr

    def test_query_by_slug(self, app):
        """Test querying tenants by slug."""
        with app.app_context():
            tenant = M8flowTenantModel(
                id="tenant-query",
                name="Query Tenant",
                slug="query-tenant",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Query by slug
            found_tenant = M8flowTenantModel.query.filter_by(slug="query-tenant").first()
            assert found_tenant is not None
            assert found_tenant.id == "tenant-query"
            assert found_tenant.name == "Query Tenant"

    def test_multiple_tenants_different_slugs(self, app):
        """Test creating multiple tenants with different slugs."""
        with app.app_context():
            tenants = [
                M8flowTenantModel(
                    id=f"tenant-{i}",
                    name=f"Tenant {i}",
                    slug=f"tenant-{i}",
                    status=TenantStatus.ACTIVE,
                    created_by="admin",
                    modified_by="admin"
                )
                for i in range(1, 4)
            ]
            
            for tenant in tenants:
                db.session.add(tenant)
            db.session.commit()
            
            # Verify all tenants were created
            all_tenants = M8flowTenantModel.query.all()
            assert len(all_tenants) == 3
            
            # Verify slugs are unique
            slugs = [t.slug for t in all_tenants]
            assert len(slugs) == len(set(slugs))  # All slugs are unique

    def test_default_status_is_active(self, app):
        """Test that default status is ACTIVE when not specified."""
        with app.app_context():
            # Note: This test depends on how the model handles defaults
            # The model definition shows default=TenantStatus.ACTIVE
            tenant = M8flowTenantModel(
                id="tenant-default-status",
                name="Default Status Tenant",
                slug="default-status-tenant",
                # status not specified
                created_by="admin",
                modified_by="admin"
            )
            db.session.add(tenant)
            db.session.commit()
            
            # Verify default status is ACTIVE
            saved_tenant = M8flowTenantModel.query.filter_by(id="tenant-default-status").first()
            assert saved_tenant.status == TenantStatus.ACTIVE
