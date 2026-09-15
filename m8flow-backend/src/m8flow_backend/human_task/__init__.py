from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from jinja2 import Environment, BaseLoader
from sqlalchemy import select
from sqlalchemy.orm import Session

from m8flow_bpmn_core.models.human_task import HumanTaskModel
from m8flow_bpmn_core.models.process_instance_metadata import ProcessInstanceMetadataModel
from m8flow_backend.models.native import (
    TaskDraftDataModel,
    TaskInstructionsForEndUserModel,
    TypeaheadModel,
)
from m8flow_backend import catalog, workflow

LOGGER = logging.getLogger(__name__)

# Serialized-spec extension property keys that carry the form supporting-file
# names (SpiffArena authoring convention). Read from
# HumanTaskModel.json_metadata["task_definition_properties"]["extensions"];
# the value is a bare filename resolved via catalog.read_model_file. As a
# fallback we also scan any extension value ending in the matching suffix.
_SCHEMA_FILENAME_KEYS = ("formJsonSchemaFilename",)
_UI_SCHEMA_FILENAME_KEYS = ("formUiSchemaFilename",)
_SCHEMA_FILENAME_SUFFIX = "-schema.json"
_UI_SCHEMA_FILENAME_SUFFIX = "-uischema.json"

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

# Gateway typenames whose serialized spec carries branching conditions. These
# are SpiffWorkflow class names (typename == cls.__name__) persisted on
# TaskDefinitionModel.typename.
_GATEWAY_TYPENAMES = ("ExclusiveGateway", "InclusiveGateway")

# The single reserved decision variable an approval gateway branches on. A
# gateway condition is expected to be a simple string equality against it, in
# either operand order: `outcome == 'approve'` / `'approve' == outcome`.
_OUTCOME_VARIABLE = "outcome"
_OUTCOME_CONDITION_RE = re.compile(
    r"""^\s*(?:"""
    r"""outcome\s*==\s*(['"])(?P<v1>.*?)\1"""
    r"""|(['"])(?P<v2>.*?)\3\s*==\s*outcome"""
    r""")\s*$"""
)


def render_instructions(template: str, context: dict[str, Any] | None = None) -> str:
    env = Environment(loader=BaseLoader(), autoescape=True)
    return env.from_string(template).render(**(context or {}))


def form_schema_for_task(
    session: Session, *, tenant_id: str, human_task: HumanTaskModel
) -> dict[str, Any]:
    """Load a human task's form (schema + optional ui-schema + prior values).

    - schema / ui-schema filenames come from the serialized spec extensions on
      the human-task row (``form_file_name`` is always None in core, so it is
      never consulted). Content is loaded from the model's supporting files via
      the ``catalog`` module.
    - values are the task's own prior submission
      (``HumanTaskModel.task_guid -> TaskModel.json_data_hash ->
      JsonDataModel.data``), tenant-scoped.

    Tolerant by design: missing extensions/filename -> empty schema; missing
    ui-schema file -> ``ui_schema`` None; missing/None json_data -> ``{}``.
    """
    schema, ui_schema = _load_form_files(tenant_id=tenant_id, human_task=human_task)
    values = _prior_submission_values(session, tenant_id=tenant_id, human_task=human_task)
    return {"schema": schema, "ui_schema": ui_schema, "values": values}


