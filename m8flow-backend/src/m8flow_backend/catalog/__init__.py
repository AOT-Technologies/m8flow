from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from typing import Any

from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend import workflow

LOGGER = logging.getLogger(__name__)

UNSUPPORTED_CONSTRUCTS = (
    "callActivity",
    "messageEventDefinition",
    "correlationKey",
    "correlationProperty",
    "compensateEventDefinition",
    "multiInstanceLoopCharacteristics",
)

_GROUP_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# Startable seed diagram for a newly created process model. `{process_id}` is
# replaced with an NCName derived from the model leaf. StartEvent_1 is the
# start the designer can open in the modeler.
_DEFAULT_BPMN_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="{process_id}" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:task id="Activity_1" name="Task">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:task>
    <bpmn:endEvent id="EndEvent_1">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Activity_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Activity_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{process_id}">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="180" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_1_di" bpmnElement="Activity_1">
        <dc:Bounds x="270" y="148" width="150" height="60" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="480" y="160" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint x="216" y="178" />
        <di:waypoint x="270" y="178" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint x="420" y="178" />
        <di:waypoint x="480" y="178" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

# Seed DMN for Add file — not the old public/new_dmn_diagram.dmn. `{decision_id}`
# is replaced the same way as the BPMN template (not str.format).
_DEFAULT_DMN_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="Definitions_1" name="{decision_id}" namespace="https://m8flow.example/dmn">
  <decision id="{decision_id}" name="{decision_id}">
    <decisionTable id="DecisionTable_1">
      <input id="Input_1">
        <inputExpression id="InputExpression_1" typeRef="string">
          <text></text>
        </inputExpression>
      </input>
      <output id="Output_1" typeRef="string" />
    </decisionTable>
  </decision>
