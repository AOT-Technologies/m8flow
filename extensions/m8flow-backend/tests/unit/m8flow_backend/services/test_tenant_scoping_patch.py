# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_scoping_patch.py
import sys
from pathlib import Path

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
from m8flow_backend.services import tenant_scoping_patch  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

import spiffworkflow_backend.load_database_models  # noqa: F401,E402
from m8flow_backend.models.message_model import MessageModel  # noqa: E402
from m8flow_backend.models.process_instance import ProcessInstanceModel  # noqa: E402
from m8flow_backend.models.process_instance import ProcessInstanceStatus  # noqa: E402


def test_tenant_scopes_process_instances() -> None:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    tenant_scoping_patch.apply()

    with app.app_context():
        db.create_all()
        db.session.add(M8flowTenantModel(id="tenant-a", name="Tenant A"))
        db.session.add(M8flowTenantModel(id="tenant-b", name="Tenant B"))
        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        db.session.add(user)
        db.session.commit()

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            process_a = ProcessInstanceModel(
                process_model_identifier="process-a",
                process_model_display_name="Process A",
                process_initiator_id=user.id,
                status=ProcessInstanceStatus.running.value,
            )
            message_a = MessageModel(
                identifier="message-a",
                location="group/a",
                schema={},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            db.session.add(process_a)
            db.session.add(message_a)
            db.session.commit()
            assert process_a.m8f_tenant_id == "tenant-a"
            assert message_a.m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            process_b = ProcessInstanceModel(
                process_model_identifier="process-b",
                process_model_display_name="Process B",
                process_initiator_id=user.id,
                status=ProcessInstanceStatus.running.value,
            )
            message_b = MessageModel(
                identifier="message-b",
                location="group/b",
                schema={},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            db.session.add(process_b)
            db.session.add(message_b)
            db.session.commit()
            assert process_b.m8f_tenant_id == "tenant-b"
            assert message_b.m8f_tenant_id == "tenant-b"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            rows = ProcessInstanceModel.query.all()
            assert len(rows) == 1
            assert rows[0].process_model_identifier == "process-a"
            messages = MessageModel.query.all()
            assert len(messages) == 1
            assert messages[0].identifier == "message-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            rows = ProcessInstanceModel.query.all()
            assert len(rows) == 1
            assert rows[0].process_model_identifier == "process-b"
            messages = MessageModel.query.all()
            assert len(messages) == 1
            assert messages[0].identifier == "message-b"
