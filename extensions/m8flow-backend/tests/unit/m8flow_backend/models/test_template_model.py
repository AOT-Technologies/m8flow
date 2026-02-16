"""Unit tests for TemplateModel.

Focus:
- Spiff-standard timestamp auto-population (created_at_in_seconds, updated_at_in_seconds)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from flask import Flask

# Setup path for imports (mirrors other unit tests in this extension)
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.models.template import TemplateModel  # noqa: E402
from spiffworkflow_backend.models.user_group_assignment import (  # noqa: E402,F401
    UserGroupAssignmentModel,
)
from spiffworkflow_backend.models.db import db, add_listeners  # noqa: E402


@pytest.fixture
def app():
    """Create Flask app with in-memory database for testing."""
    app = Flask(__name__)
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


class TestTemplateModel:
    def test_timestamps_auto_populated_and_updated(self, app):
        with app.app_context():
            # Need a tenant row for FK.
            tenant = M8flowTenantModel(
                id="tenant-1",
                name="Tenant One",
                slug="tenant-one",
                status=TenantStatus.ACTIVE,
                created_by="admin",
                modified_by="admin",
            )
            db.session.add(tenant)
            db.session.commit()

            template = TemplateModel(
                template_key="test-key",
                version="V1",
                name="Test Template",
                description=None,
                tags=None,
                category=None,
                m8f_tenant_id=tenant.id,
                visibility="PRIVATE",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                status="draft",
                is_deleted=False,
                created_by="admin",
                modified_by="admin",
            )
            db.session.add(template)
            db.session.commit()

            assert isinstance(template.created_at_in_seconds, int)
            assert isinstance(template.updated_at_in_seconds, int)
            assert template.created_at_in_seconds > 0
            assert template.updated_at_in_seconds > 0

            now_seconds = int(round(time.time()))
            assert abs(template.created_at_in_seconds - now_seconds) < int(timedelta(minutes=1).total_seconds())

            # Updating a non-timestamp field should bump updated_at_in_seconds.
            before_update = template.updated_at_in_seconds
            template.name = "Renamed Template"
            db.session.commit()
            assert template.updated_at_in_seconds >= before_update