def outcomes_for_task(
    session: Session, *, tenant_id: str, human_task_id: int
) -> list[dict[str, str]]:
    """Derive the outcome buttons ``[{"value", "label"}]`` for a user task.

    Finds the exclusive/inclusive gateway immediately following the task (via
    the serialized spec ``outputs`` -> gateway ``TaskDefinitionModel``), reads
    its ``cond_task_specs`` + ``default_task_spec``, and parses the process's
    ``source_bpmn_xml`` sequence flows for the human-readable button labels
    (flow ``name``). Each conditional flow's value is the string literal from
    an ``outcome == '<value>'`` equality (the reserved decision variable is
    ``outcome``).

    Best-effort, never raises for a modeling problem: no gateway or a single
    outgoing flow (linear task) -> ``[]`` (frontend renders one generic
    Submit); a gateway condition that is not a simple ``outcome == '...'``
    equality is skipped with a logged warning.
    """
    human_task = session.get(HumanTaskModel, human_task_id)
    if human_task is None or human_task.m8f_tenant_id != tenant_id:
        return []

    props = _task_definition_properties(human_task)
    outputs = [str(o) for o in (props.get("outputs") or [])]
    if not outputs:
        return []

    from m8flow_bpmn_core.models.process_instance import ProcessInstanceModel

    instance = session.get(ProcessInstanceModel, human_task.process_instance_id)
    if (
        instance is None
        or instance.m8f_tenant_id != tenant_id
        or instance.bpmn_process_definition_id is None
    ):
        return []
    definition_id = instance.bpmn_process_definition_id

    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    gateway = session.scalars(
        select(TaskDefinitionModel).where(
            TaskDefinitionModel.m8f_tenant_id == tenant_id,
            TaskDefinitionModel.bpmn_process_definition_id == definition_id,
            TaskDefinitionModel.bpmn_identifier.in_(outputs),
            TaskDefinitionModel.typename.in_(_GATEWAY_TYPENAMES),
        )
    ).first()
    if gateway is None:
        return []

    gw_props = gateway.properties_json or {}
    gateway_bpmn_id = gw_props.get("bpmn_id") or gateway.bpmn_identifier

    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    definition = session.get(BpmnProcessDefinitionModel, definition_id)
    source_xml = None
    if definition is not None and definition.m8f_tenant_id == tenant_id:
        source_xml = definition.source_bpmn_xml
    flows = _gateway_sequence_flows(source_xml, gateway_bpmn_id)

    # Linear-ish gateway (0/1 outgoing flow): no real choice to present.
    if len(flows) <= 1:
        return []

    flow_by_target = {flow["target"]: flow for flow in flows if flow.get("target")}
    task_names = _task_name_map(session, tenant_id=tenant_id, definition_id=definition_id)

    outcomes: list[dict[str, str]] = []
    for entry in gw_props.get("cond_task_specs") or []:
        if not isinstance(entry, dict):
            continue
        task_spec = entry.get("task_spec")
        condition = entry.get("condition")
        flow = flow_by_target.get(task_spec)
        if condition is None:
            # A conditional gateway may list its default branch here with a
            # null condition; treat it like the default flow.
            value = _default_flow_value(flow, task_spec)
            label = _flow_label(flow, task_spec, task_names) or value
            outcomes.append({"value": value, "label": label})
            continue
        value = _parse_outcome_literal(condition)
        if value is None:
            LOGGER.warning(
                "Gateway %r condition %r is not a simple `outcome == '...'` equality; "
                "skipping this outcome (button set is best-effort).",
                gateway_bpmn_id,
                condition,
            )
            continue
        label = _flow_label(flow, task_spec, task_names) or value
        outcomes.append({"value": value, "label": label})

    default_task_spec = gw_props.get("default_task_spec")
    if default_task_spec:
        flow = flow_by_target.get(default_task_spec)
        value = _default_flow_value(flow, default_task_spec)
        label = _flow_label(flow, default_task_spec, task_names) or value
        outcomes.append({"value": value, "label": label})

    return outcomes


def display_task(session: Session, *, tenant_id: str, human_task_id: int) -> dict[str, Any]:
    task = session.get(HumanTaskModel, human_task_id)
    if task is None:
        return {}
    metadata = session.scalars(
        select(ProcessInstanceMetadataModel).where(
            ProcessInstanceMetadataModel.process_instance_id == task.process_instance_id,
            ProcessInstanceMetadataModel.m8f_tenant_id == tenant_id,
        )
    ).all()
    form = form_schema_for_task(session, tenant_id=tenant_id, human_task=task)
    return {
        "id": task.id,
        "task_title": task.task_title or task.task_name,
        "task_name": task.task_name,
        "status": task.task_status,
        "form_schema": form["schema"],
        "form": form,
        "metadata": {row.key: row.value for row in metadata},
    }


