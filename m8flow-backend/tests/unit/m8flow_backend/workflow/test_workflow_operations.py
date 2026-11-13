from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from m8flow_backend import catalog, identity, workflow

BPMN = Path(__file__).resolve().parents[3] / "fixtures" / "invoice_approval_poc.bpmn"


def test_complete_maps_core_errors_before_inspecting_task_wrapper(db_session, monkeypatch):
    from m8flow_backend.errors import ApiError
    from m8flow_core.errors import InvalidStateError

    core_error = InvalidStateError("task is already complete")
    core_error.task = SimpleNamespace(id="automatic-task")
    work_item = SimpleNamespace(
        process_instance_id=42,
        m8f_tenant_id="tenant-a",
        task_guid="user-task",
    )
    monkeypatch.setattr(db_session, "get", lambda *_args, **_kwargs: work_item)
    monkeypatch.setattr(workflow, "_reject_task_write_if_instance_suspended", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_reject_in_app_completion_of_external_form_task", lambda *_args, **_kwargs: None)

    def _raise_core_error(*_args, **_kwargs):
        raise core_error

    monkeypatch.setattr(workflow.api, "execute_command", _raise_core_error)

    with pytest.raises(ApiError) as raised:
        workflow.complete(
            db_session,
            tenant_id="tenant-a",
            work_item_id=1,
            user_id=2,
        )

    assert raised.value.error_code == "invalid_state"
    assert raised.value.status_code == 409
    assert raised.value.message == "task is already complete"


def test_complete_propagates_same_named_exception_from_unrelated_module(db_session, monkeypatch, caplog):
    exception_type = type("WorkflowTaskException", (RuntimeError,), {})
    ordinary_error = exception_type("ordinary completion failure")
    ordinary_error.task = SimpleNamespace(id="not-a-core-wrapper")
    ordinary_error.task.task_spec = SimpleNamespace(bpmn_name="Unrelated task")
    work_item = SimpleNamespace(
        process_instance_id=42,
        m8f_tenant_id="tenant-a",
        task_guid="user-task",
    )
    monkeypatch.setattr(db_session, "get", lambda *_args, **_kwargs: work_item)
    monkeypatch.setattr(workflow, "_reject_task_write_if_instance_suspended", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_reject_in_app_completion_of_external_form_task", lambda *_args, **_kwargs: None)

    def _raise_ordinary_error(*_args, **_kwargs):
        raise ordinary_error

    monkeypatch.setattr(workflow.api, "execute_command", _raise_ordinary_error)

    with pytest.raises(RuntimeError, match="ordinary completion failure") as raised:
        workflow.complete(
            db_session,
            tenant_id="tenant-a",
            work_item_id=1,
            user_id=2,
        )

    assert raised.value is ordinary_error
    assert "Propagating unrecognized task-context exception" in caplog.text


def test_workflow_task_exception_context_requires_spiff_module_and_task_spec():
    task = SimpleNamespace(
        id="script-task",
        task_spec=SimpleNamespace(bpmn_name="Failing script"),
    )
    exception_type = type(
        "WorkflowTaskException",
        (RuntimeError,),
        {"__module__": "SpiffWorkflow.bpmn.exceptions"},
    )
    wrapped_error = exception_type("script step failed")
    wrapped_error.task = task

    assert workflow._workflow_task_exception_context(wrapped_error) == (task, task.task_spec)

    wrapped_error.task = SimpleNamespace(id="script-task")
    assert workflow._workflow_task_exception_context(wrapped_error) is None


@pytest.mark.parametrize("failure_kind", ["service", "script"])
@pytest.mark.parametrize("completion_context", ["missing", "incomplete", "tenant_mismatch"])
def test_complete_does_not_commit_automatic_failure_without_verified_submission(
    db_session, monkeypatch, caplog, failure_kind, completion_context
):
    from m8flow_core.errors import ServiceTaskExecutionError

    tenant_id = "tenant-a\r\nforged"
    process_instance_id = "42\r\nforged"

    if failure_kind == "service":
        failure = ServiceTaskExecutionError("connector failed")
    else:
        exception_type = type(
            "WorkflowTaskException",
            (RuntimeError,),
            {"__module__": "SpiffWorkflow.bpmn.exceptions"},
        )
        failure = exception_type("script failed")
        failure.task = SimpleNamespace(
            id="script-task",
            task_spec=SimpleNamespace(bpmn_name="Failing script"),
        )

    if completion_context == "missing":
        work_item = None
    else:
        work_item = SimpleNamespace(
            id=1,
            process_instance_id=process_instance_id,
            m8f_tenant_id="tenant-b" if completion_context == "tenant_mismatch" else tenant_id,
            task_guid="user-task",
        )

    monkeypatch.setattr(db_session, "get", lambda *_args, **_kwargs: work_item)
    monkeypatch.setattr(db_session, "scalar", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(workflow, "_reject_task_write_if_instance_suspended", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_reject_in_app_completion_of_external_form_task", lambda *_args, **_kwargs: None)
    commit_calls: list[bool] = []
    command_calls: list[object] = []
    monkeypatch.setattr(db_session, "commit", lambda: commit_calls.append(True))

    def _raise_failure(_session, command):
        command_calls.append(command)
        raise failure

    monkeypatch.setattr(workflow.api, "execute_command", _raise_failure)

    with pytest.raises(type(failure)) as raised:
        workflow.complete(db_session, tenant_id=tenant_id, work_item_id=1, user_id=2)

    assert raised.value is failure
    assert commit_calls == []
    # The failed wrapper is the only command attempted. In particular, the
    # recovery path must not try to error a process instance when the work item
    # is absent or belongs to a different tenant.
    assert len(command_calls) == 1
    assert type(command_calls[0]).__name__ == "CompleteTaskCommand"
    warning = next(record for record in caplog.records if record.getMessage().startswith("Not committing"))
    assert warning.tenant_id == "tenant-aforged"
    if completion_context in {"missing", "tenant_mismatch"}:
        assert warning.process_instance_id == "None"
    else:
        assert warning.process_instance_id == "42forged"
    assert "\r" not in warning.tenant_id and "\n" not in warning.tenant_id
    assert "\r" not in warning.process_instance_id and "\n" not in warning.process_instance_id


def test_script_automatic_step_error_masks_token_in_response_and_record(db_session, monkeypatch):
    from m8flow_backend.errors import ApiError

    exception_type = type(
        "WorkflowTaskException",
        (RuntimeError,),
        {"__module__": "SpiffWorkflow.bpmn.exceptions"},
    )
    failure = exception_type("script failed with token=script-secret-123")
    failure.task = SimpleNamespace(
        id="failed-script-task",
        task_spec=SimpleNamespace(bpmn_name="Failing script"),
    )
    work_item = SimpleNamespace(
        id=1,
        process_instance_id=42,
        m8f_tenant_id="tenant-a",
        task_guid="submitted-user-task",
    )
    monkeypatch.setattr(db_session, "get", lambda *_args, **_kwargs: work_item)
    monkeypatch.setattr(db_session, "scalar", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(workflow, "_reject_task_write_if_instance_suspended", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_reject_in_app_completion_of_external_form_task", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_record_task_completed_event_if_missing", lambda *_args, **_kwargs: False)
    recorded_errors: list[dict[str, object]] = []
    monkeypatch.setattr(
        workflow,
        "_record_process_instance_error",
        lambda _session, **kwargs: recorded_errors.append(kwargs),
    )
    monkeypatch.setattr(workflow, "record_task_completed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(db_session, "commit", lambda: None)
    command_calls = 0

    def _execute_command(_session, _command):
        nonlocal command_calls
        command_calls += 1
        if command_calls == 1:
            raise failure
        return None

    monkeypatch.setattr(workflow.api, "execute_command", _execute_command)

    with pytest.raises(ApiError) as raised:
        workflow.complete(db_session, tenant_id="tenant-a", work_item_id=1, user_id=2)

    body = raised.value.to_dict()
    assert "script-secret-123" not in body["message"]
    assert "script-secret-123" not in body["automatic_step_error_message"]
    assert "[redacted]" in body["message"]
    assert "[redacted]" in body["automatic_step_error_message"]
    assert len(recorded_errors) == 1
    assert "script-secret-123" not in recorded_errors[0]["message"]
CALL_ACTIVITY_PARENT_BPMN = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_simple_call_parent" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:scriptTask id="set" scriptFormat="python"><bpmn:script>number = 21</bpmn:script></bpmn:scriptTask>
    <bpmn:callActivity id="call" calledElement="Process_simple_call_child" />
    <bpmn:scriptTask id="check" scriptFormat="python"><bpmn:script>call_ok = child_result == 42
if not call_ok: raise Exception('call activity FAILED')</bpmn:script></bpmn:scriptTask>
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="set" />
    <bpmn:sequenceFlow id="f2" sourceRef="set" targetRef="call" />
    <bpmn:sequenceFlow id="f3" sourceRef="call" targetRef="check" />
    <bpmn:sequenceFlow id="f4" sourceRef="check" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>
"""
CALL_ACTIVITY_CHILD_BPMN = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_simple_call_child" isExecutable="true">
    <bpmn:startEvent id="child_start" />
    <bpmn:scriptTask id="calculate" scriptFormat="python"><bpmn:script>child_result = number * 2</bpmn:script></bpmn:scriptTask>
    <bpmn:endEvent id="child_end" />
    <bpmn:sequenceFlow id="child_f1" sourceRef="child_start" targetRef="calculate" />
    <bpmn:sequenceFlow id="child_f2" sourceRef="calculate" targetRef="child_end" />
  </bpmn:process>
</bpmn:definitions>
"""


def _seed_actor(
    session,
    tenant_id: str = "tenant-a",
    *,
    username: str = "editor",
    service_id: str = "editor-1",
):
    from m8flow_core.services.authorization import ensure_v1_role

    tenant = identity.ensure_tenant(session, tenant_id=tenant_id, slug=tenant_id)
    user = identity.ensure_user(
        session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=service_id,
        email=f"{username}@example.test",
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


def _add_malformed_published_definition(
    session,
    tenant_id: str,
    process_model_identifier: str,
    *,
    bpmn_identifier: str | None = None,
) -> None:
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    catalog.add_process_model(
        {"id": process_model_identifier, "status": catalog.PROCESS_MODEL_STATUS_PUBLISHED},
        tenant_id=tenant_id,
    )
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant_id,
        process_xml_digest=f"malformed:{process_model_identifier}",
        bpmn_identifier=bpmn_identifier or process_model_identifier,
        properties_json={},
    )
    definition.process_model_identifier = process_model_identifier
    definition.source_bpmn_xml = "<bpmn:definitions"
    session.add(definition)
    session.flush()


def test_import_start_claim_complete_persists_status_tasks_and_metadata(db_session, tmp_path, monkeypatch, caplog):
    from m8flow_core.models.process_instance import ProcessInstanceStatus
    from m8flow_core.models.process_instance_metadata import ProcessInstanceMetadataModel
    from m8flow_core.models.work_item import WorkItemModel

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
    work_item = db_session.get(WorkItemModel, task.id)
    assert work_item is not None
    assert work_item.completed is False
    assert work_item.actual_owner_id is None
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)
    db_session.refresh(work_item)
    assert work_item.actual_owner_id == user.id
    assert work_item.task_status == "CLAIMED"
    completed = workflow.complete(
        db_session,
        tenant_id=tenant.id,
        work_item_id=task.id,
        user_id=user.id,
        task_payload={"approval_state": "approved", "amount": 42},
    )
    assert completed.id == instance.id
    db_session.refresh(work_item)
    assert work_item.completed is True
    assert work_item.completed_by_user_id == user.id
    assert work_item.task_status == "COMPLETED"
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


def test_call_activity_resolves_child_process_within_tenant(db_session, tmp_path, monkeypatch):
    from m8flow_core.models.process_instance import ProcessInstanceStatus

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )

    instance = workflow.start(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        process_model_identifier="examples/call-parent",
    )

    assert instance.status == ProcessInstanceStatus.complete.value


def test_instance_detail_drills_into_called_child_process(db_session, tmp_path, monkeypatch):
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(db_session, path="examples/call-parent", xml=CALL_ACTIVITY_PARENT_BPMN, tenant_id=tenant.id, user_id=user.id)
    catalog.save(db_session, path="examples/call-child", xml=CALL_ACTIVITY_CHILD_BPMN, tenant_id=tenant.id, user_id=user.id)
    instance = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="examples/call-parent"
    )

    parent = workflow.get_instance_detail_for_designer(db_session, tenant_id=tenant.id, process_instance_id=instance.id)
    call_task = next(t for t in parent["tasks"] if t["bpmn_identifier"] == "call")
    assert call_task["called_process_identifier"] == "Process_simple_call_child"
    assert parent["called_process"] is None
    assert 'id="Process_simple_call_parent"' in parent["bpmn_xml"]

    child = workflow.get_instance_detail_for_designer(
        db_session,
        tenant_id=tenant.id,
        process_instance_id=instance.id,
        bpmn_process_identifier="Process_simple_call_child",
    )
    assert child["called_process"] == {
        "bpmn_process_identifier": "Process_simple_call_child",
        "process_model_identifier": "examples/call-child",
    }
    assert 'id="Process_simple_call_child"' in child["bpmn_xml"]
    states = {t["bpmn_identifier"]: t["state"] for t in child["tasks"]}
    assert states["calculate"] == "COMPLETED"
    assert {"call", "set", "check"}.isdisjoint(states)
    assert not any("::" in identifier for identifier in states)

    # Only a process this instance called: never another model's BPMN.
    with pytest.raises(ApiError) as not_called:
        workflow.get_instance_detail_for_designer(
            db_session,
            tenant_id=tenant.id,
            process_instance_id=instance.id,
            bpmn_process_identifier="Process_simple_call_parent",
        )
    assert not_called.value.status_code == 404


def test_call_activity_selects_latest_revision_when_deduplicating_child_definitions(
    db_session, tmp_path, monkeypatch
):
    from m8flow_core.models.process_instance import ProcessInstanceStatus

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN.replace("child_result == 42", "child_result == 63"),
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    revised_child = CALL_ACTIVITY_CHILD_BPMN.replace("child_result = number * 2", "child_result = number * 3")
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=revised_child,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    status_lookups = []
    process_model_status = catalog.process_model_status

    def track_process_model_status(*, tenant_id, process_model_identifier):
        status_lookups.append(process_model_identifier)
        return process_model_status(
            tenant_id=tenant_id,
            process_model_identifier=process_model_identifier,
        )

    monkeypatch.setattr(catalog, "process_model_status", track_process_model_status)

    instance = workflow.start(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        process_model_identifier="examples/call-parent",
    )

    assert instance.status == ProcessInstanceStatus.complete.value
    assert status_lookups.count("examples/call-child") == 1


def test_call_activity_reports_unavailable_publication_status_for_matching_child(
    db_session, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from m8flow_core.errors import CallActivityResolutionError
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    lookups = []

    def unavailable_status(*, tenant_id, process_model_identifier):
        lookups.append(process_model_identifier)
        raise ApiError("invalid_process_model", "Catalog metadata unavailable", 404)

    monkeypatch.setattr(catalog, "process_model_status", unavailable_status)
    resolver = workflow._call_activity_resolver(db_session)

    with pytest.raises(CallActivityResolutionError, match="Could not determine publication status"):
        resolver(
            SimpleNamespace(
                tenant_id=tenant.id,
                called_element="Process_simple_call_child",
            )
        )

    assert lookups == ["examples/call-child"]


def test_call_activity_resolver_scans_many_definitions_once_and_selects_latest_revision(
    db_session, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from defusedxml import ElementTree
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, _user = _seed_actor(db_session)
    child_model = "examples/call-child"
    revision_count = 15
    unrelated_model_count = 10
    all_xml = []

    catalog.add_process_model(
        {"id": child_model, "status": catalog.PROCESS_MODEL_STATUS_PUBLISHED},
        tenant_id=tenant.id,
    )
    for revision in range(revision_count):
        child_xml = CALL_ACTIVITY_CHILD_BPMN.replace(
            "child_result = number * 2", f"child_result = number * {revision + 1}"
        )
        all_xml.append(child_xml)
        definition = BpmnProcessDefinitionModel(
            m8f_tenant_id=tenant.id,
            process_xml_digest=f"stress-child-revision-{revision}",
            bpmn_identifier=child_model,
            properties_json={},
            created_at=datetime(2026, 1, 1, 0, 0, revision, tzinfo=UTC),
        )
        definition.source_bpmn_xml = child_xml
        db_session.add(definition)

    for index in range(unrelated_model_count):
        model_identifier = f"examples/unrelated-{index}"
        catalog.add_process_model(
            {"id": model_identifier, "status": catalog.PROCESS_MODEL_STATUS_PUBLISHED},
            tenant_id=tenant.id,
        )
        unrelated_xml = CALL_ACTIVITY_CHILD_BPMN.replace(
            "Process_simple_call_child", f"Process_unrelated_{index}"
        )
        all_xml.append(unrelated_xml)
        definition = BpmnProcessDefinitionModel(
            m8f_tenant_id=tenant.id,
            process_xml_digest=f"stress-unrelated-{index}",
            bpmn_identifier=model_identifier,
            properties_json={},
            created_at=datetime(2026, 1, 1, 0, 1, index, tzinfo=UTC),
        )
        definition.source_bpmn_xml = unrelated_xml
        db_session.add(definition)
    db_session.flush()

    parse_calls = []
    original_fromstring = ElementTree.fromstring

    def count_parse(xml, *args, **kwargs):
        parse_calls.append(xml)
        return original_fromstring(xml, *args, **kwargs)

    monkeypatch.setattr(ElementTree, "fromstring", count_parse)
    resolver = workflow._call_activity_resolver(db_session)
    resolved = resolver(
        SimpleNamespace(tenant_id=tenant.id, called_element="Process_simple_call_child")
    )

    assert len(parse_calls) == revision_count + unrelated_model_count
    assert resolved.bpmn_xml == all_xml[revision_count - 1]

    cached_resolution = resolver(
        SimpleNamespace(tenant_id=tenant.id, called_element="Process_simple_call_child")
    )
    assert len(parse_calls) == revision_count + unrelated_model_count
    assert cached_resolution.bpmn_xml == all_xml[revision_count - 1]

    new_revision_xml = CALL_ACTIVITY_CHILD_BPMN.replace(
        "child_result = number * 2", "child_result = number * 100"
    )
    new_revision = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant.id,
        process_xml_digest="stress-child-revision-newest",
        bpmn_identifier=child_model,
        properties_json={},
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    new_revision.source_bpmn_xml = new_revision_xml
    db_session.add(new_revision)
    db_session.flush()
    parse_calls.clear()

    refreshed_resolution = resolver(
        SimpleNamespace(tenant_id=tenant.id, called_element="Process_simple_call_child")
    )
    assert len(parse_calls) == revision_count + unrelated_model_count + 1
    assert refreshed_resolution.bpmn_xml == new_revision_xml


def test_catalog_save_accepts_call_activity_without_resolving_child_at_import_time(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)

    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )

    assert catalog.read_primary_bpmn(
        tenant_id=tenant.id,
        process_model_identifier="examples/call-parent",
    ) is not None


def test_call_activity_rejects_ambiguous_published_child_processes(db_session, tmp_path, monkeypatch):
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child-a",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    second_child = CALL_ACTIVITY_CHILD_BPMN.replace(
        "child_result = number * 2", "child_result = number + 21"
    )
    catalog.save(
        db_session,
        path="examples/call-child-b",
        xml=second_child,
        tenant_id=tenant.id,
        user_id=user.id,
    )

    with pytest.raises(ApiError) as error:
        workflow.start(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            process_model_identifier="examples/call-parent",
        )

    assert error.value.error_code == "validation_error"
    assert "More than one published child process" in str(error.value)
    assert "Process_simple_call_child" in str(error.value)


def test_call_activity_rejects_unpublished_child_process(db_session, tmp_path, monkeypatch):
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.add_process_model(
        {"id": "examples/call-child", "status": catalog.PROCESS_MODEL_STATUS_DRAFT},
        tenant_id=tenant.id,
    )

    with pytest.raises(ApiError) as error:
        workflow.start(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            process_model_identifier="examples/call-parent",
        )

    assert error.value.error_code == "validation_error"
    assert "No published child process" in str(error.value)
    assert "Process_simple_call_child" in str(error.value)


def test_call_activity_logs_malformed_stored_definition_and_resolves_valid_child(
    db_session, tmp_path, monkeypatch, caplog
):
    from m8flow_core.models.process_instance import ProcessInstanceStatus

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    _add_malformed_published_definition(
        db_session,
        tenant.id,
        "examples/broken-child",
        bpmn_identifier="Broken_child_definition",
    )
    caplog.set_level(logging.WARNING, logger="m8flow_backend.workflow")

    instance = workflow.start(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        process_model_identifier="examples/call-parent",
    )

    assert instance.status == ProcessInstanceStatus.complete.value
    warning = next(
        record
        for record in caplog.records
        if record.name == "m8flow_backend.workflow" and "could not be parsed" in record.getMessage()
    )
    assert "Broken_child_definition" in warning.getMessage()
    assert "examples/broken-child" in warning.getMessage()
    assert warning.bpmn_identifier == "Broken_child_definition"
    assert warning.process_model_identifier == "examples/broken-child"


def test_call_activity_reports_malformed_published_definitions_when_child_cannot_be_confirmed(
    db_session, tmp_path, monkeypatch
):
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    _add_malformed_published_definition(db_session, tenant.id, "examples/broken-child")

    with pytest.raises(ApiError) as error:
        workflow.start(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            process_model_identifier="examples/call-parent",
        )

    assert error.value.error_code == "validation_error"
    assert "published BPMN definitions could not be parsed" in str(error.value)
    assert "examples/broken-child" in str(error.value)


def test_call_activity_does_not_resolve_child_from_another_tenant(db_session, tmp_path, monkeypatch):
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    parent_tenant, parent_user = _seed_actor(db_session, tenant_id="tenant-parent")
    child_tenant, child_user = _seed_actor(
        db_session, tenant_id="tenant-child", username="child-editor", service_id="child-editor-1"
    )
    catalog.save(
        db_session,
        path="examples/call-parent",
        xml=CALL_ACTIVITY_PARENT_BPMN,
        tenant_id=parent_tenant.id,
        user_id=parent_user.id,
    )
    catalog.save(
        db_session,
        path="examples/call-child",
        xml=CALL_ACTIVITY_CHILD_BPMN,
        tenant_id=child_tenant.id,
        user_id=child_user.id,
    )

    with pytest.raises(ApiError) as error:
        workflow.start(
            db_session,
            tenant_id=parent_tenant.id,
            user_id=parent_user.id,
            process_model_identifier="examples/call-parent",
        )

    assert error.value.error_code == "validation_error"
    assert "tenant-parent" in str(error.value)


def test_bpmn_import_persists_existing_model_dmn_source(db_session, tmp_path, monkeypatch):
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session, tenant_id="tenant-dmn")
    model_id = "invoices/dmn-approval"
    model_dir = tmp_path / tenant.id / model_id
    model_dir.mkdir(parents=True)
    dmn_xml = catalog.default_dmn_xml(decision_id="approval_route")
    (model_dir / "approval-route.dmn").write_text(dmn_xml, encoding="utf-8")

    catalog.save(
        db_session,
        path=model_id,
        xml=BPMN.read_text(encoding="utf-8"),
        tenant_id=tenant.id,
        user_id=user.id,
        file_name="approval.bpmn",
    )

    definition = (
        db_session.query(BpmnProcessDefinitionModel)
        .filter_by(m8f_tenant_id=tenant.id)
        .one()
    )
    assert definition.source_dmn_xml == dmn_xml


_DECISION_BPMN = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="decide" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:businessRuleTask id="Decide">
      <bpmn:extensionElements>
        <spiffworkflow:calledDecisionId>approval_route</spiffworkflow:calledDecisionId>
      </bpmn:extensionElements>
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:businessRuleTask>
    <bpmn:endEvent id="EndEvent_1"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Decide" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Decide" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def _decision_dmn(decision_id: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="Definitions_1" name="{decision_id}" namespace="https://m8flow.example/dmn">
  <decision id="{decision_id}" name="{decision_id}">
    <decisionTable id="DecisionTable_1">
      <input id="Input_1"><inputExpression id="InputExpression_1" typeRef="integer"><text>1</text></inputExpression></input>
      <output id="Output_1" name="route" typeRef="string" />
      <rule id="Rule_1">
        <inputEntry id="InputEntry_1"><text>1</text></inputEntry>
        <outputEntry id="OutputEntry_1"><text>"{decision_id}"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
"""


def _seed_two_dmn_model(tmp_path, tenant_id: str, model_id: str) -> str:
    """Model whose business rule task calls the decision in the second DMN file
    by name; the first one ("a-other.dmn") is unrelated (M8F-657)."""
    model_dir = tmp_path / tenant_id / model_id
    model_dir.mkdir(parents=True)
    (model_dir / "a-other.dmn").write_text(_decision_dmn("other_decision"), encoding="utf-8")
    called_dmn = _decision_dmn("approval_route")
    (model_dir / "route.dmn").write_text(called_dmn, encoding="utf-8")
    return called_dmn


def test_start_runs_the_dmn_the_business_rule_task_calls(db_session, tmp_path, monkeypatch):
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session, tenant_id="tenant-dmn-pick")
    model_id = "invoices/decide"
    called_dmn = _seed_two_dmn_model(tmp_path, tenant.id, model_id)

    catalog.save(
        db_session, path=model_id, xml=_DECISION_BPMN, tenant_id=tenant.id, user_id=user.id, file_name="decide.bpmn"
    )
    definition = db_session.query(BpmnProcessDefinitionModel).filter_by(m8f_tenant_id=tenant.id).one()
    assert definition.source_dmn_xml == called_dmn

    instance = workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier=model_id)
    assert instance.status == "complete"


def test_start_replaces_a_stored_dmn_that_is_not_the_called_one(db_session, tmp_path, monkeypatch):
    """A definition imported before the fix keeps the wrong DMN; Start must run
    the model's called DMN as it is on disk, not that stale copy."""
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session, tenant_id="tenant-dmn-stale")
    model_id = "invoices/decide"
    called_dmn = _seed_two_dmn_model(tmp_path, tenant.id, model_id)
    catalog.save(
        db_session, path=model_id, xml=_DECISION_BPMN, tenant_id=tenant.id, user_id=user.id, file_name="decide.bpmn"
    )
    definition = db_session.query(BpmnProcessDefinitionModel).filter_by(m8f_tenant_id=tenant.id).one()
    definition.source_dmn_xml = _decision_dmn("other_decision")
    db_session.flush()

    instance = workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier=model_id)

    assert instance.status == "complete"
    db_session.refresh(definition)
    assert definition.source_dmn_xml == called_dmn


def test_adding_an_unrelated_dmn_keeps_the_called_one(db_session, tmp_path, monkeypatch):
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session, tenant_id="tenant-dmn-add")
    model_id = "invoices/decide"
    model_dir = tmp_path / tenant.id / model_id
    model_dir.mkdir(parents=True)
    called_dmn = _decision_dmn("approval_route")
    (model_dir / "route.dmn").write_text(called_dmn, encoding="utf-8")
    catalog.save(
        db_session, path=model_id, xml=_DECISION_BPMN, tenant_id=tenant.id, user_id=user.id, file_name="decide.bpmn"
    )
    catalog._write_process_model_json(tenant.id, model_id, {"primary_file_name": "decide.bpmn"})

    catalog.create_model_file(
        db_session,
        tenant_id=tenant.id,
        process_model_identifier=model_id,
        file_name="a-other.dmn",
        content=None,
        user_id=user.id,
    )

    definition = db_session.query(BpmnProcessDefinitionModel).filter_by(m8f_tenant_id=tenant.id).one()
    assert definition.source_dmn_xml == called_dmn