</definitions>
"""

_RESERVED_MODEL_FILE_NAMES = frozenset({"process_model.json", "process_group.json"})
_DEFAULT_CREATE_SUFFIXES = frozenset({".bpmn", ".dmn", ".json", ".md"})
_UPLOAD_SUFFIXES = _DEFAULT_CREATE_SUFFIXES | {".txt", ".xml", ".svg", ".html", ".css"}


def save(
    session: Session, *, path: str, xml: str, tenant_id: str, user_id: int, file_name: str | None = None
) -> None:
    """Import the BPMN definition and write it to disk. When the caller knows
    the real on-disk filename (e.g. update_file(), where a template-created
    model kept its template's original filename), pass it as `file_name` --
    otherwise the write falls back to process_model.json's primary_file_name,
    then to {leaf-of-path}.bpmn for a genuinely new model with no metadata
    yet. Guessing the leaf name unconditionally (the old behavior) wrote a
    phantom {leaf}.bpmn alongside the real file for every non-default-named
    model."""
    _reject_unsupported_constructs(xml)
    workflow.import_definition(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        bpmn_identifier=path,
        source_bpmn_xml=xml,
        bpmn_name=Path(path).name,
    )
    disk_path = (
        _tenant_models_root(tenant_id) / path / file_name if file_name else _model_file_path(tenant_id, path)
    )
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    # Use binary I/O so Windows does not translate LF to CRLF. Uploaded file
    # bytes must remain byte-for-byte identical after the BPMN re-import.
    disk_path.write_bytes(xml.encode("utf-8"))


def is_process_model_identifier(path: str, tenant_id: str | None = None) -> bool:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    model_dir = _tenant_models_root(tenant) / path
    if not model_dir.is_dir():
        return False
    # list_models keys off any *.bpmn in the directory. Template-created models
    # keep the template BPMN filename (e.g. wfh-approval.bpmn), not {leaf}.bpmn.
    return any(model_dir.glob("*.bpmn"))


def is_process_group_identifier(group: str, tenant_id: str | None = None) -> bool:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    return (_tenant_models_root(tenant) / group).is_dir()


def delete_process_model(*, tenant_id: str, process_model_identifier: str) -> None:
    """Remove a process model's directory from the tenant's spec dir.
    Destructive and non-reversible from the API. Callers must have already
    checked permissions and that no process instances reference the model —
    this only touches the on-disk BPMN spec, not the DB.

    Path-traversal guarded: the resolved target must stay inside the tenant's
    own models root, mirroring validate_leaf_file_name's concern for the
    file-level routes.
    """
    root = _tenant_models_root(tenant_id).resolve()
    target = (root / process_model_identifier).resolve()
    if target == root or root not in target.parents:
        raise ApiError("invalid_process_model", "Invalid process model identifier", 400)
    if not target.is_dir():
        raise ApiError("not_found", "Process model not found", 404)

    shutil.rmtree(target)


def add_process_model(process_model_info: Any, *, tenant_id: str | None = None) -> None:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    model_id = process_model_info["id"] if isinstance(process_model_info, dict) else getattr(process_model_info, "id")
    (_tenant_models_root(tenant) / model_id).mkdir(parents=True, exist_ok=True)
    if isinstance(process_model_info, dict):
        _write_process_model_json(tenant, model_id, process_model_info)


def save_process_model(process_model_info: Any, *, tenant_id: str | None = None) -> None:
    add_process_model(process_model_info, tenant_id=tenant_id)


def update_file(process_model_info: Any, file_name: str, content: bytes, *, tenant_id: str | None = None) -> Path:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    model_id = process_model_info["id"] if isinstance(process_model_info, dict) else getattr(process_model_info, "id")
    path = write_spec_file(tenant_id=tenant, path=model_id, file_name=file_name, content=content)
    if file_name.endswith(".bpmn"):
        from m8flow_backend.db import current_session
        from m8flow_backend.auth import require_current_user

        xml = content.decode("utf-8") if isinstance(content, bytes) else content
        user = require_current_user()
        save(current_session(), path=model_id, xml=xml, tenant_id=tenant, user_id=user.id, file_name=file_name)
    return path


def validate_leaf_file_name(file_name: str) -> str:
    """A model file name must be a single path segment inside its own model
    directory — reject path traversal / absolute paths / empty names.

    pathlib silently discards the left operand of `/` when the right side is
    absolute (`Path("/a/b") / "/etc/passwd" == Path("/etc/passwd")`), so an
    unvalidated file_name could otherwise escape the tenant's model root.
    Public (not `_`-prefixed): also called from the file-content routes in
    processes_controller.py before either reading or writing.
    """
    if not file_name or file_name in {".", ".."} or "/" in file_name or "\\" in file_name:
        raise ApiError("invalid_file_name", "Invalid file name", 400)
    return file_name


def read_model_file(*, tenant_id: str, process_model_identifier: str, file_name: str) -> bytes | None:
    """Raw bytes of one named file inside an existing process model directory.

    Returns None (not an error) when the file doesn't exist — callers decide
    the 404. Does not check model_exists(); callers that need a distinct
    "model not found" vs "file not found" response should check that first.
    """
    validate_leaf_file_name(file_name)
    path = _tenant_models_root(tenant_id) / process_model_identifier / file_name
    if not path.is_file():
        return None
    return path.read_bytes()


def write_spec_file(*, tenant_id: str, path: str, file_name: str, content: bytes) -> Path:
    target = _tenant_models_root(tenant_id) / path / file_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def list_models(group: str | None = None, *, tenant_id: str) -> list[str]:
    root = _tenant_models_root(tenant_id)
    if not root.exists():
        return []
    search_root = root / group if group else root
    if not search_root.exists():
        return []
    models: list[str] = []
    for bpmn_file in search_root.rglob("*.bpmn"):
        relative = bpmn_file.parent.relative_to(root).as_posix()
        models.append(relative)
    return sorted(set(models))


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def process_model_display_name(*, tenant_id: str, process_model_identifier: str) -> str:
    """Prefer process_model.json display_name; fall back to the leaf path segment."""
    meta = read_json_file(_tenant_models_root(tenant_id) / process_model_identifier / "process_model.json")
    display = meta.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.strip()
    return process_model_identifier.rstrip("/").split("/")[-1]


def process_group_id_for_model(process_model_identifier: str) -> str:
    """Parent path of a model id; empty string when the model sits at the tenant root."""
    if "/" not in process_model_identifier:
        return ""
    return process_model_identifier.rsplit("/", 1)[0]


def process_group_display_name(*, tenant_id: str, group_id: str) -> str:
    if not group_id:
        return ""
    meta = read_json_file(_tenant_models_root(tenant_id) / group_id / "process_group.json")
    display = meta.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.strip()
    return group_id.rstrip("/").split("/")[-1]


def _tenant_ids_for_fanout(tenant_id: str | None) -> list[str]:
    """``[tenant_id]`` normally; every registered tenant when it is None.

    None means "all tenants" and is only ever produced by
    ``auth.resolve_read_tenant_id`` for a verified super-admin.

    Registry-driven rather than a scan of the spec root on purpose: a stray
    directory there (a backup, a partial sync, a deleted tenant's leftovers)
    is not a tenant, and listing one would invent a browsable scope with no
    name and no authorization story. A registered tenant with no directory
    just yields no rows.
    """
    if tenant_id is not None:
        return [tenant_id]
    from m8flow_backend.services.tenant_service import TenantService

    # ponytail: one get_all_tenants() per all-tenants catalog request; cache
    # per-request on g if the tenant count ever makes this measurable.
    return [tenant.id for tenant in TenantService.get_all_tenants()]


def list_model_rows(*, tenant_id: str | None, group: str | None = None) -> list[dict[str, Any]]:
    """Disk-backed model rows for the designer Processes list (no instance stats).

    ``tenant_id`` None fans out over every tenant; each row carries its own
    ``tenant_id`` so identical model identifiers in different tenants stay
    distinguishable (they collide by design -- the identifier is a path).
    """
    rows: list[dict[str, Any]] = []
    for tenant in _tenant_ids_for_fanout(tenant_id):
        for model_id in list_models(group, tenant_id=tenant):
            group_id = process_group_id_for_model(model_id)
            rows.append(
                {
                    "id": model_id,
                    "tenant_id": tenant,
                    "display_name": process_model_display_name(
                        tenant_id=tenant, process_model_identifier=model_id
                    ),
                    "group_id": group_id,
                    "group_display_name": process_group_display_name(
                        tenant_id=tenant, group_id=group_id
                    ),
                }
            )
    return rows


def list_group_ids(*, tenant_id: str) -> list[str]:
    """Unique process-group paths: model parents ∪ dirs with process_group.json.

    Skips the empty (tenant-root) group id — root-level models still appear
    under All groups on the models list.
    """
    root = _tenant_models_root(tenant_id)
    ids: set[str] = set()
    for model_id in list_models(tenant_id=tenant_id):
        group_id = process_group_id_for_model(model_id)
        if group_id:
            ids.add(group_id)
    if root.exists():
        for meta_path in root.rglob("process_group.json"):
            rel = meta_path.parent.relative_to(root).as_posix()
            if rel and rel != ".":
                ids.add(rel)
    return sorted(ids)


def list_group_rows(*, tenant_id: str | None) -> list[dict[str, Any]]:
    """Disk-backed group rows for the designer groups picker (no instance stats).

    ``tenant_id`` None fans out over every tenant -- see ``list_model_rows``.
    """
    rows: list[dict[str, Any]] = []
    for tenant in _tenant_ids_for_fanout(tenant_id):
        for group_id in list_group_ids(tenant_id=tenant):
            meta = read_json_file(_tenant_models_root(tenant) / group_id / "process_group.json")
            description = meta.get("description")
            if not isinstance(description, str):
                description = ""
            else:
                description = description.strip()
            rows.append(
                {
                    "id": group_id,
                    "tenant_id": tenant,
                    "display_name": process_group_display_name(tenant_id=tenant, group_id=group_id),
                    "description": description,
                    "model_count": len(list_models(group_id, tenant_id=tenant)),
                }
            )
    return rows


def validate_process_group_id(group_id: str) -> str:
    """A process-group id is a `/`-separated path of identifier segments.

    Path traversal, empty segments, and colon (the API's slash stand-in) are
    rejected so the resolved directory cannot leave the tenant spec dir.
    """
    if not isinstance(group_id, str) or not group_id.strip():
        raise ApiError("invalid_process_group", "Process group id is required", 400)
    cleaned = group_id.strip().strip("/")
    if not cleaned or "\\" in cleaned or ":" in cleaned:
        raise ApiError("invalid_process_group", "Invalid process group identifier", 400)
    segments = cleaned.split("/")
    if any(not _GROUP_SEGMENT_RE.match(segment) for segment in segments):
        raise ApiError("invalid_process_group", "Invalid process group identifier", 400)
    return cleaned


def process_group_exists(*, tenant_id: str, group_id: str) -> bool:
    """True when `group_id` is a directory in the tenant catalog that is not a process model."""
    try:
        cleaned = validate_process_group_id(group_id)
        target = _resolved_inside_tenant(tenant_id, cleaned)
    except ApiError:
        return False
    if not target.is_dir():
        return False
    return not is_process_model_identifier(cleaned, tenant_id=tenant_id)


def create_process_group(
    *,
    tenant_id: str,
    group_id: str,
    display_name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a process group directory and write process_group.json. No git."""
    cleaned = validate_process_group_id(group_id)
    target = _resolved_inside_tenant(tenant_id, cleaned)
    if is_process_model_identifier(cleaned, tenant_id=tenant_id):
        raise ApiError("process_model_exists", "A process model already uses this id", 409)
    if target.exists():
        raise ApiError("process_group_exists", "Process group already exists", 409)
    target.mkdir(parents=True, exist_ok=True)
    leaf = cleaned.rsplit("/", 1)[-1]
    name = display_name.strip() if isinstance(display_name, str) and display_name.strip() else leaf
    desc = description.strip() if isinstance(description, str) else ""
    _write_process_group_json(tenant_id, cleaned, {"display_name": name, "description": desc})
    return {
        "id": cleaned,
        "display_name": name,
        "description": desc,
        "model_count": 0,
    }


def update_process_group(
    *,
    tenant_id: str,
    group_id: str,
    display_name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update process_group.json metadata. Id / path does not change."""
    cleaned = validate_process_group_id(group_id)
    if not process_group_exists(tenant_id=tenant_id, group_id=cleaned):
        raise ApiError("not_found", "Process group not found", 404)
    meta = read_json_file(_tenant_models_root(tenant_id) / cleaned / "process_group.json")
    leaf = cleaned.rsplit("/", 1)[-1]
    if isinstance(display_name, str):
        name = display_name.strip() or leaf
    else:
        existing = meta.get("display_name")
        name = existing.strip() if isinstance(existing, str) and existing.strip() else leaf
    if isinstance(description, str):
        desc = description.strip()
    else:
        existing_desc = meta.get("description")
        desc = existing_desc.strip() if isinstance(existing_desc, str) else ""
    _write_process_group_json(tenant_id, cleaned, {"display_name": name, "description": desc})
    return {
        "id": cleaned,
        "display_name": name,
        "description": desc,
        "model_count": len(list_models(cleaned, tenant_id=tenant_id)),
    }


def delete_process_group(*, tenant_id: str, group_id: str) -> None:
    """Remove a process group directory (and nested models) from the tenant spec dir.

    Callers must have already checked permissions and that no process
    instances reference models under this group. No git commit.
    """
    cleaned = validate_process_group_id(group_id)
    target = _resolved_inside_tenant(tenant_id, cleaned)
    if not process_group_exists(tenant_id=tenant_id, group_id=cleaned):
        raise ApiError("not_found", "Process group not found", 404)
    shutil.rmtree(target)


def validate_process_model_leaf(leaf_id: str) -> str:
    """A process-model id is a single path segment (the leaf under its group)."""
    cleaned = validate_process_group_id(leaf_id) if isinstance(leaf_id, str) else ""
    if not cleaned or "/" in cleaned:
        raise ApiError("invalid_process_model", "Process model id must be a single path segment", 400)
    return cleaned


def slugify_process_model_leaf(display_name: str) -> str:
    """URL-friendly leaf id from a display name. Empty if nothing usable remains.

    Matches the previous product: lowercase, whitespace to hyphens, keep
    ``[a-z0-9_-]``, collapse repeated hyphens. The result is a valid
    ``_GROUP_SEGMENT_RE`` segment when non-empty.
    """
    if not isinstance(display_name, str):
        return ""
    slug = display_name.strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-_")


def resolve_process_model_leaf(*, leaf_id: str, display_name: str | None) -> str:
    """Use an explicit leaf id, or slugify one from the display name."""
    raw = leaf_id.strip() if isinstance(leaf_id, str) else ""
    if raw:
        return validate_process_model_leaf(raw)
    slug = slugify_process_model_leaf(display_name or "")
    if not slug:
        raise ApiError(
            "invalid_process_model",
            "Process model id is required, or provide a display name to generate one",
            400,
        )
    return validate_process_model_leaf(slug)


def default_bpmn_xml(*, process_id: str) -> str:
    return _DEFAULT_BPMN_TEMPLATE.replace("{process_id}", process_id)


def _bpmn_process_id(leaf: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", leaf)
    if not cleaned or not re.match(r"^[A-Za-z_]", cleaned):
        return f"Process_{cleaned or 'model'}"
    return cleaned


def create_process_model(
    session: Session,
    *,
    tenant_id: str,
    group_id: str,
    leaf_id: str,
    display_name: str | None = None,
    description: str | None = None,
    user_id: int,
) -> dict[str, Any]:
    """Create a process model under an existing group, with a default BPMN. No git.

    ``leaf_id`` may be empty: the leaf is then slugified from ``display_name``.
    """
    group = validate_process_group_id(group_id)
    leaf = resolve_process_model_leaf(leaf_id=leaf_id, display_name=display_name)
    if not process_group_exists(tenant_id=tenant_id, group_id=group):
        raise ApiError("not_found", "Process group not found", 404)
    model_id = f"{group}/{leaf}"
    target = _resolved_inside_tenant(tenant_id, model_id)
    if model_exists(tenant_id=tenant_id, process_model_identifier=model_id) or target.exists():
        raise ApiError("process_model_exists", "Process model already exists", 409)
    name = display_name.strip() if isinstance(display_name, str) and display_name.strip() else leaf
    desc = description.strip() if isinstance(description, str) else ""
    process_id = _bpmn_process_id(leaf)
    file_name = f"{leaf}.bpmn"
    xml = default_bpmn_xml(process_id=process_id)
    _reject_unsupported_constructs(xml)
    # Create FS metadata + BPMN after DB import. If anything fails mid-way, remove the
    # new model directory so a later create is not blocked by a ghost target.exists().
    try:
        workflow.import_definition(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            bpmn_identifier=model_id,
            source_bpmn_xml=xml,
            bpmn_name=file_name,
        )
        add_process_model(
            {
                "id": model_id,
                "display_name": name,
                "description": desc,
                "primary_file_name": file_name,
                "primary_process_id": process_id,
            },
            tenant_id=tenant_id,
        )
        write_spec_file(
            tenant_id=tenant_id, path=model_id, file_name=file_name, content=xml.encode("utf-8")
        )
    except Exception:
        if target.exists():
            shutil.rmtree(target)
        raise
    identity = get_model_identity(tenant_id=tenant_id, process_model_identifier=model_id)
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    return identity


def update_process_model_metadata(
    *,
    tenant_id: str,
    process_model_identifier: str,
    display_name: str | None = None,
    description: str | None = None,
    primary_file_name: str | None = None,
) -> dict[str, Any]:
    """Update process_model.json metadata. Id / group / files do not change."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    meta = read_json_file(_tenant_models_root(tenant_id) / process_model_identifier / "process_model.json")
    leaf = process_model_identifier.rsplit("/", 1)[-1]
    if isinstance(display_name, str):
        name = display_name.strip() or leaf
    else:
        existing = meta.get("display_name")
        name = existing.strip() if isinstance(existing, str) and existing.strip() else leaf
    if isinstance(description, str):
        desc = description.strip()
    else:
        existing_desc = meta.get("description")
        desc = existing_desc.strip() if isinstance(existing_desc, str) else ""
    primary = meta.get("primary_file_name")
    primary_name = primary.strip() if isinstance(primary, str) else ""
    if isinstance(primary_file_name, str):
        candidate = validate_leaf_file_name(primary_file_name.strip())
        file_path = _tenant_models_root(tenant_id) / process_model_identifier / candidate
        if not file_path.is_file():
            raise ApiError("invalid_primary_file", "Primary file not found in this process model", 400)
        primary_name = candidate
    payload: dict[str, Any] = {"display_name": name, "description": desc}
    if primary_name:
        payload["primary_file_name"] = primary_name
    if isinstance(meta.get("primary_process_id"), str) and meta["primary_process_id"].strip():
        payload["primary_process_id"] = meta["primary_process_id"].strip()
    _write_process_model_json(tenant_id, process_model_identifier, payload)
    identity = get_model_identity(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    return identity


def _first_bpmn_name(model_dir: Path) -> str:
    names = sorted(
        path.name
        for path in model_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".bpmn"
    )
    return names[0] if names else ""


def copy_process_model(
    session: Session,
    *,
    tenant_id: str,
    source_identifier: str,
    leaf_id: str,
    display_name: str | None,
    user_id: int,
) -> dict[str, Any]:
    """Duplicate a process model under the same group. Copies files; not instances. No git."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=source_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    group = process_group_id_for_model(source_identifier)
    leaf = validate_process_model_leaf(leaf_id)
    dest_id = f"{group}/{leaf}" if group else leaf
    dest = _resolved_inside_tenant(tenant_id, dest_id)
    if model_exists(tenant_id=tenant_id, process_model_identifier=dest_id) or dest.exists():
        raise ApiError("process_model_exists", "Process model already exists", 409)
    source_dir = _tenant_models_root(tenant_id) / source_identifier
    dest.mkdir(parents=True)
    try:
        for path in source_dir.iterdir():
            if path.is_file() and path.name != "process_model.json":
                shutil.copy2(path, dest / path.name)
        source_meta = read_json_file(source_dir / "process_model.json")
        name = display_name.strip() if isinstance(display_name, str) and display_name.strip() else leaf
        existing_desc = source_meta.get("description")
        desc = existing_desc.strip() if isinstance(existing_desc, str) else ""
        primary = source_meta.get("primary_file_name")
        primary_name = primary.strip() if isinstance(primary, str) else ""
        if primary_name and not (dest / primary_name).is_file():
            primary_name = ""
        if not primary_name:
            primary_name = _first_bpmn_name(dest)
        payload: dict[str, Any] = {"display_name": name, "description": desc}
        if primary_name:
            payload["primary_file_name"] = primary_name
        process_id = source_meta.get("primary_process_id")
        if isinstance(process_id, str) and process_id.strip():
            payload["primary_process_id"] = process_id.strip()
        _write_process_model_json(tenant_id, dest_id, payload)
        bpmn_name = primary_name if primary_name.lower().endswith(".bpmn") else _first_bpmn_name(dest)
        if bpmn_name:
            try:
                xml = (dest / bpmn_name).read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ApiError("invalid_file_content", "File is not valid UTF-8", 400) from exc
            _reject_unsupported_constructs(xml)
            workflow.import_definition(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                bpmn_identifier=dest_id,
                source_bpmn_xml=xml,
                bpmn_name=bpmn_name,
            )
    except Exception:
        if dest.exists():
            shutil.rmtree(dest)
        raise
    identity = get_model_identity(tenant_id=tenant_id, process_model_identifier=dest_id)
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    return identity


def default_dmn_xml(*, decision_id: str) -> str:
    return _DEFAULT_DMN_TEMPLATE.replace("{decision_id}", decision_id)


def _file_suffix(file_name: str) -> str:
    lower = file_name.lower()
    dot = lower.rfind(".")
    return lower[dot:] if dot >= 0 else ""


def _default_file_bytes(file_name: str) -> bytes:
    suffix = _file_suffix(file_name)
    stem = file_name[: -len(suffix)] if suffix else file_name
    if suffix == ".bpmn":
        return default_bpmn_xml(process_id=_bpmn_process_id(stem)).encode("utf-8")
    if suffix == ".dmn":
        return default_dmn_xml(decision_id=_bpmn_process_id(stem)).encode("utf-8")
    if suffix == ".json":
        return b"{}\n"
    if suffix == ".md":
        return b""
    return b""


def _file_payload(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": int(stat.st_size),
        "updated_at_in_seconds": int(stat.st_mtime),
    }


def create_model_file(
    session: Session,
    *,
    tenant_id: str,
    process_model_identifier: str,
    file_name: str,
    content: bytes | None,
    user_id: int,
) -> dict[str, Any]:
    """Create one file in an existing process model. No git. .bpmn is imported."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    name = validate_leaf_file_name(file_name.strip() if isinstance(file_name, str) else "")
    if name.lower() in _RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    suffix = _file_suffix(name)
    if content is None:
        if suffix not in _DEFAULT_CREATE_SUFFIXES:
            raise ApiError(
                "unsupported_file_type",
                "Add file without content must be .bpmn, .dmn, .json, or .md",
                400,
            )
        body = _default_file_bytes(name)
    else:
        if suffix not in _UPLOAD_SUFFIXES:
            raise ApiError("unsupported_file_type", "That file type is not allowed", 400)
        if not content:
            raise ApiError("missing_content", "Request body is required", 400)
        body = content
    target = _tenant_models_root(tenant_id) / process_model_identifier / name
    if target.exists():
        raise ApiError("file_exists", "A file with this name already exists", 409)
    if suffix == ".bpmn":
        try:
            xml = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApiError("invalid_file_content", "File is not valid UTF-8", 400) from exc
        _reject_unsupported_constructs(xml)
        workflow.import_definition(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            bpmn_identifier=process_model_identifier,
            source_bpmn_xml=xml,
            bpmn_name=name,
        )
    write_spec_file(
        tenant_id=tenant_id, path=process_model_identifier, file_name=name, content=body
    )
    return _file_payload(target)


def delete_model_file(*, tenant_id: str, process_model_identifier: str, file_name: str) -> None:
    """Remove one file from a process model. Primary file is 409. No git."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    name = validate_leaf_file_name(file_name)
    if name.lower() in _RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    path = _tenant_models_root(tenant_id) / process_model_identifier / name
    if not path.is_file():
        raise ApiError("not_found", f"File not found: {name}", 404)
    meta = read_json_file(_tenant_models_root(tenant_id) / process_model_identifier / "process_model.json")
    primary = meta.get("primary_file_name")
    primary_name = primary.strip() if isinstance(primary, str) else ""
    if primary_name and path.name == primary_name:
        raise ApiError(
            "cannot_delete_primary",
            "Set another file as primary before deleting this one.",
            409,
        )
    path.unlink()


def model_exists(*, tenant_id: str, process_model_identifier: str) -> bool:
    return is_process_model_identifier(process_model_identifier, tenant_id=tenant_id)


def process_model_description(*, tenant_id: str, process_model_identifier: str) -> str:
    meta = read_json_file(_tenant_models_root(tenant_id) / process_model_identifier / "process_model.json")
    description = meta.get("description")
    if isinstance(description, str):
        return description.strip()
    return ""


def list_model_files(*, tenant_id: str, process_model_identifier: str) -> list[dict[str, Any]]:
    """Files in the model directory (not recursive). Marks primary via process_model.json."""
    model_dir = _tenant_models_root(tenant_id) / process_model_identifier
    if not model_dir.is_dir():
        return []
    meta = read_json_file(model_dir / "process_model.json")
    primary = meta.get("primary_file_name")
    primary_name = primary.strip() if isinstance(primary, str) else ""
    files: list[dict[str, Any]] = []
    for path in sorted(model_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        if path.name in {"process_model.json"}:
            continue
        try:
            stat = path.stat()
        except OSError:
            # File removed/renamed between iterdir() and stat(); skip it
            # rather than fail the whole listing for a benign race.
            LOGGER.debug("Skipping unstat-able file %s while listing process model files", path, exc_info=True)
            continue
        files.append(
            {
                "name": path.name,
                "size_bytes": int(stat.st_size),
                "updated_at_in_seconds": int(stat.st_mtime),
                "primary": bool(primary_name) and path.name == primary_name,
            }
        )
    return files


def get_model_identity(
    *, tenant_id: str | None, process_model_identifier: str
) -> dict[str, Any] | None:
    """Identity + group + description for one model, or None if missing.

    ``tenant_id`` None resolves the owning tenant by looking through every
    registered tenant, and the returned ``tenant_id`` is what callers must use
    for their follow-up reads -- so an all-tenants lookup still reads exactly
    one tenant's files.
    """
    resolved: str | None = None
    for tenant in _tenant_ids_for_fanout(tenant_id):
        if model_exists(tenant_id=tenant, process_model_identifier=process_model_identifier):
            resolved = tenant
            break
    if resolved is None:
        return None
    group_id = process_group_id_for_model(process_model_identifier)
    return {
        "id": process_model_identifier,
        "tenant_id": resolved,
        "display_name": process_model_display_name(
            tenant_id=resolved, process_model_identifier=process_model_identifier
        ),
        "description": process_model_description(
            tenant_id=resolved, process_model_identifier=process_model_identifier
        ),
        "group_id": group_id,
        "group_display_name": process_group_display_name(tenant_id=resolved, group_id=group_id),
    }


def _reject_unsupported_constructs(xml: str) -> None:
    lowered = xml
    # Regular subProcess elements are allowed; only event subprocesses are
    # unsupported, detected here via triggeredByEvent="true" rather than via
    # UNSUPPORTED_CONSTRUCTS below.
    if "triggeredByEvent=\"true\"" in xml or "triggeredByEvent='true'" in xml:
        raise ApiError("unsupported_bpmn", "Event subprocess is not supported", 400)
    for construct in UNSUPPORTED_CONSTRUCTS:
        if f"<{construct}" in lowered or f":{construct}" in lowered:
            raise ApiError("unsupported_bpmn", f"Unsupported BPMN construct: {construct}", 400)


def _tenant_models_root(tenant_id: str) -> Path:
    base = os.environ.get("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR") or os.environ.get(
        "SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"
    ) or "/tmp/m8flow-process-models"
    return Path(base) / tenant_id


def _resolved_inside_tenant(tenant_id: str, relative: str) -> Path:
    """Resolve `relative` under the tenant spec dir; reject escapes."""
    root = _tenant_models_root(tenant_id).resolve()
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ApiError("invalid_process_group", "Invalid process group identifier", 400)
    return target


def _write_process_group_json(tenant_id: str, group_id: str, info: dict[str, Any]) -> None:
    path = _tenant_models_root(tenant_id) / group_id / "process_group.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")


def _model_file_path(tenant_id: str, path: str) -> Path:
    """Best-effort default disk path for a model's primary .bpmn file when the
    caller didn't pass an explicit file_name. Prefers process_model.json's
    primary_file_name (the real on-disk name for template-created models);
    falls back to {leaf-of-path}.bpmn only when no metadata exists yet, e.g.
    a genuinely new model created via POST /v1.0/process-models."""
    meta = read_json_file(_tenant_models_root(tenant_id) / path / "process_model.json")
    primary = meta.get("primary_file_name")
    if isinstance(primary, str) and primary.strip():
        return _tenant_models_root(tenant_id) / path / primary.strip()
    name = path.rstrip("/").split("/")[-1]
    return _tenant_models_root(tenant_id) / path / f"{name}.bpmn"


def _write_process_model_json(tenant_id: str, model_id: str, info: dict[str, Any]) -> None:
    """Persist the process_model.json fields this module already reads
    (display_name, description, primary_file_name, primary_process_id) --
    without this, callers wrote them onto `process_model_info` dicts that
    were never actually saved to disk, so every read back saw {}."""
    payload = {key: value for key, value in info.items() if key != "id" and value is not None}
    if not payload:
        return
    path = _tenant_models_root(tenant_id) / model_id / "process_model.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _best_effort_git_commit(file_path: Path, *, message: str) -> None:
    repo = file_path.parent
    try:
        subprocess.run(["git", "add", str(file_path)], cwd=repo, check=False, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo,
            check=False,
            capture_output=True,
        )
    except OSError:
        return