def save_draft(
    session: Session,
    *,
    tenant_id: str,
    process_instance_id: int,
    task_guid: str,
    saved_form_data: dict[str, Any],
) -> TaskDraftDataModel:
    row = session.scalars(
        select(TaskDraftDataModel).where(
            TaskDraftDataModel.process_instance_id == process_instance_id,
            TaskDraftDataModel.task_guid == task_guid,
            TaskDraftDataModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    payload = json.dumps(saved_form_data)
    if row is None:
        row = TaskDraftDataModel(
            process_instance_id=process_instance_id,
            task_guid=task_guid,
            saved_form_data=payload,
            m8f_tenant_id=tenant_id,
        )
        session.add(row)
    else:
        row.saved_form_data = payload
    return row


def typeahead_lookup(session: Session, *, tenant_id: str, category: str, search_term: str) -> list[str]:
    rows = session.scalars(
        select(TypeaheadModel).where(
            TypeaheadModel.m8f_tenant_id == tenant_id,
            TypeaheadModel.category == category,
            TypeaheadModel.search_term.ilike(f"%{search_term}%"),
        )
    ).all()
    return [row.result for row in rows]


def store_end_user_instructions(
    session: Session, *, tenant_id: str, process_instance_id: int, instruction: str
) -> TaskInstructionsForEndUserModel:
    row = TaskInstructionsForEndUserModel(
        process_instance_id=process_instance_id,
        instruction=instruction,
        m8f_tenant_id=tenant_id,
    )
    session.add(row)
    return row


def submit_external_form(
    session: Session,
    *,
    tenant_id: str,
    human_task_id: int,
    user_id: int,
    task_payload: dict[str, Any] | None,
) -> Any:
    workflow.claim(
        session,
        tenant_id=tenant_id,
        human_task_id=human_task_id,
        user_id=user_id,
    )
    return workflow.complete(
        session,
        tenant_id=tenant_id,
        human_task_id=human_task_id,
        user_id=user_id,
        task_payload=task_payload,
    )


# ---------------------------------------------------------------------------
# Form-loading internals
# ---------------------------------------------------------------------------


def _task_definition_properties(human_task: HumanTaskModel) -> dict[str, Any]:
    metadata = human_task.json_metadata if isinstance(human_task.json_metadata, dict) else {}
    props = metadata.get("task_definition_properties")
    return props if isinstance(props, dict) else {}


def _form_extensions(human_task: HumanTaskModel) -> dict[str, Any]:
    extensions = _task_definition_properties(human_task).get("extensions")
    return extensions if isinstance(extensions, dict) else {}


def _extension_filename(
    extensions: dict[str, Any], keys: tuple[str, ...], suffix: str
) -> str | None:
    """Resolve a supporting-file name from the spec extensions.

    Spiff puts ``spiffworkflow:properties`` under ``extensions["properties"]``
    and other custom extension elements at ``extensions[<localName>]``, so both
    scopes are searched: first the known property keys, then any value ending
    in ``suffix`` as a convention fallback.
    """
    scopes = [extensions]
    props = extensions.get("properties")
    if isinstance(props, dict):
        scopes.append(props)
    for scope in scopes:
        for key in keys:
            value = scope.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for scope in scopes:
        for value in scope.values():
            if isinstance(value, str) and value.endswith(suffix):
                return value
    return None


def _load_json_supporting_file(
    *, tenant_id: str, process_model_identifier: str, file_name: str | None
) -> dict[str, Any] | None:
    if not file_name:
        return None
    raw = catalog.read_model_file(
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        file_name=file_name,
    )
    if raw is None:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    except (ValueError, UnicodeDecodeError):
        LOGGER.warning(
            "Form supporting file %r for model %r is not valid JSON; ignoring.",
            file_name,
            process_model_identifier,
        )
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_form_files(
    *, tenant_id: str, human_task: HumanTaskModel
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    extensions = _form_extensions(human_task)
    model_id = human_task.bpmn_process_identifier
    schema_name = _extension_filename(extensions, _SCHEMA_FILENAME_KEYS, _SCHEMA_FILENAME_SUFFIX)
    ui_name = _extension_filename(extensions, _UI_SCHEMA_FILENAME_KEYS, _UI_SCHEMA_FILENAME_SUFFIX)
    schema = _load_json_supporting_file(
        tenant_id=tenant_id, process_model_identifier=model_id, file_name=schema_name
    )
    ui_schema = _load_json_supporting_file(
        tenant_id=tenant_id, process_model_identifier=model_id, file_name=ui_name
    )
    if schema is None:
        schema = dict(_EMPTY_SCHEMA)
    return schema, ui_schema


def _prior_submission_values(
    session: Session, *, tenant_id: str, human_task: HumanTaskModel
) -> dict[str, Any]:
    if not human_task.task_guid:
        return {}

    from m8flow_bpmn_core.models.json_data import JsonDataModel
    from m8flow_bpmn_core.models.task import TaskModel

    task = session.scalars(
        select(TaskModel).where(
            TaskModel.guid == human_task.task_guid,
            TaskModel.m8f_tenant_id == tenant_id,
        )
    ).first()
    if task is None or not task.json_data_hash:
        return {}
    json_data = session.get(JsonDataModel, task.json_data_hash)
    if json_data is None or not isinstance(json_data.data, dict):
        return {}
    return json_data.data


# ---------------------------------------------------------------------------
# Outcome-derivation internals
# ---------------------------------------------------------------------------


def _task_name_map(
    session: Session, *, tenant_id: str, definition_id: int
) -> dict[str, str]:
    """bpmn_identifier -> bpmn_name for the definition's task specs (label
    fallback when a sequence flow has no authored name)."""
    from m8flow_bpmn_core.models.task_definition import TaskDefinitionModel

    rows = session.execute(
        select(TaskDefinitionModel.bpmn_identifier, TaskDefinitionModel.bpmn_name).where(
            TaskDefinitionModel.m8f_tenant_id == tenant_id,
            TaskDefinitionModel.bpmn_process_definition_id == definition_id,
        )
    ).all()
    return {ident: name for ident, name in rows if name}


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _gateway_sequence_flows(source_xml: str | None, gateway_bpmn_id: str | None) -> list[dict[str, Any]]:
    """Outgoing ``<bpmn:sequenceFlow>`` elements of one gateway, namespace-agnostic.

    Returns ``[{"id", "name", "target"}]``; ``name`` is None when unauthored.
    """
    flows: list[dict[str, Any]] = []
    if not source_xml or not gateway_bpmn_id:
        return flows
    try:
        root = ET.fromstring(source_xml)
    except ET.ParseError:
        LOGGER.warning("Could not parse source_bpmn_xml while deriving outcomes.", exc_info=True)
        return flows
    for element in root.iter():
        if _localname(element.tag) != "sequenceFlow":
            continue
        if element.get("sourceRef") != gateway_bpmn_id:
            continue
        name = (element.get("name") or "").strip()
        flows.append(
            {
                "id": element.get("id"),
                "name": name or None,
                "target": element.get("targetRef"),
            }
        )
    return flows


def _flow_label(
    flow: dict[str, Any] | None, task_spec: Any, task_names: dict[str, str]
) -> str | None:
    """Button label: authored flow name, else target task name, else None
    (caller falls back to the outcome value)."""
    if flow and flow.get("name"):
        return flow["name"]
    if isinstance(task_spec, str):
        target_name = task_names.get(task_spec)
        if target_name:
            return target_name
    return None


def _default_flow_value(flow: dict[str, Any] | None, task_spec: Any) -> str:
    if flow and flow.get("name"):
        return flow["name"]
    if flow and flow.get("id"):
        return flow["id"]
    return str(task_spec)


def _parse_outcome_literal(condition: Any) -> str | None:
    if not isinstance(condition, str):
        return None
    match = _OUTCOME_CONDITION_RE.match(condition)
    if match is None:
        return None
    return match.group("v1") if match.group("v1") is not None else match.group("v2")
