# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_template_service.py
import sys
from pathlib import Path
from unittest.mock import patch

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
from m8flow_backend.services.template_service import TemplateService  # noqa: E402
from m8flow_backend.services.template_storage_service import TemplateStorageService  # noqa: E402
from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

import spiffworkflow_backend.load_database_models  # noqa: F401,E402


class MockTemplateStorageService:
    """Mock storage service for testing without file system dependencies."""

    def store_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> None:
        pass

    def get_file(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_name: str,
    ) -> bytes:
        return b"<bpmn>mock content</bpmn>"

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
        pass

    def stream_zip(
        self,
        tenant_id: str,
        template_key: str,
        version: str,
        file_entries: list,
    ) -> bytes:
        return b"PK\x03\x04"  # minimal zip bytes


# ============================================================================
# Version Management Tests
# ============================================================================


def test_version_key() -> None:
    """Test _version_key() static method for V-style versions (V1, V2, ...)."""
    assert TemplateService._version_key("V1") == (1, 1)
    assert TemplateService._version_key("V2") == (1, 2)
    assert TemplateService._version_key("v10") == (1, 10)


def test_next_version_first_template() -> None:
    """Test _next_version() returns 'V1' for first template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.commit()

        version = TemplateService._next_version("test-template", "tenant-a")
        assert version == "V1"


def test_next_version_increments_patch() -> None:
    """Test V-style version incrementing (V1 -> V2 -> V3)."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create first template (V1)
        template1 = TemplateModel(
            template_key="test-template",
            version="V1",
            name="Test Template",
            m8f_tenant_id="tenant-a",
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template1)
        db.session.commit()

        # Get next version
        next_version = TemplateService._next_version("test-template", "tenant-a")
        assert next_version == "V2"

        # Create another version
        template2 = TemplateModel(
            template_key="test-template",
            version=next_version,
            name="Test Template",
            m8f_tenant_id="tenant-a",
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template2)
        db.session.commit()

        # Get next version again
        next_version2 = TemplateService._next_version("test-template", "tenant-a")
        assert next_version2 == "V3"


def test_next_version_handles_non_numeric() -> None:
    """Non-numeric V suffix (e.g. V1-alpha) falls back to V1 for next version."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create template with non-numeric V suffix (V1-alpha -> fallback to V1)
        template = TemplateModel(
            template_key="test-template",
            version="V1-alpha",
            name="Test Template",
            m8f_tenant_id="tenant-a",
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template)
        db.session.commit()

        # Next version starts V-series at V1
        next_version = TemplateService._next_version("test-template", "tenant-a")
        assert next_version == "V1"


def test_next_version_tenant_scoped() -> None:
    """Verify versions are scoped per tenant."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create template for tenant-a (V1)
        template_a = TemplateModel(
            template_key="shared-template",
            version="V1",
            name="Shared Template",
            m8f_tenant_id="tenant-a",
            files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template_a)
        db.session.commit()

        # Tenant-b should get V1 as first version (independent versioning)
        version_b = TemplateService._next_version("shared-template", "tenant-b")
        assert version_b == "V1"

        # Tenant-a should get V2
        version_a = TemplateService._next_version("shared-template", "tenant-a")
        assert version_a == "V2"


# ============================================================================
# Create Template Tests
# ============================================================================


