"""The NATS trigger consumer starts instances through m8flow_backend.workflow.

Regression: instantiate_process imported spiffworkflow_backend (not installed on this
branch), so every triggered event failed after authentication.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

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


def test_nats_workers_do_not_import_spiffworkflow():
    import re

    for name in ("trigger_event_consumer.py", "notification_worker.py"):
        source = (_CONSUMER_DIR / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+spiffworkflow", source, re.MULTILINE), name


def test_starts_for_a_user_active_in_another_tenant_without_switching_them(consumer, db_session, tmp_path):
    from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel
    from m8flow_bpmn_core.models.user import UserModel
    from m8flow_backend.models.nats_event_audit import NatsEventAuditModel

    _seed(db_session, tmp_path)
    user = db_session.scalars(select(UserModel).where(UserModel.username == "admin")).one()
    # Multi-org user whose last login was into another organization.
    identity.ensure_membership(db_session, user, identity.ensure_tenant(db_session, tenant_id="t-other", slug="other"))
    db_session.commit()

    result = consumer.instantiate_process(
        "t-acme", "group-a/flow-a", "admin", {"note": "x" * 5000}, {"event_id": "evt-2", "stream_seq": 3}
    )

    db_session.expire_all()
    assert db_session.scalars(select(NatsEventAuditModel)).one().process_instance_id == result["id"]
    note = db_session.scalars(
        select(ProcessInstanceMetadataModel.value).where(
            ProcessInstanceMetadataModel.process_instance_id == result["id"],
            ProcessInstanceMetadataModel.key == "note",
        )
    ).one()
    assert 0 < len(note) < 5000
    # The grant is temporary: the user stays active in, and only a member of, their own tenant.
    refreshed = db_session.get(UserModel, user.id)
    assert (refreshed.tenant_specific_field_1, refreshed.tenant_specific_field_3) == ("t-other", None)


def test_a_failed_start_under_the_grant_is_rolled_back_not_committed(consumer, db_session, tmp_path, monkeypatch):
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel
    from m8flow_bpmn_core.models.user import UserModel

    _seed(db_session, tmp_path)
    user = db_session.scalars(select(UserModel).where(UserModel.username == "admin")).one()
    identity.ensure_membership(db_session, user, identity.ensure_tenant(db_session, tenant_id="t-other", slug="other"))
    db_session.commit()

    def failing_start(session, **_kwargs):
        identity.ensure_tenant(session, tenant_id="t-half-written")
        session.flush()
        raise RuntimeError("start failed midway")

    monkeypatch.setattr("m8flow_backend.workflow.start", failing_start)
    with pytest.raises(RuntimeError, match="midway"):
        consumer.instantiate_process("t-acme", "group-a/flow-a", "admin", {}, None)

    db_session.expire_all()
    assert db_session.get(M8flowTenantModel, "t-half-written") is None
    assert db_session.get(UserModel, user.id).tenant_specific_field_3 is None


def test_unknown_initiator_and_model_raise_the_classified_errors(consumer, db_session, tmp_path):
    _seed(db_session, tmp_path)

    with pytest.raises(consumer.ProcessModelNotFoundError):
        consumer.instantiate_process("t-acme", "group-a/missing", "admin", {}, None)
    with pytest.raises(consumer.InitiatorNotFoundError):
        consumer.instantiate_process("t-acme", "group-a/flow-a", "nobody-xyz", {}, None)


class _Message:
    def __init__(self, subject: str, body: dict, seq: int):
        self.subject = subject
        self.data = json.dumps(body).encode()
        self.headers = {}
        self.metadata = SimpleNamespace(sequence=SimpleNamespace(stream=seq))
        self.acked = False

    async def ack(self):
        self.acked = True


class _Nats:
    async def publish(self, *_args, **_kwargs):
        pass


def test_a_forged_message_cannot_rewrite_another_tenants_history(consumer, db_session):
    from m8flow_backend.models.nats_event_audit import NatsEventAuditModel
    from m8flow_backend.services.nats_event_audit_service import NatsEventAuditService

    identity.ensure_tenant(db_session, tenant_id="t-victim", slug="victim")
    identity.ensure_tenant(db_session, tenant_id="t-evil", slug="evil")
    db_session.commit()
    NatsEventAuditService.record_queued(tenant_id="t-victim", event_id="victim-evt")
    # Published on the sender's own subject, claiming the victim's tenant and event id,
    # with a key that does not authenticate.
    forged = _Message(
        "m8flow.events.evil.trigger",
        {
            "id": "victim-evt",
            "tenant_id": "t-victim",
            "process_identifier": "group-a/flow-a",
            "username": "admin",
            "api_key": "m8f_bad.key",
        },
        seq=77,
    )

    asyncio.run(consumer.process_message(forged, None, _Nats()))

    db_session.expire_all()
    rows = {(r.m8f_tenant_id, r.event_id): r for r in db_session.scalars(select(NatsEventAuditModel))}
    assert (rows[("t-victim", "victim-evt")].outcome, rows[("t-victim", "victim-evt")].stream_seq) == ("queued", None)
    # The rejection is still recorded, under the tenant the subject names.
    assert rows[("t-evil", "victim-evt")].outcome == "rejected_auth"
    assert forged.acked


def _tenant_editor(db_session, *, username: str, service: str, service_id: str):
    """A t-acme member as older code could leave it, inserted directly: ensure_user no
    longer mints a second row for the same Keycloak user."""
    from m8flow_bpmn_core.models.user import UserModel
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    now = datetime.now(timezone.utc)
    user = UserModel(
        username=username,
        service=service,
        service_id=service_id,
        display_name=username,
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    db_session.flush()
    tenant = identity.ensure_tenant(db_session, tenant_id="t-acme", slug="acme")
    identity.ensure_membership(db_session, user, tenant)
    identity.sync_groups(db_session, user=user, group_identifiers=["t-acme:editor"], tenant_id="t-acme")
    ensure_v1_role(db_session, tenant_id="t-acme", role_name="admin", user_ids=(user.id,))
    db_session.commit()
    return user


def test_one_keycloak_user_under_two_hosts_starts_as_the_row_logins_use(consumer, db_session, tmp_path):
    from m8flow_backend.integrations.auth import get_auth_provider

    _seed(db_session, tmp_path)
    login_issuer = get_auth_provider().default_issuer_claim()
    other_host = "http://keycloak-internal:8080/realms/" + login_issuer.rsplit("/realms/", 1)[1]
    login_row = _tenant_editor(db_session, username="twin", service=login_issuer, service_id="kc-twin")
    _tenant_editor(db_session, username="twin", service=other_host, service_id="kc-twin")

    started = consumer.instantiate_process("t-acme", "group-a/flow-a", "twin", {}, None)

    initiator = db_session.execute(
        text("SELECT process_initiator_id FROM process_instance WHERE id = :id"), {"id": started["id"]}
    ).scalar_one()
    assert initiator == login_row.id


def test_two_different_people_sharing_a_username_are_refused_as_ambiguous(consumer, db_session, tmp_path):
    _seed(db_session, tmp_path)
    _tenant_editor(db_session, username="dup", service="https://example.test/realms/m8flow", service_id="kc-a")
    _tenant_editor(db_session, username="dup", service="https://example.test/realms/m8flow", service_id="kc-b")

    with pytest.raises(consumer.InitiatorNotFoundError, match="ambiguous"):
        consumer.instantiate_process("t-acme", "group-a/flow-a", "dup", {}, None)
