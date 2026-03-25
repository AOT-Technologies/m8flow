# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_tenant_scoping_patch.py

from flask import Flask, g

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.message_model import MessageModel
from m8flow_backend.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
from m8flow_backend.services import tenant_scoping_patch
from spiffworkflow_backend.models.configuration import ConfigurationModel
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel
from spiffworkflow_backend.models.db import db as spiff_db
from spiffworkflow_backend.models.pkce_code_verifier import PkceCodeVerifierModel
from spiffworkflow_backend.models.refresh_token import RefreshTokenModel
from spiffworkflow_backend.models.typeahead import TypeaheadModel
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


def test_tenant_scopes_configuration_pkce_refresh_token_and_typeahead() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"

    spiff_db.init_app(app)

    tenant_scoping_patch.apply()

    with app.app_context():
        # Verify these models are tenant scoped.
        assert "m8f_tenant_id" in ConfigurationModel.__table__.columns
        assert "m8f_tenant_id" in PkceCodeVerifierModel.__table__.columns
        assert "m8f_tenant_id" in RefreshTokenModel.__table__.columns
        assert "m8f_tenant_id" in TypeaheadModel.__table__.columns

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

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            config_a = ConfigurationModel(
                category="global_settings",
                value={"source": "tenant-a"},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            pkce_a = PkceCodeVerifierModel(
                pkce_id="shared-pkce-id",
                code_verifier="verifier-a",
                created_at_in_seconds=1,
            )
            refresh_a = RefreshTokenModel(
                user_id=user.id,
                token="token-a",
            )
            typeahead_a = TypeaheadModel(
                category="albums",
                search_term="shared-term",
                result={"source": "tenant-a"},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            spiff_db.session.add_all([config_a, pkce_a, refresh_a, typeahead_a])
            spiff_db.session.commit()
            assert config_a.m8f_tenant_id == "tenant-a"
            assert pkce_a.m8f_tenant_id == "tenant-a"
            assert refresh_a.m8f_tenant_id == "tenant-a"
            assert typeahead_a.m8f_tenant_id == "tenant-a"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            # These duplicate identifiers/user IDs across tenants should be allowed now.
            config_b = ConfigurationModel(
                category="global_settings",
                value={"source": "tenant-b"},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            pkce_b = PkceCodeVerifierModel(
                pkce_id="shared-pkce-id",
                code_verifier="verifier-b",
                created_at_in_seconds=1,
            )
            refresh_b = RefreshTokenModel(
                user_id=user.id,
                token="token-b",
            )
            typeahead_b = TypeaheadModel(
                category="albums",
                search_term="shared-term",
                result={"source": "tenant-b"},
                updated_at_in_seconds=1,
                created_at_in_seconds=1,
            )
            spiff_db.session.add_all([config_b, pkce_b, refresh_b, typeahead_b])
            spiff_db.session.commit()
            assert config_b.m8f_tenant_id == "tenant-b"
            assert pkce_b.m8f_tenant_id == "tenant-b"
            assert refresh_b.m8f_tenant_id == "tenant-b"
            assert typeahead_b.m8f_tenant_id == "tenant-b"

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            assert ConfigurationModel.query.count() == 1
            assert ConfigurationModel.query.first().value["source"] == "tenant-a"  # type: ignore[index]

            assert PkceCodeVerifierModel.query.count() == 1
            assert PkceCodeVerifierModel.query.first().code_verifier == "verifier-a"  # type: ignore[union-attr]

            assert RefreshTokenModel.query.count() == 1
            assert RefreshTokenModel.query.first().token == "token-a"  # type: ignore[union-attr]

            assert TypeaheadModel.query.count() == 1
            assert TypeaheadModel.query.first().result["source"] == "tenant-a"  # type: ignore[index]

        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-b"
            assert ConfigurationModel.query.count() == 1
            assert ConfigurationModel.query.first().value["source"] == "tenant-b"  # type: ignore[index]

            assert PkceCodeVerifierModel.query.count() == 1
            assert PkceCodeVerifierModel.query.first().code_verifier == "verifier-b"  # type: ignore[union-attr]

            assert RefreshTokenModel.query.count() == 1
            assert RefreshTokenModel.query.first().token == "token-b"  # type: ignore[union-attr]

            assert TypeaheadModel.query.count() == 1
            assert TypeaheadModel.query.first().result["source"] == "tenant-b"  # type: ignore[index]