def test_create_template_with_bpmn_bytes() -> None:
    """Create template with BPMN bytes and metadata."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                metadata = {
                    "template_key": "test-template",
                    "name": "Test Template",
                    "description": "A test template",
                    "category": "test",
                    "tags": ["tag1", "tag2"],
                    "visibility": TemplateVisibility.private.value,
                }
                bpmn_bytes = b"<bpmn>test content</bpmn>"

                template = TemplateService.create_template(
                    bpmn_bytes=bpmn_bytes,
                    metadata=metadata,
                    user=user,
                    tenant_id="tenant-a",
                )

                assert template.template_key == "test-template"
                assert template.name == "Test Template"
                assert template.description == "A test template"
                assert template.category == "test"
                assert template.tags == ["tag1", "tag2"]
                assert template.visibility == TemplateVisibility.private.value
                assert template.m8f_tenant_id == "tenant-a"
                assert template.version == "V1"
                assert template.files and len(template.files) == 1
                assert template.files[0]["file_name"] == "diagram.bpmn"
                assert template.created_by == "tester"
                assert template.modified_by == "tester"


def test_create_template_with_legacy_data_format() -> None:
    """Legacy data dict format is no longer supported."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Legacy data dict should not be accepted; metadata + BPMN bytes are required.
            try:
                TemplateService.create_template(
                    metadata=None,
                    bpmn_bytes=None,
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError for missing metadata/BPMN"
            except ApiError as e:
                assert e.error_code == "missing_fields"


def test_create_template_without_user() -> None:
    """Should raise ApiError when user is None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            try:
                TemplateService.create_template(
                    metadata={"template_key": "test", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=None,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "unauthorized"
                assert e.status_code == 403


def test_create_template_without_tenant() -> None:
    """Should raise ApiError when tenant is missing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.user = user
            # No tenant set

            try:
                TemplateService.create_template(
                    metadata={"template_key": "test", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "tenant_required"
                assert e.status_code == 400


def test_create_template_without_required_fields() -> None:
    """Should raise ApiError for missing template_key/name."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Missing template_key
            try:
                TemplateService.create_template(
                    metadata={"name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"
                assert e.status_code == 400

            # Missing name
            try:
                TemplateService.create_template(
                    metadata={"template_key": "test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"
                assert e.status_code == 400


def test_create_template_without_bpmn_content() -> None:
    """Should raise ApiError when BPMN content is missing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            try:
                TemplateService.create_template(
                    metadata={"template_key": "test", "name": "Test"},
                    bpmn_bytes=None,
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"
                assert e.status_code == 400


def test_create_template_auto_versioning() -> None:
    """Verify automatic version assignment."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # First template should get V1
                template1 = TemplateService.create_template(
                    metadata={"template_key": "auto-version", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template1.version == "V1"

                # Second template with same key should get V2
                template2 = TemplateService.create_template(
                    metadata={"template_key": "auto-version", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template2.version == "V2"


def test_create_template_with_provided_version() -> None:
    """Test explicit version assignment."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                metadata = {
                    "template_key": "explicit-version",
                    "name": "Test",
                    "version": "V5",
                }
                template = TemplateService.create_template(
                    metadata=metadata,
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template.version == "V5"


def test_create_template_tenant_isolation() -> None:
    """Verify templates are scoped to correct tenant."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template_a = TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template_a.m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template_b = TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-b",
                )
                assert template_b.m8f_tenant_id == "tenant-b"
                assert template_b.template_key == "shared"
                # Should be independent versioning (V1 for first in tenant-b)
                assert template_b.version == "V1"


# ============================================================================
# List Templates Tests
# ============================================================================


def test_list_templates_latest_only() -> None:
    """Test listing only latest versions."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create multiple versions (V-style)
            template1 = TemplateModel(
                template_key="multi-version",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="multi-version",
                version="V2",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template3 = TemplateModel(
                template_key="multi-version",
                version="V3",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2, template3])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=True)
            assert len(results) == 1
            assert results[0].version == "V3"


def test_list_templates_all_versions() -> None:
    """Test listing all versions when latest_only=False."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create multiple versions (V-style)
            template1 = TemplateModel(
                template_key="all-versions",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="all-versions",
                version="V2",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
            assert len(results) == 2


def test_list_templates_filter_by_category() -> None:
    """Test category filtering."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="cat1-template",
                version="V1",
                name="Category 1",
                category="category1",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="cat2-template",
                version="V1",
                name="Category 2",
                category="category2",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", category="category1")
            assert len(results) == 1
            assert results[0].category == "category1"


def test_list_templates_filter_by_tag() -> None:
    """Test tag filtering (JSON array)."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="tag1-template",
                version="V1",
                name="Tag 1",
                tags=["tag1", "tag2"],
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="tag3-template",
                version="V1",
                name="Tag 3",
                tags=["tag3"],
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1")
            assert len(results) == 1
            assert "tag1" in results[0].tags


def test_list_templates_filter_by_owner() -> None:
    """Test owner filtering."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user1 = UserModel(username="owner1", email="owner1@example.com", service="local", service_id="owner1")
        user2 = UserModel(username="owner2", email="owner2@example.com", service="local", service_id="owner2")
        db.session.add_all([user1, user2])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="owner1-template",
                version="V1",
                name="Owner 1",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="owner1",
                modified_by="owner1",
            )
            template2 = TemplateModel(
                template_key="owner2-template",
                version="V1",
                name="Owner 2",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="owner2",
                modified_by="owner2",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user1, tenant_id="tenant-a", owner="owner1")
            assert len(results) == 1
            assert results[0].created_by == "owner1"


def test_list_templates_filter_by_visibility() -> None:
    """Test visibility filtering."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="public-template",
                version="V1",
                name="Public",
                visibility=TemplateVisibility.public.value,
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="private-template",
                version="V1",
                name="Private",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", visibility=TemplateVisibility.public.value
            )
            assert len(results) == 1
            assert results[0].visibility == TemplateVisibility.public.value


def test_list_templates_search() -> None:
    """Test text search in name/description."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="search-template",
                version="V1",
                name="Searchable Template",
                description="This is searchable",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="other-template",
                version="V1",
                name="Other Template",
                description="Unrelated content",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", search="searchable")
            assert len(results) == 1
            assert "searchable" in results[0].name.lower() or "searchable" in results[0].description.lower()


def test_list_templates_tenant_isolation() -> None:
    """Verify tenant scoping."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template_a = TemplateModel(
                template_key="shared",
                version="V1",
                name="Tenant A Template",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_a)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"

            template_b = TemplateModel(
                template_key="shared",
                version="V1",
                name="Tenant B Template",
                m8f_tenant_id="tenant-b",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_b)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a")
            assert len(results) == 1
            assert results[0].m8f_tenant_id == "tenant-a"


# ============================================================================
# Get Template Tests
# ============================================================================


def test_get_template_by_key_and_version() -> None:
    """Get specific version."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="specific-version",
                version="V2",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            result = TemplateService.get_template(
                template_key="specific-version", version="V2", user=user, tenant_id="tenant-a"
            )
            assert result is not None
            assert result.version == "V2"


def test_get_template_latest() -> None:
    """Get latest version when version=None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="latest-test",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="latest-test",
                version="V3",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            template3 = TemplateModel(
                template_key="latest-test",
                version="V2",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2, template3])
            db.session.commit()

            result = TemplateService.get_template(
                template_key="latest-test", latest=True, user=user, tenant_id="tenant-a"
            )
            assert result is not None
            assert result.version == "V3"


def test_get_template_not_found() -> None:
    """Return None for non-existent template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            result = TemplateService.get_template(
                template_key="nonexistent", user=user, tenant_id="tenant-a"
            )
            assert result is None


def test_get_template_tenant_isolation() -> None:
    """Verify tenant scoping."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template_a = TemplateModel(
                template_key="shared",
                version="V1",
                name="Tenant A",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_a)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"

            template_b = TemplateModel(
                template_key="shared",
                version="V1",
                name="Tenant B",
                m8f_tenant_id="tenant-b",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_b)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            result = TemplateService.get_template(template_key="shared", user=user, tenant_id="tenant-a")
            assert result is not None
            assert result.m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            result = TemplateService.get_template(template_key="shared", user=user, tenant_id="tenant-b")
            assert result is not None
            assert result.m8f_tenant_id == "tenant-b"


def test_get_template_by_id() -> None:
    """Get template by database ID."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="by-id",
                version="V1",
                name="Test",
                visibility=TemplateVisibility.public.value,
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            result = TemplateService.get_template_by_id(template_id, user=user)
            assert result is not None
            assert result.id == template_id


def test_get_template_by_id_visibility_check() -> None:
    """Verify visibility enforcement."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user1 = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        user2 = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([user1, user2])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="private",
                version="V1",
                name="Private Template",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="owner",
                modified_by="owner",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            # Owner can view
            result1 = TemplateService.get_template_by_id(template_id, user=user1)
            assert result1 is not None

            # Other user cannot view private template
            result2 = TemplateService.get_template_by_id(template_id, user=user2)
            assert result2 is None


def test_get_template_suppress_visibility() -> None:
    """Test suppress_visibility flag."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="suppress-test",
                version="V1",
                name="Test",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            # With suppress_visibility=True, should bypass visibility check
            result = TemplateService.get_template(
                template_key="suppress-test",
                user=user,
                tenant_id="tenant-a",
                suppress_visibility=True,
            )
            assert result is not None


# ============================================================================
# Update Template Tests
# ============================================================================


def test_update_template_by_key_version() -> None:
    """Update unpublished template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="update-test",
                version="V1",
                name="Original Name",
                description="Original Description",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            updates = {"name": "Updated Name", "description": "Updated Description"}
            updated = TemplateService.update_template("update-test", "V1", updates, user=user)

            assert updated.name == "Updated Name"
            assert updated.description == "Updated Description"


def test_update_template_published_immutable() -> None:
    """Should raise ApiError for published templates."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published",
                version="V1",
                name="Published Template",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.update_template("published", "V1", {"name": "Updated"}, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "immutable"
                assert e.status_code == 400


def test_update_template_unauthorized() -> None:
    """Should raise ApiError for unauthorized users."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        owner = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        other = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([owner, other])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = owner

            template = TemplateModel(
                template_key="unauthorized",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                visibility=TemplateVisibility.public.value,
                created_by="owner",
                modified_by="owner",
            )
            db.session.add(template)
            db.session.commit()

            # Other user can see (public) but cannot edit
            try:
                TemplateService.update_template("unauthorized", "V1", {"name": "Updated"}, user=other)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_update_template_not_found() -> None:
    """Should raise ApiError for non-existent template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            try:
                TemplateService.update_template("nonexistent", "V1", {"name": "Updated"}, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"
                assert e.status_code == 404


def test_update_template_by_id_unpublished() -> None:
    """Update unpublished template in place."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="update-by-id",
                version="V1",
                name="Original",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            updates = {"name": "Updated"}
            updated = TemplateService.update_template_by_id(template_id, updates, user=user)

            assert updated.id == template_id  # Same record
            assert updated.name == "Updated"
            assert updated.version == "V1"  # Same version


def test_update_template_by_id_publish_sets_status() -> None:
    """Publishing via is_published=True sets status to 'published'."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="publish-test",
                version="V1",
                name="Draft Template",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                status="draft",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            updates = {"is_published": True}
            updated = TemplateService.update_template_by_id(template_id, updates, user=user)

            assert updated.id == template_id
            assert updated.is_published is True
            assert updated.status == "published"


def test_update_template_by_id_published_creates_new_version() -> None:
    """Published templates create new version."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-update",
                version="V1",
                name="Published",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            updates = {"name": "New Version"}
            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                updated = TemplateService.update_template_by_id(template_id, updates, user=user)

            assert updated.id != template_id  # New record
            assert updated.name == "New Version"
            assert updated.version == "V2"  # New version (V1 -> next V2)
            assert updated.is_published is False  # New versions start unpublished


def test_update_template_with_bpmn_bytes() -> None:
    """Update BPMN content."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="bpmn-update",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "old.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                new_bpmn = b"<bpmn>new content</bpmn>"
                updated = TemplateService.update_template_by_id(template_id, {}, bpmn_bytes=new_bpmn, user=user)

                assert updated.files and len(updated.files) >= 1
                assert any(e.get("file_type") == "bpmn" for e in updated.files)


def test_update_template_allowed_fields() -> None:
    """Test updating various fields."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="fields-update",
                version="V1",
                name="Original",
                description="Original Desc",
                category="cat1",
                tags=["tag1"],
                visibility=TemplateVisibility.private.value,
                status="draft",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            updates = {
                "name": "Updated",
                "description": "Updated Desc",
                "category": "cat2",
                "tags": ["tag2"],
                "visibility": TemplateVisibility.public.value,
                "status": "active",
            }
            updated = TemplateService.update_template("fields-update", "V1", updates, user=user)

            assert updated.name == "Updated"
            assert updated.description == "Updated Desc"
            assert updated.category == "cat2"
            assert updated.tags == ["tag2"]
            assert updated.visibility == TemplateVisibility.public.value
            assert updated.status == "active"


# ============================================================================
# Delete Template Tests
# ============================================================================


def test_delete_template_by_id() -> None:
    """Soft delete unpublished template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="delete-by-id",
                version="V1",
                name="To Delete",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            TemplateService.delete_template_by_id(template_id, user=user)

            # Row should still exist but be marked as deleted
            deleted = TemplateModel.query.filter_by(id=template_id).first()
            assert deleted is not None
            assert deleted.is_deleted is True

            # Service-level accessors should no longer see the template
            assert TemplateService.get_template_by_id(template_id, user=user) is None
            assert (
                TemplateService.get_template(
                    template_key="delete-by-id",
                    version="V1",
                    user=user,
                    tenant_id="tenant-a",
                )
                is None
            )

            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
            assert all(t.id != template_id for t in results)


def test_soft_deleted_templates_are_excluded_from_queries() -> None:
    """Ensure soft-deleted templates are excluded from list/get queries."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Create active and soft-deleted templates
            active = TemplateModel(
                template_key="active-template",
                version="V1",
                name="Active",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            deleted = TemplateModel(
                template_key="deleted-template",
                version="V1",
                name="Deleted",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                is_deleted=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([active, deleted])
            db.session.commit()

            # list_templates should only return the active template
            results, pagination = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
            keys = {t.template_key for t in results}
            assert "active-template" in keys
            assert "deleted-template" not in keys

            # get_template should not return the deleted template
            assert (
                TemplateService.get_template(
                    template_key="deleted-template",
                    version="V1",
                    user=user,
                    tenant_id="tenant-a",
                )
                is None
            )

            # get_template_by_id should also exclude the deleted template
            assert TemplateService.get_template_by_id(deleted.id, user=user) is None


def test_delete_template_published_immutable() -> None:
    """Should raise ApiError for published templates."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-delete",
                version="V1",
                name="Published",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            try:
                TemplateService.delete_template_by_id(template_id, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "immutable"
                assert e.status_code == 400


def test_delete_template_unauthorized() -> None:
    """Should raise ApiError for unauthorized users."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        owner = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        other = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([owner, other])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = owner

            template = TemplateModel(
                template_key="unauthorized-delete",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                is_published=False,
                visibility=TemplateVisibility.public.value,
                created_by="owner",
                modified_by="owner",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            # Other user can see (public) but cannot delete
            try:
                TemplateService.delete_template_by_id(template_id, user=other)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_delete_template_not_found() -> None:
    """Should raise ApiError for non-existent template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template_id = 9999  # Non-existent ID

            try:
                TemplateService.delete_template_by_id(template_id, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"
                assert e.status_code == 404


# ============================================================================
# Integration/Edge Cases
# ============================================================================


def test_template_tenant_isolation_across_tenants() -> None:
    """Verify complete tenant isolation."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template_a = TemplateService.create_template(
                    metadata={"template_key": "isolated", "name": "Tenant A"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template_b = TemplateService.create_template(
                    metadata={"template_key": "isolated", "name": "Tenant B"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-b",
                )

        # Verify isolation
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            results_a, _ = TemplateService.list_templates(user=user, tenant_id="tenant-a")
            assert len(results_a) == 1
            assert results_a[0].m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            results_b, _ = TemplateService.list_templates(user=user, tenant_id="tenant-b")
            assert len(results_b) == 1
            assert results_b[0].m8f_tenant_id == "tenant-b"


def test_template_versioning_multiple_tenants() -> None:
    """Same template_key can have different versions per tenant."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B", slug="tenant-b", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # Create multiple versions for tenant-a
                TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # Create version for tenant-b (should be V1, independent)
                template_b = TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-b",
                )
                assert template_b.version == "V1"  # Independent versioning


def test_template_visibility_public_tenant_private() -> None:
    """Test all visibility levels."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # Create templates with different visibility
                public_template = TemplateService.create_template(
                    metadata={
                        "template_key": "public",
                        "name": "Public",
                        "visibility": TemplateVisibility.public.value,
                    },
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                tenant_template = TemplateService.create_template(
                    metadata={
                        "template_key": "tenant",
                        "name": "Tenant",
                        "visibility": TemplateVisibility.tenant.value,
                    },
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                private_template = TemplateService.create_template(
                    metadata={
                        "template_key": "private",
                        "name": "Private",
                        "visibility": TemplateVisibility.private.value,
                    },
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )

                assert public_template.visibility == TemplateVisibility.public.value
                assert tenant_template.visibility == TemplateVisibility.tenant.value
                assert private_template.visibility == TemplateVisibility.private.value


def test_template_tags_json_handling() -> None:
    """Test JSON tag storage and filtering."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template = TemplateService.create_template(
                    metadata={
                        "template_key": "tags-test",
                        "name": "Tags Test",
                        "tags": ["tag1", "tag2", "tag3"],
                    },
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )

                assert template.tags == ["tag1", "tag2", "tag3"]
                assert isinstance(template.tags, list)

                # Test filtering by tag
                results, _ = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1")
                assert len(results) == 1
                assert "tag1" in results[0].tags

                # Test filtering by multiple tags
                results, _ = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1,tag2")
                assert len(results) == 1


# ============================================================================
# Create Template with Multiple Files Tests
# ============================================================================


def test_create_template_with_multiple_files() -> None:
    """Create template with BPMN + JSON files."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                files = [
                    ("diagram.bpmn", b"<bpmn>content</bpmn>"),
                    ("form.json", b'{"field": "value"}'),
                ]
                metadata = {
                    "template_key": "multi-file",
                    "name": "Multi-File Template",
                }
                template = TemplateService.create_template_with_files(
                    metadata=metadata,
                    files=files,
                    user=user,
                    tenant_id="tenant-a",
                )

                assert template.template_key == "multi-file"
                assert len(template.files) == 2
                file_names = [f["file_name"] for f in template.files]
                assert "diagram.bpmn" in file_names
                assert "form.json" in file_names
                file_types = {f["file_name"]: f["file_type"] for f in template.files}
                assert file_types["diagram.bpmn"] == "bpmn"
                assert file_types["form.json"] == "json"


def test_create_template_with_files_requires_bpmn() -> None:
    """Should raise ApiError when no BPMN file is included."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                files = [
                    ("form.json", b'{"field": "value"}'),
                    ("readme.md", b"# Readme"),
                ]
                metadata = {
                    "template_key": "no-bpmn",
                    "name": "No BPMN Template",
                }
                try:
                    TemplateService.create_template_with_files(
                        metadata=metadata,
                        files=files,
                        user=user,
                        tenant_id="tenant-a",
                    )
                    assert False, "Should have raised ApiError"
                except ApiError as e:
                    assert e.error_code == "missing_fields"
                    assert e.status_code == 400


def test_create_template_with_files_requires_user() -> None:
    """Should raise ApiError when user is None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            try:
                TemplateService.create_template_with_files(
                    metadata={"template_key": "test", "name": "Test"},
                    files=[("diagram.bpmn", b"<bpmn/>")],
                    user=None,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "unauthorized"


def test_create_template_with_files_requires_metadata() -> None:
    """Should raise ApiError when metadata is missing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            try:
                TemplateService.create_template_with_files(
                    metadata=None,
                    files=[("diagram.bpmn", b"<bpmn/>")],
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"


# ============================================================================
# Update File Content Tests
# ============================================================================


def test_update_file_content_unpublished() -> None:
    """Update file content for an unpublished template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="file-update",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # Should not raise - updates file content
                TemplateService.update_file_content(
                    template, "form.json", b'{"updated": true}', user=user
                )


def test_update_file_content_published_rejected() -> None:
    """Should raise ApiError for published template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-file",
                version="V1",
                name="Published",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.update_file_content(
                    template, "diagram.bpmn", b"<bpmn>new</bpmn>", user=user
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_update_file_content_file_not_found() -> None:
    """Should raise ApiError when file is not in template files list."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="missing-file",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.update_file_content(
                    template, "nonexistent.json", b"content", user=user
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"
                assert e.status_code == 404


# ============================================================================
# Delete File from Template Tests
# ============================================================================


def test_delete_file_from_template_removes_entry() -> None:
    """Delete a file from template removes it from files list."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="delete-file",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                TemplateService.delete_file_from_template(template, "form.json", user=user)

            assert len(template.files) == 1
            assert template.files[0]["file_name"] == "diagram.bpmn"


def test_delete_file_rejects_last_file() -> None:
    """Cannot delete the last file from a template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="last-file",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.delete_file_from_template(template, "diagram.bpmn", user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_delete_file_rejects_only_bpmn() -> None:
    """Cannot delete the only BPMN file (even if other file types remain)."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="only-bpmn",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.delete_file_from_template(template, "diagram.bpmn", user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_delete_file_rejects_published() -> None:
    """Cannot delete files from a published template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-del-file",
                version="V1",
                name="Published",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.delete_file_from_template(template, "form.json", user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "forbidden"
                assert e.status_code == 403


def test_delete_file_not_found() -> None:
    """Should raise ApiError when file is not in template files list."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="del-not-found",
                version="V1",
                name="Test",
                m8f_tenant_id="tenant-a",
                files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.delete_file_from_template(template, "nonexistent.json", user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"
                assert e.status_code == 404


# ============================================================================
# Export Template Zip Tests
# ============================================================================


def test_export_template_zip() -> None:
    """Export template as zip returns zip bytes and filename."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="export-test",
                version="V1",
                name="Export Test",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                zip_bytes, filename = TemplateService.export_template_zip(template_id, user=user)

            assert isinstance(zip_bytes, bytes)
            assert len(zip_bytes) > 0
            assert "export-test" in filename
            assert filename.endswith(".zip")


def test_export_template_zip_not_found() -> None:
    """Should raise ApiError for non-existent template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            try:
                TemplateService.export_template_zip(9999, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"
                assert e.status_code == 404


def test_export_template_zip_no_files() -> None:
    """Should raise ApiError when template has no files."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="no-files",
                version="V1",
                name="No Files",
                m8f_tenant_id="tenant-a",
                files=[],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            try:
                TemplateService.export_template_zip(template_id, user=user)
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "not_found"


# ============================================================================
# Import Template from Zip Tests
# ============================================================================


def _create_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Helper to create zip bytes from a dict of {filename: content}."""
    import io as _io
    import zipfile as _zipfile
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_import_template_from_zip_valid() -> None:
    """Import a valid zip with BPMN and JSON files."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            zip_bytes = _create_zip_bytes({
                "diagram.bpmn": b"<bpmn>content</bpmn>",
                "form.json": b'{"field": "value"}',
            })
            metadata = {
                "template_key": "imported",
                "name": "Imported Template",
            }

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                template = TemplateService.import_template_from_zip(
                    zip_bytes=zip_bytes,
                    metadata=metadata,
                    user=user,
                    tenant_id="tenant-a",
                )

            assert template.template_key == "imported"
            assert len(template.files) == 2
            file_names = sorted(f["file_name"] for f in template.files)
            assert file_names == ["diagram.bpmn", "form.json"]


def test_import_template_from_zip_no_bpmn() -> None:
    """Should raise ApiError when zip contains no BPMN file."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            zip_bytes = _create_zip_bytes({
                "form.json": b'{"field": "value"}',
                "readme.md": b"# Readme",
            })
            metadata = {
                "template_key": "no-bpmn-zip",
                "name": "No BPMN",
            }

            try:
                TemplateService.import_template_from_zip(
                    zip_bytes=zip_bytes,
                    metadata=metadata,
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"
                assert e.status_code == 400


def test_import_template_from_zip_requires_user() -> None:
    """Should raise ApiError when user is None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            zip_bytes = _create_zip_bytes({"diagram.bpmn": b"<bpmn/>"})
            try:
                TemplateService.import_template_from_zip(
                    zip_bytes=zip_bytes,
                    metadata={"template_key": "test", "name": "Test"},
                    user=None,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "unauthorized"


def test_import_template_from_zip_oversized_rejected() -> None:
    """Should raise ApiError when zip exceeds maximum size."""
    from m8flow_backend.services.template_service import MAX_ZIP_SIZE

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Create oversized zip bytes (bigger than MAX_ZIP_SIZE)
            oversized_bytes = b"x" * (MAX_ZIP_SIZE + 1)
            metadata = {
                "template_key": "oversized",
                "name": "Oversized",
            }

            try:
                TemplateService.import_template_from_zip(
                    zip_bytes=oversized_bytes,
                    metadata=metadata,
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "payload_too_large"
                assert e.status_code == 400


def test_import_template_from_zip_missing_fields() -> None:
    """Should raise ApiError when required metadata fields are missing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            zip_bytes = _create_zip_bytes({"diagram.bpmn": b"<bpmn/>"})

            # Missing template_key
            try:
                TemplateService.import_template_from_zip(
                    zip_bytes=zip_bytes,
                    metadata={"name": "Test"},
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"

            # Missing name
            try:
                TemplateService.import_template_from_zip(
                    zip_bytes=zip_bytes,
                    metadata={"template_key": "test"},
                    user=user,
                    tenant_id="tenant-a",
                )
                assert False, "Should have raised ApiError"
            except ApiError as e:
                assert e.error_code == "missing_fields"


# ============================================================================
# Pagination Tests
# ============================================================================


def test_list_templates_pagination_returns_correct_structure() -> None:
    """list_templates returns (items, pagination) tuple with correct metadata."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create 5 templates
            for i in range(5):
                db.session.add(TemplateModel(
                    template_key=f"page-test-{i}",
                    version="V1",
                    name=f"Template {i}",
                    m8f_tenant_id="tenant-a",
                    files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                    created_by="tester",
                    modified_by="tester",
                ))
            db.session.commit()

            # Page 1, 2 per page
            items, pagination = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=1, per_page=2
            )
            assert len(items) == 2
            assert pagination["total"] == 5
            assert pagination["count"] == 2
            assert pagination["pages"] == 3

            # Page 2
            items2, pagination2 = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=2, per_page=2
            )
            assert len(items2) == 2
            assert pagination2["total"] == 5
            assert pagination2["count"] == 2

            # Page 3 (last page, partial)
            items3, pagination3 = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=3, per_page=2
            )
            assert len(items3) == 1
            assert pagination3["total"] == 5
            assert pagination3["count"] == 1


def test_list_templates_pagination_clamps_page() -> None:
    """Page value is clamped to valid range."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create 3 templates
            for i in range(3):
                db.session.add(TemplateModel(
                    template_key=f"clamp-test-{i}",
                    version="V1",
                    name=f"Template {i}",
                    m8f_tenant_id="tenant-a",
                    files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                    created_by="tester",
                    modified_by="tester",
                ))
            db.session.commit()

            # Page beyond max should be clamped
            items, pagination = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=999, per_page=10
            )
            assert len(items) == 3  # All items on page 1 (clamped)
            assert pagination["pages"] == 1

            # Page 0 or negative should be clamped to 1
            items_neg, pagination_neg = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=0, per_page=2
            )
            assert len(items_neg) == 2
            assert pagination_neg["total"] == 3


def test_list_templates_pagination_per_page_clamped() -> None:
    """per_page is clamped to 1..100."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            for i in range(3):
                db.session.add(TemplateModel(
                    template_key=f"perpage-test-{i}",
                    version="V1",
                    name=f"Template {i}",
                    m8f_tenant_id="tenant-a",
                    files=[{"file_type": "bpmn", "file_name": "test.bpmn"}],
                    created_by="tester",
                    modified_by="tester",
                ))
            db.session.commit()

            # per_page=0 should be clamped to 1
            items, pagination = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=1, per_page=0
            )
            assert len(items) == 1
            assert pagination["pages"] == 3

            # per_page=200 should be clamped to 100
            items2, pagination2 = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=1, per_page=200
            )
            assert len(items2) == 3  # All 3 fit within 100
            assert pagination2["pages"] == 1


def test_list_templates_pagination_empty_results() -> None:
    """Pagination with no results."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            items, pagination = TemplateService.list_templates(
                user=user, tenant_id="tenant-a", latest_only=False, page=1, per_page=10
            )
            assert len(items) == 0
            assert pagination["total"] == 0
            assert pagination["count"] == 0
            assert pagination["pages"] == 1


# ============================================================================
# _safe_content_disposition Tests (Controller Helper)
# ============================================================================


def test_safe_content_disposition_simple_filename() -> None:
    """Simple filename is properly encoded."""
    from m8flow_backend.routes.templates_controller import _safe_content_disposition

    result = _safe_content_disposition("diagram.bpmn")
    assert "Content-Disposition" in result
    assert "diagram.bpmn" in result["Content-Disposition"]
    assert result["Content-Disposition"].startswith("attachment;")


def test_safe_content_disposition_special_chars() -> None:
    """Special characters are percent-encoded per RFC 5987."""
    from m8flow_backend.routes.templates_controller import _safe_content_disposition

    result = _safe_content_disposition("my template (1).bpmn")
    header = result["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    # Spaces and parens should be encoded
    assert " " not in header.split("UTF-8''")[1]
    assert "(" not in header.split("UTF-8''")[1]


def test_safe_content_disposition_unicode() -> None:
    """Unicode filename is properly percent-encoded."""
    from m8flow_backend.routes.templates_controller import _safe_content_disposition

    result = _safe_content_disposition("diagrama_\u00e9.bpmn")
    header = result["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    # The unicode char should be percent-encoded
    assert "\u00e9" not in header


# ============================================================================
# get_first_bpmn_content Tests
# ============================================================================


def test_get_first_bpmn_content_returns_first_bpmn() -> None:
    """get_first_bpmn_content returns the content of the first BPMN file in list order."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Files list has primary.bpmn FIRST, then secondary.bpmn
            template = TemplateModel(
                template_key="primary-first",
                version="V1",
                name="Primary First",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "bpmn", "file_name": "primary.bpmn"},
                    {"file_type": "json", "file_name": "form.json"},
                    {"file_type": "bpmn", "file_name": "secondary.bpmn"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            class OrderAwareMockStorage:
                """Returns different content for each BPMN file to verify ordering."""
                def store_file(self, *a, **kw): pass
                def get_file(self, tenant_id, template_key, version, file_name):
                    if file_name == "primary.bpmn":
                        return b"<bpmn>PRIMARY CONTENT</bpmn>"
                    if file_name == "secondary.bpmn":
                        return b"<bpmn>SECONDARY CONTENT</bpmn>"
                    return b""
                def list_files(self, *a, **kw): return []
                def delete_file(self, *a, **kw): pass
                def stream_zip(self, *a, **kw): return b""

            with patch.object(TemplateService, "storage", OrderAwareMockStorage()):
                content = TemplateService.get_first_bpmn_content(template)

            assert content is not None
            assert b"PRIMARY CONTENT" in content
            assert b"SECONDARY" not in content


def test_get_first_bpmn_content_skips_non_bpmn() -> None:
    """get_first_bpmn_content skips non-BPMN files and returns the first BPMN."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # JSON file first, then BPMN
            template = TemplateModel(
                template_key="json-first",
                version="V1",
                name="JSON First",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "json", "file_name": "form.json"},
                    {"file_type": "bpmn", "file_name": "diagram.bpmn"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                content = TemplateService.get_first_bpmn_content(template)

            assert content is not None


def test_get_first_bpmn_content_no_bpmn_returns_none() -> None:
    """get_first_bpmn_content returns None when no BPMN files exist."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="no-bpmn",
                version="V1",
                name="No BPMN",
                m8f_tenant_id="tenant-a",
                files=[
                    {"file_type": "json", "file_name": "form.json"},
                ],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                content = TemplateService.get_first_bpmn_content(template)

            assert content is None


def test_get_first_bpmn_content_empty_files() -> None:
    """get_first_bpmn_content returns None when files list is empty."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A", slug="tenant-a", created_by="test", modified_by="test"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="empty-files",
                version="V1",
                name="Empty Files",
                m8f_tenant_id="tenant-a",
                files=[],
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                content = TemplateService.get_first_bpmn_content(template)

            assert content is None