def test_model_files_list_the_decision_id_a_business_rule_task_calls(tmp_path, monkeypatch):
    """The designer's decision dropdown writes this id, not the file name, into
    calledDecisionId -- a file name fails Start with "No DMN Diagram" (M8F-657)."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    _seed_two_dmn_model(tmp_path, "tenant-dmn-list", "invoices/decide")
    (tmp_path / "tenant-dmn-list" / "invoices/decide" / "decide.bpmn").write_text(_DECISION_BPMN, encoding="utf-8")

    files = {f["name"]: f for f in catalog.list_model_files(tenant_id="tenant-dmn-list", process_model_identifier="invoices/decide")}

    assert files["route.dmn"]["decision_id"] == "approval_route"
    assert files["a-other.dmn"]["decision_id"] == "other_decision"
    assert "decision_id" not in files["decide.bpmn"]


def test_reconcile_pending_tasks_is_idempotent_and_does_not_claim_task(db_session):
    import uuid

    from m8flow_core.models.bpmn_process import BpmnProcessModel
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_core.models.group import GroupModel
    from m8flow_core.models.work_item import WorkItemModel
    from m8flow_core.models.work_item_user import WorkItemUserModel
    from m8flow_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus
    from m8flow_core.models.user_group_assignment import UserGroupAssignmentModel

    tenant, user = _seed_actor(db_session, tenant_id="tenant-reconcile")
    lane_name = "Submitters"
    lane_group_id = workflow.api.resolve_lane_assignment_id(lane_name, tenant.id)
    db_session.add(
        GroupModel(
            id=lane_group_id,
            name=lane_name,
            identifier=f"{tenant.id}:{lane_name}",
            authorization_key=f"authorization:lane:{lane_group_id}",
        )
    )
    db_session.add(
        UserGroupAssignmentModel(
            user_id=user.id,
            group_id=lane_group_id,
        )
    )
    instance = ProcessInstanceModel(
        m8f_tenant_id=tenant.id,
        process_model_identifier="reconcile/process",
        process_model_display_name="Reconcile process",
        process_initiator_id=user.id,
        status=ProcessInstanceStatus.user_input_required.value,
    )
    db_session.add(instance)
    db_session.flush()
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant.id,
        process_xml_digest=uuid.uuid4().hex,
        bpmn_identifier="reconcile/process",
        properties_json={},
    )
    db_session.add(definition)
    db_session.flush()
    instance.bpmn_process_definition_id = definition.id
    bpmn_process = BpmnProcessModel(
        m8f_tenant_id=tenant.id,
        bpmn_process_definition_id=definition.id,
        properties_json={},
        json_data_hash=uuid.uuid4().hex,
    )
    db_session.add(bpmn_process)
    db_session.flush()
    from m8flow_core.models.task import TaskModel
    from m8flow_core.models.task_definition import TaskDefinitionModel

    task_definition = TaskDefinitionModel(
        m8f_tenant_id=tenant.id,
        bpmn_process_definition_id=definition.id,
        bpmn_identifier="submit",
        bpmn_name="Submit",
        typename="UserTask",
        properties_json={},
    )
    db_session.add(task_definition)
    db_session.flush()
    guid = str(uuid.uuid4())
    db_session.add(
        TaskModel(
            m8f_tenant_id=tenant.id,
            guid=guid,
            bpmn_process_id=bpmn_process.id,
            process_instance_id=instance.id,
            task_definition_id=task_definition.id,
            state="READY",
            properties_json={"lane": lane_name},
            json_data_hash=uuid.uuid4().hex,
            python_env_data_hash=uuid.uuid4().hex,
        )
    )
    db_session.flush()
    task = WorkItemModel(
        m8f_tenant_id=tenant.id,
        process_instance_id=instance.id,
        lane_assignment_id=lane_group_id,
        task_guid=guid,
        task_status="READY",
        completed=False,
        actual_owner_id=None,
    )
    db_session.add(task)
    db_session.flush()

    first = workflow.reconcile_pending_tasks_for_user(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
    )
    second = workflow.reconcile_pending_tasks_for_user(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
    )

    assert [item.id for item in first] == [task.id]
    assert second == []
    assignments = db_session.query(WorkItemUserModel).filter_by(work_item_id=task.id).all()
    assert [(item.user_id, item.added_by) for item in assignments] == [(user.id, "lane_assignment")]
    assert task.actual_owner_id is None


def test_emit_process_instance_terminal_log_records_duration(db_session, caplog):
    import uuid

    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_core.models.process_instance import ProcessInstanceModel, ProcessInstanceStatus

    tenant, user = _seed_actor(db_session, tenant_id="tenant-metrics")
    definition = BpmnProcessDefinitionModel(
        m8f_tenant_id=tenant.id,
        process_xml_digest=uuid.uuid4().hex,
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
        started_at=datetime.fromtimestamp(1_700_000_000, UTC),
        ended_at=datetime.fromtimestamp(1_700_000_042, UTC),
        created_at=datetime.fromtimestamp(1_700_000_000, UTC),
        updated_at=datetime.fromtimestamp(1_700_000_042, UTC),
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


@pytest.mark.parametrize("sequential", [True, False], ids=["sequential", "default-parallel"])
def test_catalog_accepts_multi_instance_task(db_session, tmp_path, monkeypatch, sequential):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    fixture = BPMN.with_name("simple-multi-instance.bpmn")
    xml = fixture.read_text(encoding="utf-8")
    if sequential:
        xml = xml.replace(
            "<bpmn:multiInstanceLoopCharacteristics>",
            '<bpmn:multiInstanceLoopCharacteristics isSequential="true">',
        )
    else:
        xml = xml.replace(' isSequential="true"', "")

    catalog.save(
        db_session,
        path="bpmn-gap-tracker-tests/simple-multi-instance",
        xml=xml,
        tenant_id=tenant.id,
        user_id=user.id,
    )

    saved_file = (
        tmp_path
        / tenant.id
        / "bpmn-gap-tracker-tests"
        / "simple-multi-instance"
        / "simple-multi-instance.bpmn"
    )
    assert saved_file.read_text(encoding="utf-8") == xml


def test_catalog_accepts_parallel_multi_instance_completion_condition(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.with_name("simple-multi-instance.bpmn").read_text(encoding="utf-8")
    xml = xml.replace(
        "<bpmn:loopDataOutputRef>par_out</bpmn:loopDataOutputRef>",
        "<bpmn:loopDataOutputRef>par_out</bpmn:loopDataOutputRef>"
        "<bpmn:completionCondition>nrOfCompletedInstances &gt;= 2</bpmn:completionCondition>",
        1,
    )

    catalog.save(db_session, path="p/parallel-condition", xml=xml, tenant_id=tenant.id, user_id=user.id)

    saved = tmp_path / tenant.id / "p" / "parallel-condition" / "parallel-condition.bpmn"
    assert "nrOfCompletedInstances &gt;= 2" in saved.read_text(encoding="utf-8")


def test_catalog_rejects_negative_multi_instance_cardinality(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.with_name("simple-multi-instance.bpmn").read_text(encoding="utf-8")
    xml = xml.replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopCardinality>-1</bpmn:loopCardinality>",
        1,
    )
    from m8flow_backend.errors import ApiError

    with pytest.raises(ApiError) as error:
        catalog.save(db_session, path="bad/negative-cardinality", xml=xml, tenant_id=tenant.id, user_id=user.id)

    assert error.value.status_code == 400
    assert error.value.error_code == "invalid_process_model"
    assert "loopCardinality must be zero or a positive integer" in str(error.value)


@pytest.mark.parametrize(
    "output_item",
    [
        '<bpmn:outputDataItem name="o1" />',
        '<bpmn:outputDataItem id="" name="o1" />',
        "<bpmn:outputDataItem />",
        '<bpmn:outputDataItem id="o1 with space" name="o1" />',
        '<bpmn:outputDataItem id="${o1}" name="o1" />',
    ],
    ids=["missing-id", "empty-id", "missing-attributes", "space-in-id", "expression-as-id"],
)
def test_catalog_rejects_multi_instance_output_item_without_valid_id(
    db_session, tmp_path, monkeypatch, output_item
):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.with_name("simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        '<bpmn:outputDataItem id="o1" name="o1" />',
        output_item,
        1,
    )
    from m8flow_backend.errors import ApiError

    with pytest.raises(ApiError) as error:
        catalog.save(db_session, path="bad/output-item", xml=xml, tenant_id=tenant.id, user_id=user.id)

    assert error.value.status_code == 400
    assert error.value.error_code == "invalid_process_model"
    assert "outputDataItem must include a non-empty valid BPMN id" in str(error.value)


def test_catalog_rejects_multi_instance_input_item_with_invalid_bpmn_id(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.with_name("simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        '<bpmn:inputDataItem id="it1" name="it1" />',
        '<bpmn:inputDataItem id="item value" name="it1" />',
        1,
    )
    from m8flow_backend.errors import ApiError

    with pytest.raises(ApiError) as error:
        catalog.save(db_session, path="bad/input-item-id", xml=xml, tenant_id=tenant.id, user_id=user.id)

    assert error.value.status_code == 400
    assert error.value.error_code == "invalid_process_model"
    assert "inputDataItem must include a non-empty valid BPMN id" in str(error.value)


@pytest.mark.parametrize("entrypoint", ["save", "file_import"], ids=["save", "file-import"])
@pytest.mark.parametrize(
    "malformed_xml",
    [
        "<bpmn:definitions>",
        "<bpmn:definitions><bpmn:process></bpmn:definitions>",
        "<bpmn:definitions><bpmn:callActivity",
    ],
    ids=["unclosed-root", "mismatched-tags", "partial-unsupported-construct"],
)
def test_catalog_malformed_bpmn_has_consistent_error(db_session, tmp_path, monkeypatch, entrypoint, malformed_xml):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    model_id = "bpmn-gap-tracker-tests/malformed"
    if entrypoint == "file_import":
        catalog.save(
            db_session,
            path=model_id,
            xml=BPMN.with_name("simple-multi-instance.bpmn").read_text(encoding="utf-8"),
            tenant_id=tenant.id,
            user_id=user.id,
        )

    from m8flow_backend.errors import ApiError

    with pytest.raises(ApiError) as error:
        if entrypoint == "save":
            catalog.save(
                db_session,
                path=model_id,
                xml=malformed_xml,
                tenant_id=tenant.id,
                user_id=user.id,
            )
        else:
            catalog.create_model_file(
                db_session,
                tenant_id=tenant.id,
                process_model_identifier=model_id,
                file_name="uploaded-malformed.bpmn",
                content=malformed_xml.encode("utf-8"),
                user_id=user.id,
            )

    assert error.value.status_code == 400
    assert error.value.error_code == "invalid_process_model"
    assert error.value.message == "BPMN XML is malformed"


def test_metadata_values_are_truncated_to_the_column_width():
    """`process_instance_metadata.value` is a bounded varchar: PostgreSQL raises
    StringDataRightTruncation rather than trimming, so one long form field used to fail
    the INSERT and take the whole task completion down with it."""
    from m8flow_backend.workflow import _METADATA_VALUE_MAX_LENGTH, _stringify_metadata_value

    assert len(_stringify_metadata_value("x" * 5000)) == _METADATA_VALUE_MAX_LENGTH
    assert len(_stringify_metadata_value({f"k{i}": "v" * 50 for i in range(50)})) == (
        _METADATA_VALUE_MAX_LENGTH
    )
    # Ordinary values are untouched.
    assert _stringify_metadata_value("sonal") == "sonal"
    assert _stringify_metadata_value(42) == "42"


def _start_invoice_instance(db_session, tmp_path, monkeypatch, display_name: str | None = None):
    import json

    for name in (
        "record_process_instance_created",
        "record_process_instance_active_delta",
        "record_process_instance_terminal",
    ):
        monkeypatch.setattr(f"m8flow_backend.workflow.{name}", lambda *_a, **_k: None)
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session,
        path="invoices/approval",
        xml=BPMN.read_text(encoding="utf-8"),
        tenant_id=tenant.id,
        user_id=user.id,
    )
    if display_name is not None:
        meta = tmp_path / tenant.id / "invoices" / "approval" / "process_model.json"
        data = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        data["display_name"] = display_name
        meta.write_text(json.dumps(data), encoding="utf-8")
    instance = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
    )
    return tenant, user, instance


def test_start_uses_process_model_display_name(db_session, tmp_path, monkeypatch):
    from m8flow_core.models.work_item import WorkItemModel

    tenant, _user, instance = _start_invoice_instance(
        db_session, tmp_path, monkeypatch, display_name="Invoice Approval"
    )
    assert instance.process_model_display_name == "Invoice Approval"
    tasks = db_session.query(WorkItemModel).filter_by(process_instance_id=instance.id).all()
    assert tasks and {t.process_model_display_name for t in tasks} == {"Invoice Approval"}
    rows, _ = workflow.list_instances_for_designer(db_session, tenant_id=tenant.id)
    assert rows[0]["process_model_display_name"] == "Invoice Approval"


def test_read_repairs_instances_stored_with_model_id_as_display_name(db_session, tmp_path, monkeypatch):
    tenant, _user, instance = _start_invoice_instance(
        db_session, tmp_path, monkeypatch, display_name="Invoice Approval"
    )
    instance.process_model_display_name = "invoices/approval"  # pre-fix row
    db_session.flush()
    detail = workflow.get_instance_detail_for_designer(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id
    )
    assert detail["process_model_display_name"] == "Invoice Approval"


def test_instance_diagram_shows_task_failed_event_as_error_even_if_engine_terminated_task(
    db_session, tmp_path, monkeypatch
):
    from m8flow_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_core.models.task import TaskModel
    from m8flow_core.models.task_definition import TaskDefinitionModel

    tenant, user, instance = _start_invoice_instance(db_session, tmp_path, monkeypatch)
    task = (
        db_session.query(TaskModel)
        .join(TaskDefinitionModel, TaskDefinitionModel.id == TaskModel.task_definition_id)
        .filter(
            TaskModel.process_instance_id == instance.id,
            TaskDefinitionModel.bpmn_identifier == "approve",
        )
        .one()
    )
    # Spiff marks the throwing task TERMINATED when it unwinds after an error.
    task.state = "TERMINATED"
    db_session.add(
        ProcessInstanceEventModel(
            m8f_tenant_id=tenant.id,
            process_instance_id=instance.id,
            event_type="task_failed",
            occurred_at=datetime.now(UTC),
            task_guid=task.guid,
        )
    )
    db_session.flush()

    detail = workflow.get_instance_detail_for_designer(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id
    )

    failed_task = next(item for item in detail["tasks"] if item["guid"] == task.guid)
    assert failed_task["state"] == "ERROR"


def test_delete_instance_requires_finished_status_then_removes_run_data(db_session, tmp_path, monkeypatch):
    import pytest
    from m8flow_core.models.work_item import WorkItemModel
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.task import TaskModel

    from m8flow_backend.errors import ApiError

    tenant, user, instance = _start_invoice_instance(db_session, tmp_path, monkeypatch)
    instance_id = instance.id

    with pytest.raises(ApiError) as active:
        workflow.delete_instance(db_session, tenant_id=tenant.id, process_instance_id=instance_id)
    assert active.value.status_code == 409

    with pytest.raises(ApiError) as other_tenant:
        workflow.delete_instance(db_session, tenant_id="tenant-b", process_instance_id=instance_id)
    assert other_tenant.value.status_code == 404

    workflow.terminate_instance(
        db_session, tenant_id=tenant.id, process_instance_id=instance_id, user_id=user.id
    )
    workflow.delete_instance(db_session, tenant_id=tenant.id, process_instance_id=instance_id)
    db_session.expire_all()
    assert db_session.get(ProcessInstanceModel, instance_id) is None
    assert db_session.query(TaskModel).filter_by(process_instance_id=instance_id).count() == 0
    assert db_session.query(WorkItemModel).filter_by(process_instance_id=instance_id).count() == 0


def _seed_submitter(session, tenant):
    """A start-only actor: V1 `user` role, no `process_definition.import` grant."""
    from m8flow_core.services.authorization import ensure_v1_role

    user = identity.ensure_user(
        session,
        username="submitter",
        service="https://example.test/realms/m8flow",
        service_id="submitter-1",
        email="submitter@example.test",
    )
    identity.ensure_membership(session, user, tenant)
    identity.sync_groups(
        session,
        user=user,
        group_identifiers=[f"{tenant.id}:submitter"],
        tenant_id=tenant.id,
    )
    ensure_v1_role(session, tenant_id=tenant.id, role_name="user", user_ids=(user.id,))
    session.flush()
    return user


def _write_unimported_model(tenant_id: str, path: str = "invoices/approval") -> None:
    """The M8F-566 state: the model is on disk (bind mount survives a clean build)
    but its definition is gone from the wiped database."""
    catalog.write_spec_file(
        tenant_id=tenant_id,
        path=path,
        file_name=f"{path.rsplit('/', 1)[-1]}.bpmn",
        content=BPMN.read_bytes(),
    )


def _imported_versions(session, tenant_id: str, path: str = "invoices/approval") -> int:
    from m8flow_core.models.process_model_bpmn_version import ProcessModelBpmnVersionModel

    return (
        session.query(ProcessModelBpmnVersionModel)
        .filter_by(m8f_tenant_id=tenant_id, process_model_identifier=path)
        .count()
    )


def test_start_reimports_model_missing_from_db(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    _write_unimported_model(tenant.id)
    assert _imported_versions(db_session, tenant.id) == 0

    instance = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
    )

    assert instance.id
    assert _imported_versions(db_session, tenant.id) == 1


def test_submitter_can_start_model_missing_from_db(db_session, tmp_path, monkeypatch):
    """Re-import must not need the caller's own import grant, or a submitter (and the
    NATS service user) trades the 404 for a 403."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, _editor = _seed_actor(db_session)
    submitter = _seed_submitter(db_session, tenant)
    _write_unimported_model(tenant.id)

    instance = workflow.start(
        db_session, tenant_id=tenant.id, user_id=submitter.id, process_model_identifier="invoices/approval"
    )

    assert instance.process_initiator_id == submitter.id


