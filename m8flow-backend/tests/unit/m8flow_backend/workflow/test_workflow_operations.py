from __future__ import annotations

import logging
from pathlib import Path

from m8flow_backend import catalog, identity, workflow

BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn"


def _seed_actor(session, tenant_id: str = "tenant-a"):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = identity.ensure_tenant(session, tenant_id=tenant_id, slug=tenant_id)
    user = identity.ensure_user(
        session,
        username="editor",
        service="https://example.test/realms/m8flow",
        service_id="editor-1",
        email="editor@example.test",
    )
    identity.ensure_membership(session, user, tenant)
    identity.sync_groups(
        session,
        user=user,
        group_identifiers=[f"{tenant_id}:editor"],
        tenant_id=tenant_id,
    )
    ensure_v1_role(session, tenant_id=tenant_id, role_name="admin", user_ids=(user.id,))
    session.flush()
    return tenant, user


def test_import_start_claim_complete_persists_status_tasks_and_metadata(db_session, tmp_path, monkeypatch, caplog):
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceStatus
    from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel

    created: list[str] = []
    completed_tasks: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "m8flow_backend.workflow.record_process_instance_created",
        lambda tenant_id, **_kwargs: created.append(tenant_id),
    )
    monkeypatch.setattr("m8flow_backend.workflow.record_process_instance_active_delta", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("m8flow_backend.workflow.record_process_instance_terminal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "m8flow_backend.workflow.record_task_completed",
        lambda tenant_id, *, task_type: completed_tasks.append((tenant_id, task_type)),
    )

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    caplog.set_level(logging.INFO, logger="m8flow_backend.workflow")
    tenant, user = _seed_actor(db_session)
    xml = BPMN.read_text(encoding="utf-8")
    catalog.save(
        db_session,
        path="invoices/approval",
        xml=xml,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    instance = workflow.start(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        process_model_identifier="invoices/approval",
    )
    assert instance.status in {
        ProcessInstanceStatus.user_input_required.value,
        ProcessInstanceStatus.running.value,
        "user_input_required",
        "running",
    }
    pending = workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id)
    assert pending
    task = pending[0]
    workflow.claim(db_session, tenant_id=tenant.id, human_task_id=task.id, user_id=user.id)
    completed = workflow.complete(
        db_session,
        tenant_id=tenant.id,
        human_task_id=task.id,
        user_id=user.id,
        task_payload={"approval_state": "approved", "amount": 42},
    )
    assert completed.id == instance.id
    rows = db_session.query(ProcessInstanceMetadataModel).filter_by(process_instance_id=instance.id).all()
    keys = {row.key for row in rows}
    assert "approval_state" in keys
    values = {row.key: row.value for row in rows}
    assert values["approval_state"] == "approved"
    assert isinstance(values["amount"], str)
    assert created == [tenant.id]
    assert completed_tasks == [(tenant.id, "UserTask")]
    db_session.refresh(instance)
    if instance.status in {
        ProcessInstanceStatus.complete.value,
        "complete",
    }:
        duration_logs = [
            record
            for record in caplog.records
            if record.getMessage() == "process instance completed"
        ]
        assert duration_logs
        assert duration_logs[-1].process_instance_status == "complete"
        assert duration_logs[-1].duration_seconds >= 0


def test_emit_process_instance_terminal_log_records_duration(db_session, caplog):
    import uuid

    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus

    tenant, user = _seed_actor(db_session, tenant_id="tenant-metrics")
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant.id,
        single_process_hash=uuid.uuid4().hex,
        bpmn_identifier="Process_metrics",
        properties_json={},
    )
    db_session.add(definition)
    db_session.flush()
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant.id,
        process_model_identifier="finance/approval",
        process_model_display_name="Approval",
        process_initiator_id=user.id,
        bpmn_process_definition_id=definition.id,
        status=ProcessInstanceStatus.complete.value,
        start_in_seconds=1_700_000_000,
        end_in_seconds=1_700_000_042,
        created_at_in_seconds=1_700_000_000,
        updated_at_in_seconds=1_700_000_042,
    )
    db_session.add(instance)
    db_session.flush()
    caplog.set_level(logging.INFO, logger="m8flow_backend.workflow")

    status = workflow._emit_process_instance_terminal_log(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id
    )

    assert status == "complete"
    records = [r for r in caplog.records if r.getMessage() == "process instance completed"]
    assert len(records) == 1
    assert records[0].duration_seconds == 42.0
    assert records[0].process_instance_status == "complete"
    assert records[0].process_model_identifier == "finance/approval"
    assert records[0].m8flow_tenant_id == tenant.id


def test_catalog_rejects_call_activity(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:callActivity id="x"/></bpmn:definitions>'
    from m8flow_backend.errors import ApiError
    import pytest

    with pytest.raises(ApiError):
        catalog.save(db_session, path="bad/call", xml=xml, tenant_id=tenant.id, user_id=user.id)
