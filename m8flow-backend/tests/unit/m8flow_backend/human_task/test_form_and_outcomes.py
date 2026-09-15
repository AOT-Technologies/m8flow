from __future__ import annotations

import json
import logging

from m8flow_backend import human_task

TENANT = "tenant-a"
MODEL_ID = "finance/approval"
DEF_ID = 501


def _write_model_file(root, *, model_id, file_name, content):
    target = root / TENANT / model_id / file_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _human_task(session, *, extensions=None, task_guid=None, outputs=None, process_instance_id=1):
    from m8flow_bpmn_core.models.human_task import HumanTaskModel

    properties: dict = {}
    if extensions is not None:
        properties["extensions"] = extensions
    if outputs is not None:
        properties["outputs"] = outputs
    ht = HumanTaskModel(
        m8f_tenant_id=TENANT,
        process_instance_id=process_instance_id,
        task_id=task_guid,
        task_guid=task_guid,
        task_name="review_expense_claim",
        task_title="Review Expense Claim",
        task_type="UserTask",
        task_status="READY",
        process_model_display_name="Approval",
        bpmn_process_identifier=MODEL_ID,
        json_metadata={"task_definition_properties": properties},
        completed=False,
        created_at_in_seconds=1000,
        updated_at_in_seconds=1000,
    )
    session.add(ht)
    session.flush()
    return ht


def _seed_task_json_data(session, *, task_guid, data):
    from m8flow_bpmn_core.models.json_data import JsonDataModel
    from m8flow_bpmn_core.models.task import TaskModel

    hash_ = f"hash-{task_guid}"
    session.add(JsonDataModel(hash=hash_, data=data))
    session.add(
        TaskModel(
            guid=task_guid,
            m8f_tenant_id=TENANT,
            bpmn_process_id=1,
            process_instance_id=1,
            task_definition_id=1,
            state="READY",
            properties_json={},
            json_data_hash=hash_,
            python_env_data_hash="pyenv",
        )
    )
    session.flush()


# ---------------------------------------------------------------------------
# Form loader
# ---------------------------------------------------------------------------