def test_start_without_bpmn_on_disk_is_still_404(db_session, tmp_path, monkeypatch):
    import pytest
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)

    with pytest.raises(ApiError) as excinfo:
        workflow.start(
            db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/missing"
        )
    assert excinfo.value.status_code == 404


def test_read_primary_bpmn_does_not_escape_the_tenant_root(tmp_path, monkeypatch):
    """The re-import runs under a scoped import grant, so a `..` model id must not
    pull another tenant's BPMN into this tenant."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    _write_unimported_model("tenant-b")

    assert catalog.read_primary_bpmn(tenant_id="tenant-b", process_model_identifier="invoices/approval")
    assert (
        catalog.read_primary_bpmn(tenant_id="tenant-a", process_model_identifier="../tenant-b/invoices/approval")
        is None
    )


def test_read_primary_bpmn_needs_a_model_below_the_tenant_root(tmp_path, monkeypatch):
    """Ids resolving to the root itself are not a model, so a stray BPMN there is not
    read. (Why the guard is `root in parents`, not `is_relative_to(root)`.)"""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    _write_unimported_model("tenant-a")
    (tmp_path / "tenant-a" / "stray.bpmn").write_bytes(BPMN.read_bytes())

    for model_id in ("", ".", "invoices/..", "invoices/approval/../.."):
        assert catalog.read_primary_bpmn(tenant_id="tenant-a", process_model_identifier=model_id) is None, model_id


def test_read_primary_bpmn_of_a_file_deleted_after_the_checks_is_none(tmp_path, monkeypatch):
    """A model deleted mid-Start maps to the same 404 as one never there, not a 500."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    _write_unimported_model("tenant-a")
    real_is_file = Path.is_file

    def is_file_then_delete(self, *args, **kwargs):
        found = real_is_file(self, *args, **kwargs)
        if found and self.suffix == ".bpmn":
            self.unlink()
        return found

    monkeypatch.setattr(Path, "is_file", is_file_then_delete)

    assert catalog.read_primary_bpmn(tenant_id="tenant-a", process_model_identifier="invoices/approval") is None


