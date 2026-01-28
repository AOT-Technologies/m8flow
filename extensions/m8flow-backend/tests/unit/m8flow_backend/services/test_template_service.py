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

    def store_bpmn(self, template_key: str, version: str, bpmn_bytes: bytes, tenant_id: str) -> str:
        """Return a mock filename."""
        return f"{template_key}.bpmn"

    def get_bpmn(self, filename: str, tenant_id: str) -> bytes:
        """Return mock BPMN content."""
        return b"<bpmn>mock content</bpmn>"


# ============================================================================
# Version Management Tests
# ============================================================================


def test_version_key() -> None:
    """Test _version_key() static method with various version formats."""
    assert TemplateService._version_key("1.0.0") == (1, 0, 0)
    assert TemplateService._version_key("2.5.10") == (2, 5, 10)
    assert TemplateService._version_key("1.0") == (1, 0)
    assert TemplateService._version_key("1") == (1,)
    assert TemplateService._version_key("1.0.0-alpha") == (1, 0, 0, "-alpha")
    assert TemplateService._version_key("1.0.0.beta") == (1, 0, 0, ".beta")
    assert TemplateService._version_key("v1.0.0") == ("v1", 0, 0)


def test_next_version_first_template() -> None:
    """Test _next_version() returns '1.0.0' for first template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.commit()

        version = TemplateService._next_version("test-template", "tenant-a")
        assert version == "1.0.0"


def test_next_version_increments_patch() -> None:
    """Test version incrementing logic."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create first template
        template1 = TemplateModel(
            template_key="test-template",
            version="1.0.0",
            name="Test Template",
            m8f_tenant_id="tenant-a",
            bpmn_object_key="test.bpmn",
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template1)
        db.session.commit()

        # Get next version
        next_version = TemplateService._next_version("test-template", "tenant-a")
        assert next_version == "1.0.1"

        # Create another version
        template2 = TemplateModel(
            template_key="test-template",
            version=next_version,
            name="Test Template",
            m8f_tenant_id="tenant-a",
            bpmn_object_key="test.bpmn",
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template2)
        db.session.commit()

        # Get next version again
        next_version2 = TemplateService._next_version("test-template", "tenant-a")
        assert next_version2 == "1.0.2"


def test_next_version_handles_non_numeric() -> None:
    """Test version handling with non-numeric parts."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create template with non-numeric version
        template = TemplateModel(
            template_key="test-template",
            version="1.0.0-alpha",
            name="Test Template",
            m8f_tenant_id="tenant-a",
            bpmn_object_key="test.bpmn",
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template)
        db.session.commit()

        # Should append .1 to non-numeric version
        next_version = TemplateService._next_version("test-template", "tenant-a")
        assert next_version == "1.0.0-alpha.1"


def test_next_version_tenant_scoped() -> None:
    """Verify versions are scoped per tenant."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        # Create template for tenant-a
        template_a = TemplateModel(
            template_key="shared-template",
            version="1.0.0",
            name="Shared Template",
            m8f_tenant_id="tenant-a",
            bpmn_object_key="test.bpmn",
            created_by="tester",
            modified_by="tester",
        )
        db.session.add(template_a)
        db.session.commit()

        # Tenant-b should get 1.0.0 as first version (independent versioning)
        version_b = TemplateService._next_version("shared-template", "tenant-b")
        assert version_b == "1.0.0"

        # Tenant-a should get 1.0.1
        version_a = TemplateService._next_version("shared-template", "tenant-a")
        assert version_a == "1.0.1"


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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
                assert template.version == "1.0.0"
                assert template.bpmn_object_key == "test-template.bpmn"
                assert template.created_by == "tester"
                assert template.modified_by == "tester"


