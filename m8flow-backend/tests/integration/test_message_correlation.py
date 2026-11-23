"""Run external message correlation over HTTP against the real Postgres runtime role."""

from __future__ import annotations

import pytest

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

ROUTE = "/v1.0/m8flow/messages/correlate"


@pytest.mark.parametrize(
    ("previous_revision", "preinstalled"),
    [("c81d2e3f4a56", False), ("m8f_694_core_message_schema", False), ("c81d2e3f4a56", True)],
)
def test_postgres_upgrade_from_both_previous_heads(admin_engine, monkeypatch, tmp_path, previous_revision, preinstalled):
    from datetime import UTC, datetime
    from pathlib import Path
    from uuid import uuid4

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from m8flow_core.models import Base

    schema = f"messages_upgrade_{uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    engine = sa.create_engine(admin_engine.url.update_query_dict({"options": f"-c search_path={schema}"}))
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    try:
        command.upgrade(cfg, previous_revision)
        if preinstalled:
            revision = ScriptDirectory.from_config(cfg).get_revision("m8f_694_core_message_schema").module
            with engine.begin() as connection:
                for table, name in revision.PARENT_INDEXES.items():
                    if name not in {index["name"] for index in sa.inspect(connection).get_indexes(table)}:
                        connection.execute(sa.text(f"CREATE UNIQUE INDEX {name} ON {table} (m8f_tenant_id, id)"))
                for name in revision.TABLES:
                    Base.metadata.tables[name].create(connection)
                connection.execute(revision.VERSION.update().values(version_num=revision.CORE_HEAD))
                connection.execute(Base.metadata.tables["message_delivery_receipt"].insert().values(
                    m8f_tenant_id="m8flow", delivery_id="core-owned-receipt", request_digest="a" * 64,
                    delivered_at=datetime.now(UTC),
                ))
        with engine.begin() as connection:
            connection.execute(sa.text("UPDATE m8flow_tenant SET slug = 'retained-tenant' WHERE id = 'm8flow'"))
        command.upgrade(cfg, "head")
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert connection.execute(sa.text(
                "SELECT version_num FROM m8flow_core_alembic_version"
            )).scalars().all() == ["m8f_694_message_correlation"]
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version_m8flow")) == (
                "m8f_694_merge_run_stats"
            )
            assert connection.scalar(sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")) == "retained-tenant"
            assert {"message_subscription", "message_delivery_receipt", "m8flow_process_model_release"} <= set(
                sa.inspect(connection).get_table_names()
            )
        command.downgrade(cfg, previous_revision)
        if preinstalled:
            with engine.connect() as connection:
                assert set(revision.TABLES) <= set(sa.inspect(connection).get_table_names())
                assert connection.scalar(sa.text("SELECT delivery_id FROM message_delivery_receipt")) == (
                    "core-owned-receipt"
                )
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT slug FROM m8flow_tenant WHERE id = 'm8flow'")) == "retained-tenant"
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))


