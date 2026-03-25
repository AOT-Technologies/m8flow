# extensions/m8flow-backend/tests/unit/m8flow_backend/models/test_process_model_template.py
"""Tests for ProcessModelTemplateModel."""
import sys
from pathlib import Path

import pytest
from flask import Flask

extension_root = Path(__file__).resolve().parents[1]
repo_root = extension_root.parents[1]
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import model_override_patch

model_override_patch.apply()

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: E402
from m8flow_backend.models.template import TemplateModel, TemplateVisibility  # noqa: E402
from m8flow_backend.models.process_model_template import ProcessModelTemplateModel  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402

import spiffworkflow_backend.load_database_models  # noqa: F401,E402


def test_process_model_template_model_creation() -> None:
    """Test ProcessModelTemplateModel can be created and persisted."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Create a tenant first
        tenant = M8flowTenantModel(
            id="tenant-1",
            name="Test Tenant",
            slug="test-tenant",
            created_by="test",
            modified_by="test",
        )
        db.session.add(tenant)
        db.session.commit()

        # Create a template
        template = TemplateModel(
            template_key="test-template",
            version="V1",
            name="Test Template",
            m8f_tenant_id="tenant-1",
            visibility=TemplateVisibility.private.value,
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="testuser",
            modified_by="testuser",
        )
        db.session.add(template)
        db.session.commit()

        # Create provenance record
        provenance = ProcessModelTemplateModel(
            process_model_identifier="test-group/test-model",
            source_template_id=template.id,
            source_template_key="test-template",
            source_template_version="V1",
            source_template_name="Test Template",
            m8f_tenant_id="tenant-1",
            created_by="testuser",
        )
        db.session.add(provenance)
        db.session.commit()

        # Verify it was saved
        assert provenance.id is not None
        
        # Query it back
        retrieved = ProcessModelTemplateModel.query.filter_by(
            process_model_identifier="test-group/test-model"
        ).first()
        
        assert retrieved is not None
        assert retrieved.source_template_id == template.id
        assert retrieved.source_template_key == "test-template"
        assert retrieved.source_template_version == "V1"
        assert retrieved.source_template_name == "Test Template"
        assert retrieved.m8f_tenant_id == "tenant-1"
        assert retrieved.created_by == "testuser"


def test_process_model_template_model_unique_constraint() -> None:
    """Test ProcessModelTemplateModel enforces unique process_model_identifier."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Create a tenant
        tenant = M8flowTenantModel(
            id="tenant-1",
            name="Test Tenant",
            slug="test-tenant",
            created_by="test",
            modified_by="test",
        )
        db.session.add(tenant)
        db.session.commit()

        # Create a template
        template = TemplateModel(
            template_key="test-template",
            version="V1",
            name="Test Template",
            m8f_tenant_id="tenant-1",
            visibility=TemplateVisibility.private.value,
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="testuser",
            modified_by="testuser",
        )
        db.session.add(template)
        db.session.commit()

        # Create first provenance record
        provenance1 = ProcessModelTemplateModel(
            process_model_identifier="test-group/test-model",
            source_template_id=template.id,
            source_template_key="test-template",
            source_template_version="V1",
            source_template_name="Test Template",
            m8f_tenant_id="tenant-1",
            created_by="testuser",
        )
        db.session.add(provenance1)
        db.session.commit()

        # Try to create duplicate - should fail
        provenance2 = ProcessModelTemplateModel(
            process_model_identifier="test-group/test-model",  # Same identifier
            source_template_id=template.id,
            source_template_key="test-template",
            source_template_version="V2",
            source_template_name="Test Template",
            m8f_tenant_id="tenant-1",
            created_by="testuser",
        )
        db.session.add(provenance2)
        
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()


def test_process_model_template_model_serialized() -> None:
    """Test ProcessModelTemplateModel.serialized() returns expected dict."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        provenance = ProcessModelTemplateModel(
            process_model_identifier="test-group/test-model",
            source_template_id=1,
            source_template_key="test-template",
            source_template_version="V1",
            source_template_name="Test Template",
            m8f_tenant_id="tenant-1",
            created_by="testuser",
        )
        # Manually set audit fields for testing
        provenance.created_at_in_seconds = 1234567890
        provenance.updated_at_in_seconds = 1234567891

        serialized = provenance.serialized()

        assert serialized["process_model_identifier"] == "test-group/test-model"
        assert serialized["source_template_id"] == 1
        assert serialized["source_template_key"] == "test-template"
        assert serialized["source_template_version"] == "V1"
        assert serialized["source_template_name"] == "Test Template"
        assert serialized["m8f_tenant_id"] == "tenant-1"
        assert serialized["created_by"] == "testuser"
        assert serialized["created_at_in_seconds"] == 1234567890
        assert serialized["updated_at_in_seconds"] == 1234567891


def test_process_model_template_model_relationship() -> None:
    """Test ProcessModelTemplateModel has relationship to TemplateModel."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Create a tenant
        tenant = M8flowTenantModel(
            id="tenant-1",
            name="Test Tenant",
            slug="test-tenant",
            created_by="test",
            modified_by="test",
        )
        db.session.add(tenant)
        db.session.commit()

        # Create a template
        template = TemplateModel(
            template_key="test-template",
            version="V1",
            name="Test Template",
            m8f_tenant_id="tenant-1",
            visibility=TemplateVisibility.private.value,
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="testuser",
            modified_by="testuser",
        )
        db.session.add(template)
        db.session.commit()

        # Create provenance record
        provenance = ProcessModelTemplateModel(
            process_model_identifier="test-group/test-model",
            source_template_id=template.id,
            source_template_key="test-template",
            source_template_version="V1",
            source_template_name="Test Template",
            m8f_tenant_id="tenant-1",
            created_by="testuser",
        )
        db.session.add(provenance)
        db.session.commit()

        # Verify relationship works
        retrieved = ProcessModelTemplateModel.query.filter_by(
            process_model_identifier="test-group/test-model"
        ).first()
        
        assert retrieved is not None
        assert retrieved.source_template is not None
        assert retrieved.source_template.id == template.id
        assert retrieved.source_template.template_key == "test-template"
        assert retrieved.source_template.name == "Test Template"