def test_create_template_with_legacy_data_format() -> None:
    """Create template using legacy data dict format."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            data = {
                "template_key": "legacy-template",
                "name": "Legacy Template",
                "bpmn_object_key": "legacy.bpmn",
                "version": "2.0.0",
            }

            template = TemplateService.create_template(
                data=data,
                user=user,
                tenant_id="tenant-a",
            )

            assert template.template_key == "legacy-template"
            assert template.name == "Legacy Template"
            assert template.version == "2.0.0"
            assert template.bpmn_object_key == "legacy.bpmn"


def test_create_template_without_user() -> None:
    """Should raise ApiError when user is None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            try:
                TemplateService.create_template(
                    metadata={"template_key": "test", "name": "Test"},
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            try:
                TemplateService.create_template(
                    metadata={"template_key": "test", "name": "Test"},
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            with patch.object(TemplateService, "storage", MockTemplateStorageService()):
                # First template should get 1.0.0
                template1 = TemplateService.create_template(
                    metadata={"template_key": "auto-version", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template1.version == "1.0.0"

                # Second template with same key should get 1.0.1
                template2 = TemplateService.create_template(
                    metadata={"template_key": "auto-version", "name": "Test"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template2.version == "1.0.1"


def test_create_template_with_provided_version() -> None:
    """Test explicit version assignment."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
                    "version": "5.0.0",
                }
                template = TemplateService.create_template(
                    metadata=metadata,
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-a",
                )
                assert template.version == "5.0.0"


def test_create_template_tenant_isolation() -> None:
    """Verify templates are scoped to correct tenant."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
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
                # Should be independent versioning
                assert template_b.version == "1.0.0"


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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create multiple versions
            template1 = TemplateModel(
                template_key="multi-version",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="multi-version",
                version="1.0.1",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template3 = TemplateModel(
                template_key="multi-version",
                version="1.0.2",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2, template3])
            db.session.commit()

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=True)
            assert len(results) == 1
            assert results[0].version == "1.0.2"


def test_list_templates_all_versions() -> None:
    """Test listing all versions when latest_only=False."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            # Create multiple versions
            template1 = TemplateModel(
                template_key="all-versions",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="all-versions",
                version="1.0.1",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="cat1-template",
                version="1.0.0",
                name="Category 1",
                category="category1",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="cat2-template",
                version="1.0.0",
                name="Category 2",
                category="category2",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", category="category1")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="tag1-template",
                version="1.0.0",
                name="Tag 1",
                tags=["tag1", "tag2"],
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="tag3-template",
                version="1.0.0",
                name="Tag 3",
                tags=["tag3"],
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user1 = UserModel(username="owner1", email="owner1@example.com", service="local", service_id="owner1")
        user2 = UserModel(username="owner2", email="owner2@example.com", service="local", service_id="owner2")
        db.session.add_all([user1, user2])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="owner1-template",
                version="1.0.0",
                name="Owner 1",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="owner1",
                modified_by="owner1",
            )
            template2 = TemplateModel(
                template_key="owner2-template",
                version="1.0.0",
                name="Owner 2",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="owner2",
                modified_by="owner2",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(user=user1, tenant_id="tenant-a", owner="owner1")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="public-template",
                version="1.0.0",
                name="Public",
                visibility=TemplateVisibility.public.value,
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="private-template",
                version="1.0.0",
                name="Private",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="search-template",
                version="1.0.0",
                name="Searchable Template",
                description="This is searchable",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="other-template",
                version="1.0.0",
                name="Other Template",
                description="Not searchable",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2])
            db.session.commit()

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", search="searchable")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template_a = TemplateModel(
                template_key="shared",
                version="1.0.0",
                name="Tenant A Template",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_a)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"

            template_b = TemplateModel(
                template_key="shared",
                version="1.0.0",
                name="Tenant B Template",
                m8f_tenant_id="tenant-b",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_b)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            results = TemplateService.list_templates(user=user, tenant_id="tenant-a")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="specific-version",
                version="2.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            result = TemplateService.get_template(
                template_key="specific-version", version="2.0.0", user=user, tenant_id="tenant-a"
            )
            assert result is not None
            assert result.version == "2.0.0"


def test_get_template_latest() -> None:
    """Get latest version when version=None."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template1 = TemplateModel(
                template_key="latest-test",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template2 = TemplateModel(
                template_key="latest-test",
                version="1.0.2",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            template3 = TemplateModel(
                template_key="latest-test",
                version="1.0.1",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([template1, template2, template3])
            db.session.commit()

            result = TemplateService.get_template(
                template_key="latest-test", latest=True, user=user, tenant_id="tenant-a"
            )
            assert result is not None
            assert result.version == "1.0.2"


def test_get_template_not_found() -> None:
    """Return None for non-existent template."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template_a = TemplateModel(
                template_key="shared",
                version="1.0.0",
                name="Tenant A",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template_a)
            db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"

            template_b = TemplateModel(
                template_key="shared",
                version="1.0.0",
                name="Tenant B",
                m8f_tenant_id="tenant-b",
                bpmn_object_key="test.bpmn",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="by-id",
                version="1.0.0",
                name="Test",
                visibility=TemplateVisibility.public.value,
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user1 = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        user2 = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([user1, user2])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="private",
                version="1.0.0",
                name="Private Template",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"

            template = TemplateModel(
                template_key="suppress-test",
                version="1.0.0",
                name="Test",
                visibility=TemplateVisibility.private.value,
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="update-test",
                version="1.0.0",
                name="Original Name",
                description="Original Description",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            updates = {"name": "Updated Name", "description": "Updated Description"}
            updated = TemplateService.update_template("update-test", "1.0.0", updates, user=user)

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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published",
                version="1.0.0",
                name="Published Template",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()

            try:
                TemplateService.update_template("published", "1.0.0", {"name": "Updated"}, user=user)
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        owner = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        other = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([owner, other])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = owner

            template = TemplateModel(
                template_key="unauthorized",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=False,
                created_by="owner",
                modified_by="owner",
            )
            db.session.add(template)
            db.session.commit()

            # Other user cannot edit
            try:
                TemplateService.update_template("unauthorized", "1.0.0", {"name": "Updated"}, user=other)
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            try:
                TemplateService.update_template("nonexistent", "1.0.0", {"name": "Updated"}, user=user)
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="update-by-id",
                version="1.0.0",
                name="Original",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
            assert updated.version == "1.0.0"  # Same version


def test_update_template_by_id_published_creates_new_version() -> None:
    """Published templates create new version."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-update",
                version="1.0.0",
                name="Published",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            updates = {"name": "New Version"}
            updated = TemplateService.update_template_by_id(template_id, updates, user=user)

            assert updated.id != template_id  # New record
            assert updated.name == "New Version"
            assert updated.version == "1.0.1"  # New version
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="bpmn-update",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="old.bpmn",
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

                assert updated.bpmn_object_key == "bpmn-update.bpmn"


def test_update_template_allowed_fields() -> None:
    """Test updating various fields."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="fields-update",
                version="1.0.0",
                name="Original",
                description="Original Desc",
                category="cat1",
                tags=["tag1"],
                visibility=TemplateVisibility.private.value,
                status="draft",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
            updated = TemplateService.update_template("fields-update", "1.0.0", updates, user=user)

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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="delete-by-id",
                version="1.0.0",
                name="To Delete",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
                    version="1.0.0",
                    user=user,
                    tenant_id="tenant-a",
                )
                is None
            )

            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            # Create active and soft-deleted templates
            active = TemplateModel(
                template_key="active-template",
                version="1.0.0",
                name="Active",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=False,
                created_by="tester",
                modified_by="tester",
            )
            deleted = TemplateModel(
                template_key="deleted-template",
                version="1.0.0",
                name="Deleted",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=False,
                is_deleted=True,
                created_by="tester",
                modified_by="tester",
            )
            db.session.add_all([active, deleted])
            db.session.commit()

            # list_templates should only return the active template
            results = TemplateService.list_templates(user=user, tenant_id="tenant-a", latest_only=False)
            keys = {t.template_key for t in results}
            assert "active-template" in keys
            assert "deleted-template" not in keys

            # get_template should not return the deleted template
            assert (
                TemplateService.get_template(
                    template_key="deleted-template",
                    version="1.0.0",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = user

            template = TemplateModel(
                template_key="published-delete",
                version="1.0.0",
                name="Published",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        owner = UserModel(username="owner", email="owner@example.com", service="local", service_id="owner")
        other = UserModel(username="other", email="other@example.com", service="local", service_id="other")
        db.session.add_all([owner, other])
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g.user = owner

            template = TemplateModel(
                template_key="unauthorized-delete",
                version="1.0.0",
                name="Test",
                m8f_tenant_id="tenant-a",
                bpmn_object_key="test.bpmn",
                is_published=False,
                created_by="owner",
                modified_by="owner",
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
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
            results_a = TemplateService.list_templates(user=user, tenant_id="tenant-a")
            assert len(results_a) == 1
            assert results_a[0].m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            results_b = TemplateService.list_templates(user=user, tenant_id="tenant-b")
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
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
                # Create version for tenant-b (should be 1.0.0, independent)
                template_b = TemplateService.create_template(
                    metadata={"template_key": "shared", "name": "Shared"},
                    bpmn_bytes=b"<bpmn>test</bpmn>",
                    user=user,
                    tenant_id="tenant-b",
                )
                assert template_b.version == "1.0.0"  # Independent versioning


def test_template_visibility_public_tenant_private() -> None:
    """Test all visibility levels."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
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
                results = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1")
                assert len(results) == 1
                assert "tag1" in results[0].tags

                # Test filtering by multiple tags
                results = TemplateService.list_templates(user=user, tenant_id="tenant-a", tag="tag1,tag2")
                assert len(results) == 1