def test_read_primary_bpmn_does_not_follow_a_symlink_out_of_the_tenant_root(tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    _write_unimported_model("tenant-b")
    model_dir = tmp_path / "tenant-a" / "invoices" / "approval"
    model_dir.mkdir(parents=True)
    try:
        (model_dir / "approval.bpmn").symlink_to(
            tmp_path / "tenant-b" / "invoices" / "approval" / "approval.bpmn"
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise

    assert catalog.read_primary_bpmn(tenant_id="tenant-a", process_model_identifier="invoices/approval") is None


def test_start_of_a_non_utf8_bpmn_on_disk_is_a_400_not_a_500(db_session, tmp_path, monkeypatch):
    import pytest
    from m8flow_backend.errors import ApiError

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.write_spec_file(
        tenant_id=tenant.id, path="invoices/approval", file_name="approval.bpmn", content=b"\xff\xfe<bpmn/>"
    )

    with pytest.raises(ApiError) as excinfo:
        workflow.start(
            db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
        )
    assert (excinfo.value.status_code, excinfo.value.error_code) == (400, "invalid_file_content")


def test_start_runs_the_bpmn_on_disk_not_an_older_imported_version(db_session, tmp_path, monkeypatch):
    """The catalog lists and guards the file on disk, so Start must run that file too --
    not whichever version the database imported last (e.g. after a spec-dir restore)."""
    from m8flow_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.read_text(encoding="utf-8")
    catalog.save(db_session, path="invoices/approval", xml=xml, tenant_id=tenant.id, user_id=user.id)
    on_disk = xml.replace("</bpmn:definitions>", "<!-- edited outside the app --></bpmn:definitions>")
    catalog.write_spec_file(
        tenant_id=tenant.id, path="invoices/approval", file_name="approval.bpmn", content=on_disk.encode()
    )

    instance = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
    )

    definition = db_session.get(BpmnProcessDefinitionModel, instance.bpmn_process_definition_id)
    assert definition.source_bpmn_xml == on_disk


def test_start_attributes_the_instance_to_the_started_copy(db_session, tmp_path, monkeypatch):
    """Identical XML shares one definition row, which names the model imported last.
    Starting the original must not create (and authorize) the instance as the copy.

    The saves are committed, as they are in real (earlier) requests: core then
    prepares the instance in an independent session that can see the shared
    definition, which used to wait forever on Start's uncommitted import.
    """
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    xml = BPMN.read_text(encoding="utf-8")
    for path in ("invoices/approval", "invoices/approval-copy"):
        catalog.save(db_session, path=path, xml=xml, tenant_id=tenant.id, user_id=user.id)
    db_session.commit()
    imports: list[str] = []
    real_import = workflow.import_definition
    monkeypatch.setattr(
        workflow,
        "import_definition",
        lambda session, **kwargs: imports.append(kwargs["bpmn_identifier"]) or real_import(session, **kwargs),
    )

    first = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
    )
    db_session.commit()  # request boundary
    again = workflow.start(
        db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval"
    )

    assert first.process_model_identifier == again.process_model_identifier == "invoices/approval"
    # Re-pointed once; the second Start finds it already pointing here.
    assert imports == ["invoices/approval"]


