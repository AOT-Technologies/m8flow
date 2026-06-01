"""Unit tests for tenancy module (create_tenant_if_not_exists with slug)."""
import sys
from pathlib import Path

import pytest
from flask import Flask, g

extension_root = Path(__file__).resolve().parents[3]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: E402
from m8flow_backend.models.reference_cache import ReferenceCacheModel  # noqa: E402
from m8flow_backend.services import tenant_scoping_patch  # noqa: E402
from m8flow_backend.tenancy import create_tenant_if_not_exists  # noqa: E402
from m8flow_backend.tenancy import get_tenant_id  # noqa: E402
from m8flow_backend.tenancy import path_matches_any_prefix  # noqa: E402
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


def test_path_matches_any_prefix_requires_boundary():
    prefixes = ("/v1.0/login", "/login")

    assert path_matches_any_prefix("/v1.0/login", prefixes)
    assert path_matches_any_prefix("/v1.0/login/", prefixes)
    assert path_matches_any_prefix("/v1.0/login/oidc", prefixes)

    # Regression: `/v1.0/login_return` must not match `/v1.0/login`.
    assert not path_matches_any_prefix("/v1.0/login_return", prefixes)


def test_get_tenant_id_raises_on_protected_request_without_tenant_context():
    app = Flask(__name__)
    with app.test_request_context("/v1.0/tasks"):
        with pytest.raises(RuntimeError, match="Missing tenant id in request context"):
            get_tenant_id(warn_on_default=False)


def test_get_tenant_id_raises_on_exempt_request_without_tenant_context():
    app = Flask(__name__)
    with app.test_request_context("/v1.0/status"):
        with pytest.raises(RuntimeError, match="Missing tenant id in request context"):
            get_tenant_id(warn_on_default=False)


def test_is_tenant_context_exempt_request_recognizes_global_request_flag():
    """
    Master-realm sign-ins, /login_return callbacks, and other intentionally
    tenant-less requests are tagged with ``g._m8flow_global_request = True`` by
    the tenant resolver.  ``is_tenant_context_exempt_request()`` must report
    True for these requests so tenant-scoped DB query patches (e.g.
    ReferenceCacheModel.basic_query) skip the tenant filter instead of raising
    "missing tenant context for tenant-scoped operation".
    """
    from flask import g

    from m8flow_backend.tenancy import is_tenant_context_exempt_request

    app = Flask(__name__)
    with app.test_request_context("/v1.0/extensions"):
        # Default state: not exempt.
        assert is_tenant_context_exempt_request() is False

        # Marked global by the resolver: now exempt.
        g._m8flow_global_request = True
        assert is_tenant_context_exempt_request() is True

        # Cleared again: not exempt.
        g._m8flow_global_request = False
        assert is_tenant_context_exempt_request() is False


def test_reference_cache_basic_query_skips_tenant_requirement_for_master_realm_request(app):
    """
    Regression: /extensions can hit ReferenceCacheModel.basic_query() before the
    tenant resolver tags a master-realm request as global. The fallback
    detection must treat the cached master-realm token as intentionally
    tenant-less instead of raising "Missing tenant context for tenant-scoped
    operation."
    """
    tenant_scoping_patch.apply()

    with app.test_request_context("/v1.0/extensions", headers={"Authorization": "Bearer master-token"}):
        g._m8flow_decoded_token = {
            "iss": "http://localhost:7002/realms/master",
            "preferred_username": "super-admin",
            "groups": ["super-admin"],
        }

        assert ReferenceCacheModel.basic_query().all() == []
