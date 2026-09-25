"""The NATS trigger consumer starts instances through m8flow_backend.workflow.

Regression: instantiate_process imported spiffworkflow_backend (not installed on this
branch), so every triggered event failed after authentication.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from m8flow_backend import catalog, identity

_CONSUMER_DIR = Path(__file__).resolve().parents[4] / "m8flow-nats-consumer"
_BPMN = Path(__file__).resolve().parents[2] / "fixtures" / "invoice_approval_poc.bpmn"
_SERVICE = "https://example.test/realms/m8flow"


@pytest.fixture
def consumer(app, monkeypatch, tmp_path):
    # Never read the developer's real .env into the test session.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_k: None)
    for key, value in {
        "M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR": str(tmp_path),
        "M8FLOW_NATS_URL": "nats://unused:4222",
        "M8FLOW_NATS_STREAM_NAME": "M8FLOW_EVENTS",
        "M8FLOW_NATS_SUBJECT": "m8flow.events.>",
        "M8FLOW_NATS_DURABLE_NAME": "test",
        "M8FLOW_NATS_FETCH_BATCH": "1",
        "M8FLOW_NATS_FETCH_TIMEOUT": "1",
        "M8FLOW_NATS_DEDUP_BUCKET": "test",
        "M8FLOW_NATS_DEDUP_TTL": "60",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(str(_CONSUMER_DIR))
    sys.modules.pop("trigger_event_consumer", None)
    module = importlib.import_module("trigger_event_consumer")
    monkeypatch.setattr(module, "flask_app", app)
    yield module
    sys.modules.pop("trigger_event_consumer", None)


def _seed(db_session, tmp_path):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = identity.ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    user = identity.ensure_user(db_session, username="admin", service=_SERVICE, service_id="admin-1")
    identity.ensure_membership(db_session, user, tenant)
    identity.sync_groups(db_session, user=user, group_identifiers=["t-acme:editor"], tenant_id="t-acme")
    ensure_v1_role(db_session, tenant_id="t-acme", role_name="admin", user_ids=(user.id,))
    catalog.save(
        db_session,
        path="group-a/flow-a",
        xml=_BPMN.read_text(encoding="utf-8"),
        tenant_id="t-acme",
        user_id=user.id,
    )
    db_session.commit()


def test_instantiates_and_records_the_audit_row_in_one_transaction(consumer, db_session, tmp_path):
    from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel
    from m8flow_backend.models.nats_event_audit import NatsEventAuditModel

    _seed(db_session, tmp_path)

    result = consumer.instantiate_process(
        "t-acme", "group-a/flow-a", "admin", {"invoice_id": "INV-1"}, {"event_id": "evt-1", "stream_seq": 9}
    )

    assert result["id"] and result["process_model_identifier"] == "group-a/flow-a"
    db_session.expire_all()
    audit = db_session.scalars(select(NatsEventAuditModel)).one()
    assert (audit.event_id, audit.outcome, audit.process_instance_id) == ("evt-1", "instantiated", result["id"])
    metadata = {
        row.key: row.value
        for row in db_session.scalars(
            select(ProcessInstanceMetadataModel).where(ProcessInstanceMetadataModel.process_instance_id == result["id"])
        )
    }
    assert metadata["invoice_id"] == "INV-1"
    assert metadata["_nats_initiator_username"] == "admin"


def test_unknown_initiator_and_model_raise_the_classified_errors(consumer, db_session, tmp_path):
    _seed(db_session, tmp_path)

    with pytest.raises(consumer.ProcessModelNotFoundError):
        consumer.instantiate_process("t-acme", "group-a/missing", "admin", {}, None)
    with pytest.raises(consumer.InitiatorNotFoundError):
        consumer.instantiate_process("t-acme", "group-a/flow-a", "nobody-xyz", {}, None)
