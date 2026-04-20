# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_process_model_from_template.py
"""Tests for creating process models from templates and template provenance tracking."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask
from flask import g

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
from m8flow_backend.services.template_service import TemplateService  # noqa: E402
from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

import spiffworkflow_backend.load_database_models  # noqa: F401,E402


class MockTemplateStorageService:
    """Mock storage service for testing without file system dependencies."""

    def __init__(self):
        self._files = {}

    def store_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> None:
        key = (tenant_id, template_key, version, file_name)
        self._files[key] = content

    def get_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> bytes:
        key = (tenant_id, template_key, version, file_name)
        if key in self._files:
            return self._files[key]
        # Return a valid BPMN content for testing
        return b'''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_test" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"/>
  </bpmn:process>
</bpmn:definitions>'''

    def list_files(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
    ) -> list:
        return [{"file_name": "test.bpmn", "file_type": "bpmn"}]

    def delete_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> None:
        key = (tenant_id, template_key, version, file_name)
        self._files.pop(key, None)

    def stream_zip(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_entries: list,
    ) -> bytes:
        return b"PK\x03\x04"


# ============================================================================
# ProcessModelTemplateModel Tests
# ============================================================================


def test_process_model_template_model_serialized() -> None:
    """Test ProcessModelTemplateModel.serialized() returns correct dict."""
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
        provenance.updated_at_in_seconds = 1234567890

        serialized = provenance.serialized()
        
        assert serialized["process_model_identifier"] == "test-group/test-model"
        assert serialized["source_template_id"] == 1
        assert serialized["source_template_key"] == "test-template"
        assert serialized["source_template_version"] == "V1"
        assert serialized["source_template_name"] == "Test Template"
        assert serialized["m8f_tenant_id"] == "tenant-1"
        assert serialized["created_by"] == "testuser"


# ============================================================================
# BPMN Transformation Tests
# ============================================================================


def test_transform_bpmn_content_replaces_process_id() -> None:
    """Test _transform_bpmn_content replaces process IDs with unique ones."""
    bpmn_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_original" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"/>
  </bpmn:process>
</bpmn:definitions>'''

    transformed, new_process_id = TemplateService._transform_bpmn_content(
        bpmn_content, "my-new-model"
    )

    # Check that the original process ID is replaced
    assert b"Process_original" not in transformed
    # Check that the new process ID contains the model name
    assert b"Process_my_new_model_" in transformed
    # Check that a new process ID was returned
    assert new_process_id is not None
    assert new_process_id.startswith("Process_my_new_model_")


def test_transform_bpmn_content_handles_invalid_encoding() -> None:
    """Test _transform_bpmn_content handles non-UTF8 content gracefully."""
    # Invalid UTF-8 bytes
    invalid_content = b"\xff\xfe"

    transformed, new_process_id = TemplateService._transform_bpmn_content(
        invalid_content, "test-model"
    )

    # Should return original content unchanged
    assert transformed == invalid_content
    assert new_process_id is None


# ============================================================================
# Get Process Model Template Info Tests
# ============================================================================


def test_get_process_model_template_info_returns_none_when_not_found() -> None:
    """Test get_process_model_template_info returns None for non-template process models."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        g.m8flow_tenant_id = "tenant-1"

        result = TemplateService.get_process_model_template_info(
            "non-existent/process-model"
        )

        assert result is None


def test_get_process_model_template_info_returns_provenance() -> None:
    """Test get_process_model_template_info returns provenance when exists."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        g.m8flow_tenant_id = "tenant-1"

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

        result = TemplateService.get_process_model_template_info(
            "test-group/test-model"
        )

        assert result is not None
        assert result.process_model_identifier == "test-group/test-model"
        assert result.source_template_key == "test-template"
        assert result.source_template_version == "V1"


def test_get_process_model_template_info_respects_tenant_isolation() -> None:
    """Test get_process_model_template_info only returns provenance for current tenant."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Create two tenants
        tenant1 = M8flowTenantModel(id="tenant-1", name="Tenant 1", slug="tenant-1", created_by="test", modified_by="test")
        tenant2 = M8flowTenantModel(id="tenant-2", name="Tenant 2", slug="tenant-2", created_by="test", modified_by="test")
        db.session.add_all([tenant1, tenant2])
        db.session.commit()

        # Create a template in tenant-1
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

        # Create provenance in tenant-1
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

        # Query from tenant-2 should not find the provenance
        g.m8flow_tenant_id = "tenant-2"
        result = TemplateService.get_process_model_template_info(
            "test-group/test-model"
        )

        assert result is None

        # Query from tenant-1 should find the provenance
        g.m8flow_tenant_id = "tenant-1"
        result = TemplateService.get_process_model_template_info(
            "test-group/test-model"
        )

        assert result is not None
        assert result.m8f_tenant_id == "tenant-1"


# ============================================================================
# Create Process Model From Template Tests (Mocked)
# ============================================================================


def test_create_process_model_from_template_requires_authentication() -> None:
    """Test create_process_model_from_template raises error when user is None."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        g.m8flow_tenant_id = "tenant-1"

        with pytest.raises(ApiError) as exc_info:
            TemplateService.create_process_model_from_template(
                template_id=1,
                process_group_id="test-group",
                process_model_id="test-model",
                display_name="Test Model",
                description=None,
                user=None,
            )

        assert exc_info.value.error_code == "unauthorized"


def test_create_process_model_from_template_requires_tenant() -> None:
    """Test create_process_model_from_template raises error when tenant is missing."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        # Don't set g.m8flow_tenant_id

        user = MagicMock()
        user.username = "testuser"

        with pytest.raises(ApiError) as exc_info:
            TemplateService.create_process_model_from_template(
                template_id=1,
                process_group_id="test-group",
                process_model_id="test-model",
                display_name="Test Model",
                description=None,
                user=user,
            )

        assert exc_info.value.error_code == "tenant_required"


def test_create_process_model_from_template_raises_not_found_for_missing_template() -> None:
    """Test create_process_model_from_template raises error when template doesn't exist."""
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        g.m8flow_tenant_id = "tenant-1"

        # Create tenant
        tenant = M8flowTenantModel(id="tenant-1", name="Test Tenant", slug="test-tenant", created_by="test", modified_by="test")
        db.session.add(tenant)
        db.session.commit()

        user = MagicMock()
        user.username = "testuser"

        with pytest.raises(ApiError) as exc_info:
            TemplateService.create_process_model_from_template(
                template_id=999,  # Non-existent
                process_group_id="test-group",
                process_model_id="test-model",
                display_name="Test Model",
                description=None,
                user=user,
            )

        assert exc_info.value.error_code == "not_found"