def test_starting_an_unchanged_model_does_not_reimport_it(db_session, tmp_path, monkeypatch):
    """Import re-syncs timer-start jobs (recomputing run_at), so a plain Start of an
    already-imported model must not import again -- nor commit the caller's session,
    which only the import path does."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(
        db_session, path="invoices/approval", xml=BPMN.read_text(encoding="utf-8"), tenant_id=tenant.id, user_id=user.id
    )
    imports: list[str] = []
    real_import = workflow.import_definition
    monkeypatch.setattr(
        workflow,
        "import_definition",
        lambda session, **kwargs: imports.append(kwargs["bpmn_identifier"]) or real_import(session, **kwargs),
    )

    commits: list[int] = []
    real_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1) or real_commit())

    workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval")

    assert imports == []
    assert commits == []


def test_start_that_imports_commits_what_the_caller_staged(db_session, tmp_path, monkeypatch):
    """Codifies `start()`'s documented contract: the import path commits the caller's
    session, so a write staged before Start survives a later rollback, as does the import."""
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    _write_unimported_model(tenant.id)
    user.email = "staged@example.test"

    workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="invoices/approval")
    db_session.rollback()

    assert user.email == "staged@example.test"
    assert _imported_versions(db_session, tenant.id) == 1


def test_start_import_policy_grants_the_import_and_nothing_else(db_session):
    from m8flow_core import api
    from m8flow_core.services.authorization import build_authorization_request

    tenant, _editor = _seed_actor(db_session)
    submitter = _seed_submitter(db_session, tenant)

    def allowed(command_key: str) -> bool:
        request = build_authorization_request(
            tenant_id=tenant.id, actor_user_id=submitter.id, command_key=command_key
        )
        return workflow._StartImportPolicy().authorize(db_session, request).allowed

    assert allowed(api.PROCESS_DEFINITION_IMPORT_COMMAND)
    assert not allowed(api.PROCESS_TERMINATE_COMMAND)


_TWO_STEP_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" targetNamespace="http://x">
  <bpmn:process id="two_step" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:userTask id="step1" />
    <bpmn:scriptTask id="script1"><bpmn:script>computed = 7</bpmn:script></bpmn:scriptTask>
    <bpmn:userTask id="step2" />
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="step1" />
    <bpmn:sequenceFlow id="f2" sourceRef="step1" targetRef="script1" />
    <bpmn:sequenceFlow id="f3" sourceRef="script1" targetRef="step2" />
    <bpmn:sequenceFlow id="f4" sourceRef="step2" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def test_finished_tasks_show_their_own_data_not_later_steps(db_session, tmp_path, monkeypatch):
    """Like SpiffArena's per-task json_data: each finished task shows what was in
    scope plus what it set -- never what later steps collected. Core's task rows
    keep {}, so the data is rebuilt from the deltas in the saved workflow state."""
    from sqlalchemy import select

    from m8flow_core.models.task import TaskModel
    from m8flow_core.models.task_definition import TaskDefinitionModel

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(db_session, path="p/two", xml=_TWO_STEP_BPMN, tenant_id=tenant.id, user_id=user.id)
    instance = workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="p/two")
    for payload in ({"amount": 42}, {"ssn": "123-45-6789"}):
        task = workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id)[0]
        workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)
        workflow.complete(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id, task_payload=payload)

    guids = dict(
        db_session.execute(
            select(TaskDefinitionModel.bpmn_identifier, TaskModel.guid)
            .join(TaskModel, TaskModel.task_definition_id == TaskDefinitionModel.id)
            .where(TaskModel.process_instance_id == instance.id)
        ).all()
    )

    def data_of(bpmn_identifier):
        return workflow.get_instance_task_for_designer(
            db_session, tenant_id=tenant.id, process_instance_id=instance.id, task_guid=guids[bpmn_identifier]
        )["data"]

    assert data_of("start") == {}
    assert data_of("step1") == {"amount": 42}
    assert data_of("script1") == {"amount": 42, "computed": 7}
    assert data_of("step2") == {"amount": 42, "computed": 7, "ssn": "123-45-6789"}


def test_task_data_replay_applies_deletions_and_starts_subprocesses_at_their_root():
    from types import SimpleNamespace

    state = {
        "tasks": {
            "root": {"parent": None, "data": {"a": 1}, "delta": {}},
            "t1": {"parent": "root", "data": {}, "delta": {"updates": {"b": 2}, "deletions": ["a"]}},
        },
        "subprocesses": {
            "t1": {
                "tasks": {
                    # Parent lives in the outer workflow, so this root holds full data.
                    "sub_root": {"parent": "t1", "data": {"b": 2, "c": 3}, "delta": {}},
                    "s1": {"parent": "sub_root", "data": {}, "delta": {"updates": {"c": 4}, "deletions": []}},
                }
            }
        },
    }
    instance = SimpleNamespace(workflow_state_json=json.dumps(state))

    assert workflow._task_data_from_workflow_state(instance, "t1") == {"b": 2}
    assert workflow._task_data_from_workflow_state(instance, "s1") == {"b": 2, "c": 4}
    assert workflow._task_data_from_workflow_state(instance, "missing") == {}


def test_terminate_instance_cancels_its_open_external_form_links(db_session, tmp_path, monkeypatch):
    """M8F-575 issue 3: after a terminate the emailed link still reported actionable=true."""
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel

    tenant, user, instance = _start_invoice_instance(db_session, tmp_path, monkeypatch)
    row = ExternalFormRequestModel(
        m8f_tenant_id=tenant.id,
        reference_id="ref-terminate",
        process_instance_id=instance.id,
        task_guid="any-task",
        recipient_user_id=user.id,
        email="r@example.test",
        external_form_url="https://forms.example/f",
        status="notified",
        attempts=1,
    )
    db_session.add(row)
    db_session.flush()

    workflow.terminate_instance(db_session, tenant_id=tenant.id, process_instance_id=instance.id, user_id=user.id)

    db_session.expire_all()
    assert db_session.get(ExternalFormRequestModel, row.id).status == "cancelled"


_DATA_OBJECT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" targetNamespace="http://x">
  <bpmn:process id="data_object_flow" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:userTask id="fill" />
    <bpmn:scriptTask id="prepare">
      <bpmn:dataOutputAssociation id="out"><bpmn:targetRef>ref_request</bpmn:targetRef></bpmn:dataOutputAssociation>
      <bpmn:script>obj_request = {"title": title}</bpmn:script>
    </bpmn:scriptTask>
    <bpmn:userTask id="after" />
    <bpmn:endEvent id="end" />
    <bpmn:dataObject id="obj_request" />
    <bpmn:dataObjectReference id="ref_request" dataObjectRef="obj_request" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="fill" />
    <bpmn:sequenceFlow id="f2" sourceRef="fill" targetRef="prepare" />
    <bpmn:sequenceFlow id="f3" sourceRef="prepare" targetRef="after" />
    <bpmn:sequenceFlow id="f4" sourceRef="after" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def _start_first_task(db_session, tmp_path, monkeypatch, xml):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(db_session, path="p/m8f680", xml=xml, tenant_id=tenant.id, user_id=user.id)
    instance = workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="p/m8f680")
    (task,) = workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id)
    return tenant, user, instance, task


def test_task_form_values_do_not_expose_the_engine_data_object_store(db_session, tmp_path, monkeypatch):
    """M8F-680: the designer posts every form value back on submit, so engine
    state in the values ends up in the completion payload."""
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import human_task

    tenant, _user, _instance, task = _start_first_task(db_session, tmp_path, monkeypatch, _DATA_OBJECT_BPMN)

    form = human_task.form_schema_for_task(
        db_session, tenant_id=tenant.id, work_item=db_session.get(WorkItemModel, task.id)
    )

    assert "data_objects" not in form["values"]


def test_submitted_data_objects_key_cannot_replace_the_engine_store(db_session, tmp_path, monkeypatch):
    """M8F-680: a posted ``data_objects`` reached core as a string, replaced
    Spiff's data-object store and crashed the next data-output step with
    TypeError -- a generic 500 with nothing saved."""
    from m8flow_core.models.json_data import JsonDataModel
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.process_instance_metadata import ProcessInstanceMetadataModel

    tenant, user, instance, task = _start_first_task(db_session, tmp_path, monkeypatch, _DATA_OBJECT_BPMN)
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)

    workflow.complete(
        db_session,
        tenant_id=tenant.id,
        work_item_id=task.id,
        user_id=user.id,
        task_payload={"title": "sample", "data_objects": {"obj_request": None}},
    )

    pending = workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id)
    assert [t.task_name for t in pending] == ["after"]
    db_session.expire_all()
    stored = db_session.get(ProcessInstanceModel, instance.id)
    workflow_data = JsonDataModel.get_for_tenant(db_session, tenant.id, stored.bpmn_process.json_data_hash).data
    assert workflow_data["data_objects"] == {"obj_request": {"title": "sample"}}
    keys = {
        row.key
        for row in db_session.query(ProcessInstanceMetadataModel).filter_by(process_instance_id=instance.id)
    }
    assert "data_objects" not in keys


_NESTED_VALUE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" targetNamespace="http://x">
  <bpmn:process id="nested_value" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:userTask id="step1" />
    <bpmn:scriptTask id="read_nested"><bpmn:script>approved = review["ok"]</bpmn:script></bpmn:scriptTask>
    <bpmn:userTask id="step2" />
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="step1" />
    <bpmn:sequenceFlow id="f2" sourceRef="step1" targetRef="read_nested" />
    <bpmn:sequenceFlow id="f3" sourceRef="read_nested" targetRef="step2" />
    <bpmn:sequenceFlow id="f4" sourceRef="step2" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def test_nested_payload_values_reach_the_workflow_as_objects(db_session, tmp_path, monkeypatch):
    """Core decodes stored payload values with ast.literal_eval, so JSON
    true/false/null made a nested value arrive as a string (for example a
    variableName form with a checkbox)."""
    from sqlalchemy import select

    from m8flow_core.models.task import TaskModel
    from m8flow_core.models.task_definition import TaskDefinitionModel

    tenant, user, instance, task = _start_first_task(db_session, tmp_path, monkeypatch, _NESTED_VALUE_BPMN)
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)

    workflow.complete(
        db_session,
        tenant_id=tenant.id,
        work_item_id=task.id,
        user_id=user.id,
        task_payload={"review": {"ok": True, "note": None}},
    )

    guids = dict(
        db_session.execute(
            select(TaskDefinitionModel.bpmn_identifier, TaskModel.guid)
            .join(TaskModel, TaskModel.task_definition_id == TaskDefinitionModel.id)
            .where(TaskModel.process_instance_id == instance.id)
        ).all()
    )
    data = workflow.get_instance_task_for_designer(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id, task_guid=guids["step2"]
    )["data"]
    assert data["review"] == {"ok": True, "note": None}
    assert data["approved"] is True


_FAILING_SCRIPT_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" targetNamespace="http://x">
  <bpmn:process id="failing_script" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:userTask id="fill" />
    <bpmn:scriptTask id="fail" name="Deliberate failure"><bpmn:script>raise Exception("deliberate")</bpmn:script></bpmn:scriptTask>
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="fill" />
    <bpmn:sequenceFlow id="f2" sourceRef="fill" targetRef="fail" />
    <bpmn:sequenceFlow id="f3" sourceRef="fail" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def test_script_failure_after_submit_is_shown_on_the_failed_step(db_session, tmp_path, monkeypatch):
    """M8F-680: a real SpiffWorkflow task id is a UUID, not a str, so the
    script-failure branch never matched and the user got the generic 500 with
    nothing recorded: no Error status, no red step, no Events entry."""
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend.errors import ApiError

    tenant, user, instance, task = _start_first_task(db_session, tmp_path, monkeypatch, _FAILING_SCRIPT_BPMN)
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)

    with pytest.raises(ApiError) as failed:
        workflow.complete(
            db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id, task_payload={"a": "1"}
        )

    assert failed.value.error_code == "automatic_step_failed"
    assert "Deliberate failure" in failed.value.message
    db_session.expire_all()
    assert db_session.get(WorkItemModel, task.id).completed is True
    assert db_session.get(ProcessInstanceModel, instance.id).status == "error"
    detail = workflow.get_instance_detail_for_designer(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id
    )
    assert {t["bpmn_identifier"]: t["state"] for t in detail["tasks"]}["fail"] == "ERROR"
    events = workflow.list_instance_events_for_designer(
        db_session, tenant_id=tenant.id, process_instance_id=instance.id
    )["results"]
    (failed_event,) = [e for e in events if e["event_type"] == "task_failed"]
    assert failed_event["task_identifier"] == "fail"
    assert "deliberate" in failed_event["error_message"]


_MI_REVIEW_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
  id="Defs_mi_review" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_mi_review" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:scriptTask id="prep"><bpmn:script>items = ['a', 'b', 'c']</bpmn:script></bpmn:scriptTask>
    <bpmn:userTask id="review">
      <bpmn:extensionElements>
        <spiffworkflow:instructionsForEndUser>Review {{ it }}</spiffworkflow:instructionsForEndUser>
      </bpmn:extensionElements>
      <bpmn:multiInstanceLoopCharacteristics>
        <bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>
        <bpmn:loopDataOutputRef>out</bpmn:loopDataOutputRef>
        <bpmn:inputDataItem id="it" name="it" />
        <bpmn:outputDataItem id="res" name="res" />
      </bpmn:multiInstanceLoopCharacteristics>
    </bpmn:userTask>
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="prep" />
    <bpmn:sequenceFlow id="f2" sourceRef="prep" targetRef="review" />
    <bpmn:sequenceFlow id="f3" sourceRef="review" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def test_multi_instance_review_forms_show_their_own_item(db_session, tmp_path, monkeypatch):
    """M8F-640: an iteration's input item and counters exist only on its task,
    so its form values and instructions must come from the task's own scope."""
    pytest.importorskip(
        "m8flow_core.services.multi_instance_runtime", reason="needs the m8flow-core release with M8F-640"
    )
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import human_task

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(db_session, path="p/m8f640", xml=_MI_REVIEW_BPMN, tenant_id=tenant.id, user_id=user.id)
    workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="p/m8f640")
    reviews = sorted(
        workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id), key=lambda task: task.id
    )

    def values(task):
        work_item = db_session.get(WorkItemModel, task.id)
        return human_task.form_schema_for_task(db_session, tenant_id=tenant.id, work_item=work_item)["values"]

    assert [(values(task)["it"], values(task)["loopCounter"]) for task in reviews] == [("a", 0), ("b", 1), ("c", 2)]
    second = db_session.get(WorkItemModel, reviews[1].id)
    assert human_task.instructions_for_task(db_session, tenant_id=tenant.id, work_item=second) == "Review b"

    # The designer posts every prefilled value back; that must not leak into
    # the other reviews.
    first = values(reviews[0])
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=reviews[0].id, user_id=user.id)
    workflow.complete(
        db_session,
        tenant_id=tenant.id,
        work_item_id=reviews[0].id,
        user_id=user.id,
        task_payload={**first, "res": "A"},
    )

    assert [values(task)["it"] for task in reviews[1:]] == ["b", "c"]
    assert values(reviews[1])["nrOfCompletedInstances"] == 1