def test_form_load_full_schema_ui_and_values(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    schema = {"type": "object", "properties": {"amount": {"type": "string"}}}
    ui = {"amount": {"ui:widget": "text"}}
    _write_model_file(tmp_path, model_id=MODEL_ID, file_name="invoice-schema.json", content=json.dumps(schema))
    _write_model_file(tmp_path, model_id=MODEL_ID, file_name="invoice-uischema.json", content=json.dumps(ui))

    ht = _human_task(
        db_session,
        extensions={
            "properties": {
                "formJsonSchemaFilename": "invoice-schema.json",
                "formUiSchemaFilename": "invoice-uischema.json",
            }
        },
        task_guid="guid-1",
    )
    _seed_task_json_data(db_session, task_guid="guid-1", data={"amount": "842.50"})

    form = human_task.form_schema_for_task(db_session, tenant_id=TENANT, human_task=ht)
    assert form["schema"] == schema
    assert form["ui_schema"] == ui
    assert form["values"] == {"amount": "842.50"}


def test_form_load_missing_ui_schema_file(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    schema = {"type": "object", "properties": {"note": {"type": "string"}}}
    _write_model_file(tmp_path, model_id=MODEL_ID, file_name="review-schema.json", content=json.dumps(schema))

    # ui filename declared but the file does not exist on disk.
    ht = _human_task(
        db_session,
        extensions={
            "formJsonSchemaFilename": "review-schema.json",
            "formUiSchemaFilename": "review-uischema.json",
        },
        task_guid="guid-2",
    )
    _seed_task_json_data(db_session, task_guid="guid-2", data={"note": "hi"})

    form = human_task.form_schema_for_task(db_session, tenant_id=TENANT, human_task=ht)
    assert form["schema"] == schema
    assert form["ui_schema"] is None
    assert form["values"] == {"note": "hi"}


def test_form_load_missing_json_data_and_extensions(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    # No extensions at all, and no task json_data seeded.
    ht = _human_task(db_session, extensions=None, task_guid="guid-3")

    form = human_task.form_schema_for_task(db_session, tenant_id=TENANT, human_task=ht)
    assert form["schema"] == {"type": "object", "properties": {}}
    assert form["ui_schema"] is None
    assert form["values"] == {}


def test_form_filename_discovered_by_suffix_convention(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    _write_model_file(tmp_path, model_id=MODEL_ID, file_name="thing-schema.json", content=json.dumps(schema))

    # Filename lives under an unexpected extension key; suffix scan finds it.
    ht = _human_task(
        db_session,
        extensions={"someCustomExtension": "thing-schema.json"},
        task_guid="guid-4",
    )
    form = human_task.form_schema_for_task(db_session, tenant_id=TENANT, human_task=ht)
    assert form["schema"] == schema


# ---------------------------------------------------------------------------
# Outcome enumerator
# ---------------------------------------------------------------------------


def _bpmn_xml(flows):
    """flows: list of (id, source, target, name). name=None -> no name attr."""
    flow_xml = []
    for fid, source, target, name in flows:
        name_attr = f' name="{name}"' if name is not None else ""
        flow_xml.append(
            f'<bpmn:sequenceFlow id="{fid}"{name_attr} sourceRef="{source}" targetRef="{target}" />'
        )
    return (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<bpmn:process id="p">' + "".join(flow_xml) + "</bpmn:process></bpmn:definitions>"
    )


def _seed_gateway_scenario(
    session,
    *,
    gateway_props,
    xml,
    target_defs=None,
    gateway_typename="ExclusiveGateway",
    outputs=("Gateway_1",),
):
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    definition = BpmnProcessDefinitionModel(
        id=DEF_ID,
        m8f_tenant_id=TENANT,
        single_process_hash="sph",
        bpmn_identifier="p",
        properties_json={},
    )
    definition.source_bpmn_xml = xml
    session.add(definition)

    session.add(
        ProcessInstanceModel(
            id=1,
            m8f_tenant_id=TENANT,
            process_model_identifier=MODEL_ID,
            process_model_display_name="Approval",
            process_initiator_id=1,
            bpmn_process_definition_id=DEF_ID,
            status="user_input_required",
        )
    )
    session.add(
        TaskDefinitionModel(
            m8f_tenant_id=TENANT,
            bpmn_process_definition_id=DEF_ID,
            bpmn_identifier="Gateway_1",
            typename=gateway_typename,
            properties_json=gateway_props,
        )
    )
    for ident, name in (target_defs or {}).items():
        session.add(
            TaskDefinitionModel(
                m8f_tenant_id=TENANT,
                bpmn_process_definition_id=DEF_ID,
                bpmn_identifier=ident,
                bpmn_name=name,
                typename="UserTask",
                properties_json={},
            )
        )
    ht = _human_task(session, outputs=list(outputs), task_guid="ut-guid")
    session.flush()
    return ht


def test_outcomes_normal_gateway_conditional_and_default(db_session):
    xml = _bpmn_xml(
        [
            ("f1", "Gateway_1", "Task_Approve", "Approve"),
            ("f2", "Gateway_1", "Task_Reject", "Reject"),
            ("f3", "Gateway_1", "Task_Escalate", "Escalate to Finance Director"),
        ]
    )
    gateway_props = {
        "bpmn_id": "Gateway_1",
        "cond_task_specs": [
            {"condition": "outcome == 'approve'", "task_spec": "Task_Approve"},
            {"condition": "outcome == 'reject'", "task_spec": "Task_Reject"},
        ],
        "default_task_spec": "Task_Escalate",
    }
    ht = _seed_gateway_scenario(db_session, gateway_props=gateway_props, xml=xml)
    outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == [
        {"value": "approve", "label": "Approve"},
        {"value": "reject", "label": "Reject"},
        {"value": "Escalate to Finance Director", "label": "Escalate to Finance Director"},
    ]


def test_outcomes_unnamed_flow_falls_back_to_target_task_name(db_session):
    xml = _bpmn_xml(
        [
            ("f1", "Gateway_1", "Task_Approve", "Approve"),
            ("f2", "Gateway_1", "Task_Reject", None),  # unnamed flow
        ]
    )
    gateway_props = {
        "bpmn_id": "Gateway_1",
        "cond_task_specs": [
            {"condition": "outcome == 'approve'", "task_spec": "Task_Approve"},
            {"condition": "outcome == 'reject'", "task_spec": "Task_Reject"},
        ],
        "default_task_spec": None,
    }
    ht = _seed_gateway_scenario(
        db_session,
        gateway_props=gateway_props,
        xml=xml,
        target_defs={"Task_Reject": "Reject Request"},
    )
    outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == [
        {"value": "approve", "label": "Approve"},
        {"value": "reject", "label": "Reject Request"},
    ]


def test_outcomes_convention_violating_condition_warns_and_skips(db_session, caplog):
    xml = _bpmn_xml(
        [
            ("f1", "Gateway_1", "Task_Approve", "Approve"),
            ("f2", "Gateway_1", "Task_Big", "Big Amount"),
        ]
    )
    gateway_props = {
        "bpmn_id": "Gateway_1",
        "cond_task_specs": [
            {"condition": "outcome == 'approve'", "task_spec": "Task_Approve"},
            {"condition": "amount > 500", "task_spec": "Task_Big"},
        ],
        "default_task_spec": None,
    }
    ht = _seed_gateway_scenario(db_session, gateway_props=gateway_props, xml=xml)
    with caplog.at_level(logging.WARNING):
        outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == [{"value": "approve", "label": "Approve"}]
    assert any("not a simple" in rec.message for rec in caplog.records)


def test_outcomes_linear_no_gateway_returns_empty(db_session):
    # outputs point at a plain user task, not a gateway.
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel
    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    definition = BpmnProcessDefinitionModel(
        id=DEF_ID,
        m8f_tenant_id=TENANT,
        single_process_hash="sph",
        bpmn_identifier="p",
        properties_json={},
    )
    definition.source_bpmn_xml = _bpmn_xml([("f1", "UT", "End", "done")])
    db_session.add(definition)
    db_session.add(
        ProcessInstanceModel(
            id=1,
            m8f_tenant_id=TENANT,
            process_model_identifier=MODEL_ID,
            process_model_display_name="Approval",
            process_initiator_id=1,
            bpmn_process_definition_id=DEF_ID,
            status="user_input_required",
        )
    )
    db_session.add(
        TaskDefinitionModel(
            m8f_tenant_id=TENANT,
            bpmn_process_definition_id=DEF_ID,
            bpmn_identifier="End",
            typename="EndEvent",
            properties_json={},
        )
    )
    ht = _human_task(db_session, outputs=["End"], task_guid="ut-guid")
    outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == []


def test_outcomes_single_outgoing_flow_returns_empty(db_session):
    xml = _bpmn_xml([("f1", "Gateway_1", "Task_Approve", "Approve")])
    gateway_props = {
        "bpmn_id": "Gateway_1",
        "cond_task_specs": [
            {"condition": "outcome == 'approve'", "task_spec": "Task_Approve"},
        ],
        "default_task_spec": None,
    }
    ht = _seed_gateway_scenario(db_session, gateway_props=gateway_props, xml=xml)
    outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == []


def test_outcomes_reversed_operand_order(db_session):
    xml = _bpmn_xml(
        [
            ("f1", "Gateway_1", "Task_Approve", "Approve"),
            ("f2", "Gateway_1", "Task_Reject", "Reject"),
        ]
    )
    gateway_props = {
        "bpmn_id": "Gateway_1",
        "cond_task_specs": [
            {"condition": "'approve' == outcome", "task_spec": "Task_Approve"},
            {"condition": "outcome == \"reject\"", "task_spec": "Task_Reject"},
        ],
        "default_task_spec": None,
    }
    ht = _seed_gateway_scenario(db_session, gateway_props=gateway_props, xml=xml)
    outcomes = human_task.outcomes_for_task(db_session, tenant_id=TENANT, human_task_id=ht.id)
    assert outcomes == [
        {"value": "approve", "label": "Approve"},
        {"value": "reject", "label": "Reject"},
    ]
