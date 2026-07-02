"""Unit tests for TenantService.name_exists (tenant name uniqueness)."""
# ruff: noqa: E402
import sys
from pathlib import Path

import pytest
from flask import Flask

# Ensure m8flow_backend and spiffworkflow_backend are importable
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus
from m8flow_backend.services.tenant_service import TenantService
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.db import add_listeners


@pytest.fixture
def app():
    """Flask app backed by an in-memory database (overrides the bare conftest app)."""
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


def _add_tenant(tenant_id: str, name: str, slug: str) -> None:
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=name,
        slug=slug,
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()


class TestTenantNameExists:
    def test_returns_false_when_no_tenant_has_name(self, app):
        with app.app_context():
            _add_tenant("t1", "Acme Corp", "acme-corp")
            assert TenantService.name_exists("Globex") is False

    def test_returns_true_for_exact_match(self, app):
        with app.app_context():
            _add_tenant("t1", "Acme Corp", "acme-corp")
            assert TenantService.name_exists("Acme Corp") is True

    def test_match_is_case_insensitive_and_trimmed(self, app):
        with app.app_context():
            _add_tenant("t1", "Acme Corp", "acme-corp")
            assert TenantService.name_exists("  acme corp  ") is True
            assert TenantService.name_exists("ACME CORP") is True

    def test_excludes_given_tenant_id(self, app):
        with app.app_context():
            _add_tenant("t1", "Acme Corp", "acme-corp")
            assert TenantService.name_exists("Acme Corp", exclude_tenant_id="t1") is False
            _add_tenant("t2", "Globex", "globex")
            assert TenantService.name_exists("Acme Corp", exclude_tenant_id="t2") is True

    def test_blank_name_is_never_a_duplicate(self, app):
        with app.app_context():
            _add_tenant("t1", "Acme Corp", "acme-corp")
            assert TenantService.name_exists("") is False
            assert TenantService.name_exists("   ") is False
