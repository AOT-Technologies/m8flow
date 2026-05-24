import sys
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, g

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: E402
from m8flow_backend.models.template import TemplateModel, TemplateVisibility  # noqa: E402
from m8flow_backend.routes import templates_controller  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402


def test_template_list_includes_tenant_details_for_each_result() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(
            M8flowTenantModel(
                id="tenant-b",
                name="Tenant B",
                slug="tenant-b",
                created_by="test",
                modified_by="test",
                created_at_in_seconds=1,
                updated_at_in_seconds=1,
            )
        )
        db.session.commit()

        template = TemplateModel(
            id=99,
            template_key="cross-tenant-template",
            version="V1",
            name="Cross Tenant Template",
            description="test",
            tags=["ops"],
            category="ops",
            m8f_tenant_id="tenant-b",
            visibility=TemplateVisibility.private.value,
            files=[{"file_type": "bpmn", "file_name": "diagram.bpmn"}],
            is_published=False,
            status="draft",
            created_by="owner-b",
            modified_by="owner-b",
            created_at_in_seconds=1,
            updated_at_in_seconds=2,
        )

        with app.test_request_context("/templates"):
            user = Mock()
            user.username = "super-admin"
            g.user = user
            g._m8flow_super_admin_request = True

            with patch.object(templates_controller.TemplateService, "list_templates", return_value=([template], {"count": 1, "total": 1, "pages": 1})):
                response = templates_controller.template_list()

            payload = response.get_json()
            assert payload["results"][0]["tenantId"] == "tenant-b"
            assert payload["results"][0]["tenant"] == {
                "id": "tenant-b",
                "name": "Tenant B",
                "slug": "tenant-b",
            }