_REWORK_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  id="Defs_rework" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_rework" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:scriptTask id="prep"><bpmn:script>rounds = 0</bpmn:script></bpmn:scriptTask>
    <bpmn:scriptTask id="bump"><bpmn:script>rounds = rounds + 1</bpmn:script></bpmn:scriptTask>
    <bpmn:userTask id="ask" />
    <bpmn:exclusiveGateway id="again" default="f_done" />
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="prep" />
    <bpmn:sequenceFlow id="f2" sourceRef="prep" targetRef="bump" />
    <bpmn:sequenceFlow id="f3" sourceRef="bump" targetRef="ask" />
    <bpmn:sequenceFlow id="f4" sourceRef="ask" targetRef="again" />
    <bpmn:sequenceFlow id="f_redo" sourceRef="again" targetRef="bump">
      <bpmn:conditionExpression>outcome == 'redo'</bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="f_done" sourceRef="again" targetRef="end" />
  </bpmn:process>
</bpmn:definitions>"""


def test_form_values_follow_a_script_change_after_an_earlier_submission(db_session, tmp_path, monkeypatch):
    """M8F-640: the first form posts ``rounds`` back as process metadata; when a
    script raises it later, the next form must show the new value."""
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import human_task

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    tenant, user = _seed_actor(db_session)
    catalog.save(db_session, path="p/rework", xml=_REWORK_BPMN, tenant_id=tenant.id, user_id=user.id)
    workflow.start(db_session, tenant_id=tenant.id, user_id=user.id, process_model_identifier="p/rework")

    def ask_values():
        (task,) = workflow.list_pending_tasks(db_session, tenant_id=tenant.id, user_id=user.id)
        work_item = db_session.get(WorkItemModel, task.id)
        return task, human_task.form_schema_for_task(db_session, tenant_id=tenant.id, work_item=work_item)["values"]

    task, values = ask_values()
    assert values["rounds"] == 1
    workflow.claim(db_session, tenant_id=tenant.id, work_item_id=task.id, user_id=user.id)
    workflow.complete(
        db_session,
        tenant_id=tenant.id,
        work_item_id=task.id,
        user_id=user.id,
        task_payload={**values, "outcome": "redo"},
    )

    _task, values = ask_values()
    assert values["rounds"] == 2