def test_external_message_http_delivery_is_scoped_to_the_authorized_tenant():
    from m8flow_core.models import MessageDeliveryReceiptModel, ProcessInstanceModel

    from m8flow_backend import workflow
    from m8flow_backend.app import create_app
    from m8flow_backend.auth import encode_auth_token
    from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

    tenant = new_tenant_id("message")
    other_tenant = new_tenant_id("other")
    model = "payments/wait"

    def prepare(tenant_id):
        with tenant_session(tenant_id) as session:
            admin = provision_member(session, tenant_id=tenant_id, role="tenant-admin")
            ordinary = provision_member(session, tenant_id=tenant_id, role="submitter")
            save_model(session, tenant_id=tenant_id, user_id=admin.id, path=model, fixture="message_waiting.bpmn")
            return admin.id, encode_auth_token(user=admin), encode_auth_token(user=ordinary)

    def start(tenant_id, user_id, cases):
        with tenant_session(tenant_id) as session:
            return [
                workflow.start(
                    session, tenant_id=tenant_id, user_id=user_id, process_model_identifier=model,
                    submission_metadata={"case_number": number, "region": "west"},
                ).id
                for number in cases
            ]

    admin_id, admin_token, ordinary_token = prepare(tenant)
    other_admin_id, other_admin_token, _ = prepare(other_tenant)
    one, two, duplicate_one, duplicate_two = start(tenant, admin_id, [18, 19, 20, 20])
    [other] = start(other_tenant, other_admin_id, [18])

    body = {
        "messageName": "Payment received",
        "deliveryId": "payment-18",
        "payload": {"payment": {"caseNumber": 18, "region": "west"}},
    }

    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    with create_app().test_client() as client:
        client.cookies.set(SELECTED_TENANT_COOKIE_NAME, tenant)
        assert client.post(ROUTE, headers=bearer(ordinary_token), json=body).status_code == 403
        assert client.post(ROUTE, headers=bearer(admin_token), json={**body, "payload": []}).status_code == 400
        ambiguous = client.post(ROUTE, headers=bearer(admin_token), json={
            **body, "deliveryId": "ambiguous", "payload": {"payment": {"caseNumber": 20, "region": "west"}},
        })
        assert ambiguous.status_code == 409, ambiguous.text
        assert ambiguous.json()["error_code"] == "ambiguous_message_correlation"
        absent = client.post(ROUTE, headers=bearer(admin_token), json={
            **body, "deliveryId": "absent", "payload": {"payment": {"caseNumber": 999, "region": "west"}},
        })
        assert absent.status_code == 404, absent.text
        delivered = client.post(ROUTE, headers=bearer(admin_token), json=body)
        assert delivered.status_code == 200, delivered.text
        receipt = delivered.json()
        assert receipt["processInstanceId"] == one
        assert receipt["outcome"] == "delivered"
        assert client.post(ROUTE, headers=bearer(admin_token), json=body).json() == receipt
        conflict = client.post(ROUTE, headers=bearer(admin_token), json={**body, "processInstanceId": two})
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "message_delivery_conflict"
        missed = client.post(ROUTE, headers=bearer(admin_token), json={
            **body, "deliveryId": "wrong-tenant", "processInstanceId": other,
        })
        assert missed.status_code == 404
        second_delivery = client.post(ROUTE, headers=bearer(admin_token), json={
            **body, "deliveryId": "payment-19", "payload": {"payment": {"caseNumber": 19, "region": "west"}},
        })
        assert second_delivery.status_code == 200, second_delivery.text
        assert second_delivery.json()["processInstanceId"] == two
        client.cookies.set(SELECTED_TENANT_COOKIE_NAME, other_tenant)
        other_delivery = client.post(ROUTE, headers=bearer(other_admin_token), json=body)
        assert other_delivery.status_code == 200, other_delivery.text
        assert other_delivery.json()["processInstanceId"] == other

    with tenant_session(tenant) as session:
        assert session.get(ProcessInstanceModel, one).status == "complete"
        assert session.get(ProcessInstanceModel, two).status == "complete"
        assert session.get(ProcessInstanceModel, duplicate_one).status == "waiting"
        assert session.get(ProcessInstanceModel, duplicate_two).status == "waiting"
        assert session.get(ProcessInstanceModel, other) is None
        assert session.get(MessageDeliveryReceiptModel, (other_tenant, "payment-18")) is None


def test_external_message_requires_a_concrete_tenant_without_dispatch(monkeypatch):
    from m8flow_backend import workflow
    from m8flow_backend.app import create_app
    from m8flow_backend.auth import encode_auth_token
    from m8flow_backend.identity import ensure_user, sync_groups

    with tenant_session(None) as session:
        user = ensure_user(
            session, username=new_tenant_id("platform-admin"), service="local", service_id=new_tenant_id("admin"),
        )
        sync_groups(session, user=user, group_identifiers=["super-admin"], tenant_id="m8flow")
        token = encode_auth_token(user=user)

    def unexpected_dispatch(*args, **kwargs):
        pytest.fail("A message must never dispatch without a concrete active tenant")

    monkeypatch.setattr(workflow, "correlate_message", unexpected_dispatch)
    with create_app().test_client() as client:
        response = client.post(ROUTE, headers={"Authorization": f"Bearer {token}"}, json={
            "messageName": "Payment received", "deliveryId": "no-tenant", "payload": {},
        })
    assert response.status_code == 400, response.text
    assert response.json()["error_code"] == "tenant_required"
