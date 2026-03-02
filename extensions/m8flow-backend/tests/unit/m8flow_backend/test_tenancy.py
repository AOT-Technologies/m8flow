"""Unit tests for tenancy module (create_tenant_if_not_exists with slug)."""
import sys
from pathlib import Path

import pytest
from flask import Flask

extension_root = Path(__file__).resolve().parents[3]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: E402
from m8flow_backend.tenancy import create_tenant_if_not_exists  # noqa: E402
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


def test_create_tenant_if_not_exists_with_slug_stores_keycloak_id_and_slug(app):
    """create_tenant_if_not_exists(tenant_id, name=..., slug=...) stores id=tenant_id and slug=slug."""
    keycloak_realm_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    realm_name = "tenant-a"
    display_name = "Tenant A"

    with app.app_context():
        create_tenant_if_not_exists(
            keycloak_realm_id,
            name=display_name,
            slug=realm_name,
        )

        row = db.session.get(M8flowTenantModel, keycloak_realm_id)
        assert row is not None
        assert row.id == keycloak_realm_id
        assert row.slug == realm_name
        assert row.name == display_name


def test_create_tenant_if_not_exists_without_slug_uses_tenant_id_as_slug(app):
    """When slug is not provided, slug defaults to tenant_id (backward compatible)."""
    tenant_id = "legacy-tenant-id"

    with app.app_context():
        create_tenant_if_not_exists(tenant_id, name="Legacy Tenant")

        row = db.session.get(M8flowTenantModel, tenant_id)
        assert row is not None
        assert row.id == tenant_id
        assert row.slug == tenant_id
        assert row.name == "Legacy Tenant"


def test_create_tenant_if_not_exists_idempotent(app):
    """Calling create_tenant_if_not_exists again with same tenant_id does not duplicate."""
    keycloak_realm_id = "b2c3d4e5-f6a7-8901-bcde-f23456789012"

    with app.app_context():
        create_tenant_if_not_exists(keycloak_realm_id, name="Once", slug="once")
        create_tenant_if_not_exists(keycloak_realm_id, name="Twice", slug="twice")

        count = db.session.query(M8flowTenantModel).filter(M8flowTenantModel.id == keycloak_realm_id).count()
        assert count == 1
        row = db.session.get(M8flowTenantModel, keycloak_realm_id)
        assert row.name == "Once"
        assert row.slug == "once"
