# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_scoping_patch.py

from flask import Flask, g

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.message_model import MessageModel
from m8flow_backend.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
from m8flow_backend.services import tenant_scoping_patch
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db as spiff_db
from spiffworkflow_backend.models.user import UserModel


def test_tenant_scopes_process_instances() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"

    spiff_db.init_app(app)

    tenant_scoping_patch.apply()

    with app.app_context():
        # These must be the SAME metadata universe.
        assert SpiffworkflowBaseDBModel.metadata is spiff_db.metadata
        assert M8flowTenantModel.__table__.metadata is spiff_db.metadata
        assert ProcessInstanceModel.__table__.metadata is spiff_db.metadata
        assert MessageModel.__table__.metadata is spiff_db.metadata
        assert "m8flow_tenant" in spiff_db.metadata.tables

        spiff_db.create_all()

        spiff_db.session.add(
            M8flowTenantModel(
                id="tenant-a",
                name="Tenant A",
                slug="tenant-a",
                created_by="test",
                modified_by="test",
            )
        )
        spiff_db.session.add(
            M8flowTenantModel(
                id="tenant-b",
                name="Tenant B",
                slug="tenant-b",
                created_by="test",
                modified_by="test",
            )
        )


        user = UserModel(username="tester", email="tester@example.com", service="local", service_id="tester")
        spiff_db.session.add(user)
        spiff_db.session.commit()

        # tenant-a inserts
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
            spiff_db.session.add_all([process_a, message_a])
            spiff_db.session.commit()
            assert process_a.m8f_tenant_id == "tenant-a"
            assert message_a.m8f_tenant_id == "tenant-a"

        # tenant-b inserts
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
            spiff_db.session.add_all([process_b, message_b])
            spiff_db.session.commit()
            assert process_b.m8f_tenant_id == "tenant-b"
            assert message_b.m8f_tenant_id == "tenant-b"

        # tenant-a query
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            rows = ProcessInstanceModel.query.all()
            assert len(rows) == 1
            assert rows[0].process_model_identifier == "process-a"
            msgs = MessageModel.query.all()
            assert len(msgs) == 1
            assert msgs[0].identifier == "message-a"

        # tenant-b query
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            rows = ProcessInstanceModel.query.all()
            assert len(rows) == 1
            assert rows[0].process_model_identifier == "process-b"
            msgs = MessageModel.query.all()
            assert len(msgs) == 1
            assert msgs[0].identifier == "message-b"
