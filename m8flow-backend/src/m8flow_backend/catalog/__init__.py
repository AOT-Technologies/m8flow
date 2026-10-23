from __future__ import annotations

import base64
import ctypes
import errno
import functools
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend import workflow
from m8flow_backend.models.process_model_version import ProcessModelVersionModel

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

PROCESS_MODEL_STATUS_DRAFT = "draft"
PROCESS_MODEL_STATUS_PUBLISHED = "published"
PROCESS_MODEL_STATUS_PAUSED = "paused"
PROCESS_MODEL_STATUSES = frozenset(
    {PROCESS_MODEL_STATUS_DRAFT, PROCESS_MODEL_STATUS_PUBLISHED, PROCESS_MODEL_STATUS_PAUSED}
)
# Only published models start instances; draft and paused both refuse. Paused
# is reversible and keeps its history, draft is "not ready yet" -- the split
# matters to readers of the list, not to the start guard.
PROCESS_MODEL_STARTABLE_STATUSES = frozenset({PROCESS_MODEL_STATUS_PUBLISHED})

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
    _ensure_baseline_version(session, tenant_id=tenant_id, process_model_identifier=path)
    source_dmn_xml = _model_dmn_xml(
        tenant_id=tenant_id,
        process_model_identifier=path,
    )
    workflow.import_definition(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        bpmn_identifier=path,
        source_bpmn_xml=xml,
        source_dmn_xml=source_dmn_xml,
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
    # Bounded: every model_exists() caller then trusts the id, and "../t2/..." would reach another tenant.
    model_dir = _path_inside_tenant(tenant, _tenant_models_root(tenant) / path)
    if model_dir is None or not model_dir.is_dir():
        return False
    # list_models keys off any *.bpmn in the directory. Template-created models
    # keep the template BPMN filename (e.g. wfh-approval.bpmn), not {leaf}.bpmn.
    return any(model_dir.glob("*.bpmn"))


def is_process_group_identifier(group: str, tenant_id: str | None = None) -> bool:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    return (_tenant_models_root(tenant) / group).is_dir()


def delete_process_model(session: Session, *, tenant_id: str, process_model_identifier: str) -> None:
    """Remove a process model's directory and its published versions, and
    commit. Destructive and non-reversible from the API. Callers must have
    already checked permissions and that no process instances reference it.

    Disk and DB change together: the directory is renamed aside (atomic and
    reversible), the version deletes are committed, and only then is the
    renamed copy removed. A failed commit renames it back, so version rows
    never outlive their model.

    Path-traversal guarded: the resolved target must stay inside the tenant's
    own models root, mirroring validate_leaf_file_name's concern for the
    file-level routes.
    """
    target = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier)
    if target is None:
        raise ApiError("invalid_process_model", "Invalid process model identifier", 400)
    if not target.is_dir():
        raise ApiError("not_found", "Process model not found", 404)

    delete_versions(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    session.flush()  # DB errors surface before the disk is touched
    # Outside every tenant root (beside m8flow-templates), so list_models never sees it.
    # Built from the base dir alone so no request value reaches the trash path.
    trash = _models_base_dir() / ".m8flow-trash" / uuid.uuid4().hex
    trash.parent.mkdir(parents=True, exist_ok=True)
    target.rename(trash)
    try:
        session.commit()
    except Exception:
        trash.rename(target)
        raise
    # ponytail: a crash between commit and rmtree leaves a dir in .m8flow-trash; add a sweep if it matters.
    shutil.rmtree(trash, ignore_errors=True)


def add_process_model(process_model_info: Any, *, tenant_id: str | None = None) -> None:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    model_id = process_model_info["id"] if isinstance(process_model_info, dict) else getattr(process_model_info, "id")
    (_tenant_models_root(tenant) / model_id).mkdir(parents=True, exist_ok=True)
    if isinstance(process_model_info, dict):
        _write_process_model_json(tenant, model_id, process_model_info)


def save_process_model(process_model_info: Any, *, tenant_id: str | None = None) -> None:
    add_process_model(process_model_info, tenant_id=tenant_id)


def update_file(
    process_model_info: Any, file_name: str, content: bytes, *, session: Session, tenant_id: str | None = None
) -> Path:
    from flask import g

    tenant = tenant_id or getattr(g, "m8flow_tenant_id", None) or "default"
    model_id = process_model_info["id"] if isinstance(process_model_info, dict) else getattr(process_model_info, "id")
    if not file_name.lower().endswith((".bpmn", ".dmn")):
        return write_spec_file(session, tenant_id=tenant, path=model_id, file_name=file_name, content=content)
    xml = None
    if file_name.lower().endswith(".bpmn"):
        # Refuse what the import would refuse before anything reaches disk.
        try:
            xml = content.decode("utf-8") if isinstance(content, bytes) else content
        except UnicodeDecodeError as exc:
            raise ApiError("invalid_file_content", "File is not valid UTF-8", 400) from exc
        _reject_unsupported_constructs(xml)
    previous = read_model_file(tenant_id=tenant, process_model_identifier=model_id, file_name=file_name)
    path = write_spec_file(session, tenant_id=tenant, path=model_id, file_name=file_name, content=content)
    from m8flow_backend.auth import require_current_user

    try:
        user = require_current_user()
        if xml is not None:
            save(session, path=model_id, xml=xml, tenant_id=tenant, user_id=user.id, file_name=file_name)
        else:
            bpmn_path = _path_inside_tenant(tenant, _model_file_path(tenant, model_id))
            if bpmn_path is not None and bpmn_path.is_file():
                save(
                    session,
                    path=model_id,
                    # Bytes, not read_text: newline translation would change the digest Start matches on.
                    xml=bpmn_path.read_bytes().decode("utf-8"),
                    tenant_id=tenant,
                    user_id=user.id,
                    file_name=bpmn_path.name,
                )
    except Exception as exc:
        # The failed request rolls back the baseline version too; a model left
        # with no versions would then start from this unpublished edit.
        _restore_file(path, previous, exc)
        raise
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
    path = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier / file_name)
    if path is None or not path.is_file():
        return None
    return path.read_bytes()


def read_primary_bpmn(*, tenant_id: str, process_model_identifier: str) -> tuple[str, str] | None:
    """(file name, XML) of a model's primary BPMN on disk; None when it has none.

    Traversal-guarded: the caller imports what this returns, so an id, a
    `primary_file_name`, or a symlink that escapes the tenant's models root must
    not pull in another tenant's file.
    """
    root = _tenant_models_root(tenant_id).resolve()
    model_dir = (root / process_model_identifier).resolve()
    if root not in model_dir.parents:
        LOGGER.warning("Rejected model id outside tenant %s models root: %r", tenant_id, process_model_identifier)
        return None
    if not model_dir.is_dir():
        return None
    path = _model_file_path(tenant_id, process_model_identifier)
    if not path.is_file():
        name = _first_bpmn_name(model_dir)
        if not name:
            return None
        path = model_dir / name
    # Read what was checked: `resolved` holds no symlinks, so re-pointing the
    # file's symlink after this check cannot redirect the read.
    resolved = path.resolve()
    if root not in resolved.parents:
        LOGGER.warning("Rejected BPMN outside tenant %s models root: %s -> %s", tenant_id, path, resolved)
        return None
    try:
        xml = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None  # deleted since the checks above: same 404 as never there
    except UnicodeDecodeError as exc:
        raise ApiError("invalid_file_content", "File is not valid UTF-8", 400) from exc
    _reject_unsupported_constructs(xml)
    return path.name, xml


def write_spec_file(session: Session, *, tenant_id: str, path: str, file_name: str, content: bytes) -> Path:
    target = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / path / file_name)
    if target is None:
        raise ApiError("invalid_file_name", "Invalid file name", 400)
    _ensure_baseline_version(session, tenant_id=tenant_id, process_model_identifier=path)
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


def process_model_status(*, tenant_id: str, process_model_identifier: str) -> str:
    """Lifecycle status from process_model.json; absent/unknown reads as published.

    Published -- not draft -- is the default on purpose. Models that predate
    this field were all startable, so reading them as draft would make every
    existing model in every deployment refuse to start on upgrade. Defaulting
    to published keeps them working with no backfill; models created from here
    on get an explicit `draft` written at creation (see create_process_model),
    so new work still starts in draft as designed.
    """
    meta = read_json_file(_tenant_models_root(tenant_id) / process_model_identifier / "process_model.json")
    status = meta.get("status")
    if isinstance(status, str) and status.strip() in PROCESS_MODEL_STATUSES:
        return status.strip()
    return PROCESS_MODEL_STATUS_PUBLISHED


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
                    "status": process_model_status(
                        tenant_id=tenant, process_model_identifier=model_id
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
                # Explicit so new models start in draft even though an absent
                # status reads as published for pre-existing models.
                "status": PROCESS_MODEL_STATUS_DRAFT,
                "primary_file_name": file_name,
                "primary_process_id": process_id,
            },
            tenant_id=tenant_id,
        )
        write_spec_file(
            session, tenant_id=tenant_id, path=model_id, file_name=file_name, content=xml.encode("utf-8")
        )
    except Exception:
        if target.exists():
            shutil.rmtree(target)
        raise
    identity = get_model_identity(tenant_id=tenant_id, process_model_identifier=model_id)
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    return identity


# draft -> paused is the only pair left out: pausing something that was never
# published has no meaning. Re-requesting the current status is a no-op rather
# than a 400, so a double-clicked Publish doesn't surface an error.
_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    PROCESS_MODEL_STATUS_DRAFT: frozenset({PROCESS_MODEL_STATUS_PUBLISHED}),
    PROCESS_MODEL_STATUS_PUBLISHED: frozenset(
        {PROCESS_MODEL_STATUS_PAUSED, PROCESS_MODEL_STATUS_DRAFT}
    ),
    PROCESS_MODEL_STATUS_PAUSED: frozenset(
        {PROCESS_MODEL_STATUS_PUBLISHED, PROCESS_MODEL_STATUS_DRAFT}
    ),
}


def _validated_status_transition(*, current: str, requested: str) -> str:
    candidate = requested.strip() if isinstance(requested, str) else ""
    if candidate not in PROCESS_MODEL_STATUSES:
        raise ApiError(
            "invalid_status",
            f"Unknown process model status: {requested!r}",
            400,
        )
    if candidate == current:
        return candidate
    if candidate not in _STATUS_TRANSITIONS.get(current, frozenset()):
        raise ApiError(
            "invalid_status_transition",
            f"Cannot change process model status from {current} to {candidate}",
            400,
        )
    return candidate


def update_process_model_metadata(
    session: Session,
    *,
    tenant_id: str,
    process_model_identifier: str,
    display_name: str | None = None,
    description: str | None = None,
    primary_file_name: str | None = None,
    status: str | None = None,
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
        file_path = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier / candidate)
        if file_path is None or not file_path.is_file():  # None: a symlink out of the tenant root
            raise ApiError("invalid_primary_file", "Primary file not found in this process model", 400)
        if candidate != primary_name:
            _ensure_baseline_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
        primary_name = candidate
    # Carried forward explicitly: this payload is rebuilt from scratch, so a
    # status left out here would be wiped by every rename / description edit.
    current_status = process_model_status(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if status is None:
        next_status = current_status
    else:
        next_status = _validated_status_transition(current=current_status, requested=status)
    payload: dict[str, Any] = {
        "display_name": name,
        "description": desc,
        "status": next_status,
    }
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
        # A copy always starts as draft -- duplicating a published model must
        # not silently make the untested duplicate startable too.
        payload: dict[str, Any] = {
            "display_name": name,
            "description": desc,
            "status": PROCESS_MODEL_STATUS_DRAFT,
        }
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
                source_dmn_xml=_model_dmn_xml(
                    tenant_id=tenant_id,
                    process_model_identifier=dest_id,
                ),
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
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
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
            source_dmn_xml=_model_dmn_xml(
                tenant_id=tenant_id,
                process_model_identifier=process_model_identifier,
            ),
            bpmn_name=name,
        )
    elif suffix == ".dmn":
        try:
            dmn_xml = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApiError("invalid_file_content", "DMN file is not valid UTF-8", 400) from exc
        bpmn_path = _model_file_path(tenant_id, process_model_identifier)
        if bpmn_path.is_file():
            workflow.import_definition(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                bpmn_identifier=process_model_identifier,
                source_bpmn_xml=bpmn_path.read_text(encoding="utf-8"),
                source_dmn_xml=dmn_xml,
                bpmn_name=bpmn_path.name,
            )
    write_spec_file(
        session, tenant_id=tenant_id, path=process_model_identifier, file_name=name, content=body
    )
    return _file_payload(target)


def delete_model_file(session: Session, *, tenant_id: str, process_model_identifier: str, file_name: str) -> None:
    """Remove one file from a process model. Primary file is 409. No git."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    name = validate_leaf_file_name(file_name)
    if name.lower() in _RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    path = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier / name)
    if path is None:
        raise ApiError("invalid_file_name", "Invalid file name", 400)
    if not path.is_file():
        raise ApiError("not_found", f"File not found: {name}", 404)
    meta = read_json_file(path.parent / "process_model.json")
    primary = meta.get("primary_file_name")
    primary_name = primary.strip() if isinstance(primary, str) else ""
    if primary_name and path.name == primary_name:
        raise ApiError(
            "cannot_delete_primary",
            "Set another file as primary before deleting this one.",
            409,
        )
    _ensure_baseline_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    path.unlink()


def model_exists(*, tenant_id: str, process_model_identifier: str) -> bool:
    return is_process_model_identifier(process_model_identifier, tenant_id=tenant_id)


def _model_dmn_xml(*, tenant_id: str, process_model_identifier: str) -> str | None:
    """Read the model DMN source used by the core definition import.

    The core runtime accepts one DMN document alongside a BPMN definition.
    Model directories currently contain one executable DMN file; choosing the
    stable first filename keeps existing multi-file directories deterministic.
    """
    model_dir = _tenant_models_root(tenant_id) / process_model_identifier
    dmn_paths = sorted(path for path in model_dir.glob("*.dmn") if path.is_file())
    if not dmn_paths:
        return None
    if len(dmn_paths) > 1:
        LOGGER.warning(
            "Multiple DMN files found for process model %s; importing %s",
            process_model_identifier,
            dmn_paths[0].name,
        )
    try:
        # Bytes, not read_text: Start compares this with the published DMN as stored.
        return dmn_paths[0].read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError("invalid_file_content", "DMN file is not valid UTF-8", 400) from exc


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
                "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
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
        "status": process_model_status(
            tenant_id=resolved, process_model_identifier=process_model_identifier
        ),
    }


# --- Versioned publishing ---------------------------------------------------
# The spec dir holds the working copy; m8flow_process_model_version holds every
# published snapshot. The highest version is live: Start and human-task forms
# read it, so saving a published model changes nothing until Publish changes.


def model_file_bytes(*, tenant_id: str, process_model_identifier: str) -> dict[str, bytes]:
    """Every file of a model's working copy except process_model.json."""
    files: dict[str, bytes] = {}
    for row in list_model_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        body = read_model_file(
            tenant_id=tenant_id,
            process_model_identifier=process_model_identifier,
            file_name=row["name"],
        )
        if body is not None:
            files[row["name"]] = body
    return files


def _working_primary_name(*, tenant_id: str, process_model_identifier: str) -> str:
    path = _path_inside_tenant(tenant_id, _model_file_path(tenant_id, process_model_identifier))
    if path is not None and path.is_file():
        return path.name
    model_dir = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier)
    return _first_bpmn_name(model_dir) if model_dir is not None and model_dir.is_dir() else ""


def _content_digest(primary_file_name: str, files: dict[str, bytes]) -> str:
    digest = hashlib.sha256(primary_file_name.encode("utf-8"))
    for name in sorted(files):
        digest.update(b"\0" + name.encode("utf-8") + b"\0" + hashlib.sha256(files[name]).digest())
    return digest.hexdigest()


def _working_signature(*, tenant_id: str, process_model_identifier: str) -> tuple:
    """Cheap change detector for a model dir: stat only, no reads. Includes
    process_model.json, so a primary-file change also changes it."""
    model_dir = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier)
    if model_dir is None or not model_dir.is_dir():
        return ()
    entries = []
    for entry in os.scandir(model_dir):
        if entry.is_file():
            stat = entry.stat()
            entries.append((entry.name, stat.st_size, stat.st_mtime_ns, stat.st_ino))
    return (str(model_dir), *sorted(entries))


# ponytail: per-worker LRU keyed on the stat signature. A same-size rewrite within one
# mtime tick can show a stale badge until the next edit; Publish always re-hashes.
@functools.lru_cache(maxsize=4096)
def _digest_for(tenant_id: str, process_model_identifier: str, signature: tuple) -> str:
    return _content_digest(
        _working_primary_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier),
        model_file_bytes(tenant_id=tenant_id, process_model_identifier=process_model_identifier),
    )


def working_digest(*, tenant_id: str, process_model_identifier: str) -> str:
    """Digest of the working copy; reads and hashes files only when they changed."""
    return _digest_for(
        tenant_id,
        process_model_identifier,
        _working_signature(tenant_id=tenant_id, process_model_identifier=process_model_identifier),
    )


def _versions_query(*, tenant_id: str, process_model_identifier: str):
    return select(ProcessModelVersionModel).where(
        ProcessModelVersionModel.m8f_tenant_id == tenant_id,
        ProcessModelVersionModel.process_model_identifier == process_model_identifier,
    )


def latest_version(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> ProcessModelVersionModel | None:
    """The live published snapshot, or None when the model was never versioned."""
    return session.scalars(
        _versions_query(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
        .order_by(ProcessModelVersionModel.version.desc())
        .limit(1)
    ).first()


def _snapshot_working_copy(
    session: Session, *, tenant_id: str, process_model_identifier: str, published_by: str | None
) -> ProcessModelVersionModel:
    """Store the working copy as the next version; reuse the latest when unchanged."""
    files = model_file_bytes(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    primary = _working_primary_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if not primary or primary not in files:
        raise ApiError("no_primary_bpmn", "This process model has no BPMN file to publish", 400)
    digest = _content_digest(primary, files)
    latest = latest_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if latest is not None and latest.content_digest == digest:
        return latest
    row = ProcessModelVersionModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        version=(latest.version if latest is not None else 0) + 1,
        primary_file_name=primary,
        files={name: base64.b64encode(body).decode("ascii") for name, body in files.items()},
        content_digest=digest,
        published_by=published_by,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        # A concurrent publish took this version number; same content means it is ours.
        latest = latest_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
        if latest is not None and latest.content_digest == digest:
            return latest
        raise ApiError(
            "publish_conflict", "This process model was just published by someone else; try again", 409
        ) from None
    return row


def publish_version(
    session: Session, *, tenant_id: str, process_model_identifier: str, published_by: str
) -> ProcessModelVersionModel:
    """Make the working copy live. The caller sets the status to published."""
    if not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    # Re-checks unsupported constructs: only BPMN that Start can run goes live.
    found = read_primary_bpmn(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if found is None or not found[0].lower().endswith(".bpmn"):
        raise ApiError("no_primary_bpmn", "This process model has no BPMN file to publish", 400)
    return _snapshot_working_copy(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        published_by=published_by,
    )


def publish_with_edits(
    session: Session, *, tenant_id: str, process_model_identifier: str, published_by: str, **fields: Any
) -> None:
    """PUT {status: published, ...}: apply the edits first so the snapshot takes a
    primary_file_name sent with them. A failed publish puts process_model.json
    back: the request rolls back any baseline version, and Start would then run
    the new primary.

    process_model.json is the only disk write here; publishing is DB-only. A disk
    write added to this path must join the rollback below."""
    meta = _path_inside_tenant(
        tenant_id, _tenant_models_root(tenant_id) / process_model_identifier / "process_model.json"
    )
    if meta is None:
        raise ApiError("not_found", "Process model not found", 404)
    before = meta.read_bytes() if meta.is_file() else None
    try:
        update_process_model_metadata(
            session, tenant_id=tenant_id, process_model_identifier=process_model_identifier, **fields
        )
        publish_version(
            session, tenant_id=tenant_id, process_model_identifier=process_model_identifier, published_by=published_by
        )
    except Exception as exc:
        _restore_file(meta, before, exc)
        raise


def _ensure_baseline_version(session: Session, *, tenant_id: str, process_model_identifier: str) -> None:
    """Before the first write to a model published before versioning existed,
    snapshot its disk files as v1 -- otherwise that write would go live, since
    Start falls back to the working copy for a model with no versions.
    Drafts never need it: nothing of theirs is live.
    """
    if process_model_status(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    ) == PROCESS_MODEL_STATUS_DRAFT:
        return
    if not _working_primary_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        return
    if latest_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        return
    _snapshot_working_copy(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        published_by=None,
    )


def list_versions(session: Session, *, tenant_id: str, process_model_identifier: str) -> list[dict[str, Any]]:
    """Published versions, newest first, without their file contents."""
    rows = session.execute(
        select(
            ProcessModelVersionModel.version,
            ProcessModelVersionModel.published_by,
            ProcessModelVersionModel.created_at,
            ProcessModelVersionModel.primary_file_name,
        )
        .where(
            ProcessModelVersionModel.m8f_tenant_id == tenant_id,
            ProcessModelVersionModel.process_model_identifier == process_model_identifier,
        )
        .order_by(ProcessModelVersionModel.version.desc())
    ).all()
    live = process_model_status(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    ) == PROCESS_MODEL_STATUS_PUBLISHED
    return [
        {
            "version": row.version,
            "published_by": row.published_by,
            "created_at": row.created_at.isoformat(),
            "primary_file_name": row.primary_file_name,
            "is_live": live and index == 0,
        }
        for index, row in enumerate(rows)
    ]


def revert_to_version(
    session: Session, *, tenant_id: str, process_model_identifier: str, version: int, user_id: int
) -> dict[str, Any]:
    """Make the working copy exactly `version`'s files. Status and the live
    version are untouched: the restored copy goes live only on Publish changes."""
    model_dir = _path_inside_tenant(tenant_id, _tenant_models_root(tenant_id) / process_model_identifier)
    if model_dir is None or not model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    row = session.scalars(
        _versions_query(tenant_id=tenant_id, process_model_identifier=process_model_identifier).where(
            ProcessModelVersionModel.version == version
        )
    ).first()
    if row is None:
        raise ApiError("not_found", f"Version {version} not found", 404)
    files = {validate_leaf_file_name(name): body for name, body in _version_files(row).items()}
    xml = _version_primary_xml(row, files)  # before any write: a corrupt row leaves the working copy alone
    _reject_unsupported_constructs(xml)
    # Guard every target before any write: a file symlinked out of the tenant root refuses the whole revert.
    if any(_path_inside_tenant(tenant_id, model_dir / name) is None for name in files):
        raise ApiError("invalid_file_name", "Invalid file name", 400)
    # Build the reverted copy aside and swap it in last, so a failed write or
    # re-import never touches the working copy. Same filesystem as the models
    # (see delete_process_model), so the renames are atomic.
    trash = _models_base_dir() / ".m8flow-trash"
    trash.mkdir(parents=True, exist_ok=True)
    staging = trash / uuid.uuid4().hex
    backup = trash / uuid.uuid4().hex
    try:
        shutil.copytree(model_dir, staging, symlinks=True)
        for current in staging.iterdir():
            if current.is_file() and current.name != "process_model.json" and current.name not in files:
                current.unlink()
        for name, body in files.items():
            (staging / name).unlink(missing_ok=True)  # replace the entry; never write through a link
            (staging / name).write_bytes(body)
        meta_path = staging / "process_model.json"
        meta = {**read_json_file(meta_path), "primary_file_name": row.primary_file_name}
        meta_path.unlink(missing_ok=True)  # never write through a copied link
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        # Re-import before the swap so the restored BPMN has a definition, as after
        # a save. It only flushes: a failed swap below fails the request, which
        # rolls the import back.
        workflow.import_definition(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            bpmn_identifier=process_model_identifier,
            source_bpmn_xml=xml,
            source_dmn_xml=_first_dmn(files),  # the DMN Start reads from a version
            bpmn_name=Path(process_model_identifier).name,
        )
        if not _exchange_dirs(staging, model_dir):  # atomic: on error model_dir is untouched
            # ponytail: off Linux the model dir is absent between these two renames.
            model_dir.rename(backup)
            try:
                staging.rename(model_dir)
            except OSError as exc:
                try:
                    backup.rename(model_dir)
                except OSError:
                    LOGGER.critical(
                        "Revert of %s (tenant %s) failed and the working copy could not be put back; it is kept at %s",
                        process_model_identifier.replace("\r", "").replace("\n", ""),
                        tenant_id.replace("\r", "").replace("\n", ""),
                        backup,
                        exc_info=True,
                    )
                    raise ApiError(
                        "revert_restore_failed",
                        "Revert failed and the process model could not be restored; an administrator must restore it",
                        500,
                    ) from exc
                raise
            staging = backup
        # Either way `staging` now holds the old working copy.
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    identity = get_model_identity(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    return identity


def delete_versions(session: Session, *, tenant_id: str, process_model_identifier: str) -> None:
    for row in session.scalars(
        _versions_query(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    ):
        session.delete(row)


def _first_dmn(files: dict[str, bytes]) -> str | None:
    names = sorted(name for name in files if name.lower().endswith(".dmn"))
    return files[names[0]].decode("utf-8") if names else None


def _corrupt_version(row: ProcessModelVersionModel, detail: str) -> ApiError:
    return ApiError(
        "corrupt_process_model_version",
        f"Published version {row.version} of this process model {detail}",
        500,
    )


def _decode_version_file(row: ProcessModelVersionModel, name: str, body: object) -> bytes:
    """One stored file's bytes; a corrupt row is a clear 500, not a bare binascii error."""
    try:
        return base64.b64decode(body, validate=True)
    except (TypeError, ValueError):  # binascii.Error is a ValueError
        raise _corrupt_version(row, f"has a corrupt file: {name}") from None


def _version_files(row: ProcessModelVersionModel) -> dict[str, bytes]:
    return {name: _decode_version_file(row, name, body) for name, body in row.files.items()}


def _version_primary_xml(row: ProcessModelVersionModel, files: dict[str, bytes]) -> str:
    body = files.get(row.primary_file_name)
    if body is None:
        raise _corrupt_version(row, "is missing its BPMN file")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        raise _corrupt_version(row, "has a BPMN file that is not UTF-8") from None


def read_published_primary_bpmn(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> tuple[str, str, str | None] | None:
    """(file name, BPMN XML, DMN XML) Start runs: the live version, or the disk
    copy for a model never versioned. None when there is no BPMN at all."""
    row = latest_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if row is None:
        found = read_primary_bpmn(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
        if found is None:
            return None
        return (
            found[0],
            found[1],
            _model_dmn_xml(tenant_id=tenant_id, process_model_identifier=process_model_identifier),
        )
    files = _version_files(row)
    xml = _version_primary_xml(row, files)
    _reject_unsupported_constructs(xml)
    return row.primary_file_name, xml, _first_dmn(files)


def read_published_file(
    session: Session, *, tenant_id: str, process_model_identifier: str, file_name: str
) -> bytes | None:
    """One file of the live version (disk for a model never versioned)."""
    validate_leaf_file_name(file_name)
    row = latest_version(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if row is None:
        return read_model_file(
            tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=file_name
        )
    encoded = row.files.get(file_name)
    return _decode_version_file(row, file_name, encoded) if encoded is not None else None


def attach_publish_state(session: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add `published_version` and `has_unpublished_changes` to identity rows
    (each carries `tenant_id`, `id`, `status`). A draft has nothing live, so it
    never reports unpublished changes."""
    if not rows:
        return rows
    # ponytail: reads every version's (version, digest) for these tenants; select
    # only the max version per model if version counts grow large.
    latest: dict[tuple[str, str], tuple[int, str]] = {}
    for tenant, model, version, digest in session.execute(
        select(
            ProcessModelVersionModel.m8f_tenant_id,
            ProcessModelVersionModel.process_model_identifier,
            ProcessModelVersionModel.version,
            ProcessModelVersionModel.content_digest,
        ).where(ProcessModelVersionModel.m8f_tenant_id.in_({row["tenant_id"] for row in rows}))
    ):
        if (tenant, model) not in latest or version > latest[(tenant, model)][0]:
            latest[(tenant, model)] = (version, digest)
    for row in rows:
        found = latest.get((row["tenant_id"], row["id"]))
        row["published_version"] = found[0] if found else None
        row["has_unpublished_changes"] = bool(
            found
            and row.get("status") != PROCESS_MODEL_STATUS_DRAFT
            and working_digest(tenant_id=row["tenant_id"], process_model_identifier=row["id"]) != found[1]
        )
    return rows


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


def _models_base_dir() -> Path:
    return Path(
        os.environ.get("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
        or os.environ.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR")
        or "/tmp/m8flow-process-models"
    )


def _tenant_models_root(tenant_id: str) -> Path:
    return _models_base_dir() / tenant_id


def _resolved_inside_tenant(tenant_id: str, relative: str) -> Path:
    """Resolve `relative` under the tenant spec dir; reject escapes."""
    root = _tenant_models_root(tenant_id).resolve()
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ApiError("invalid_process_group", "Invalid process group identifier", 400)
    return target


def _path_inside_tenant(tenant_id: str, path: Path) -> Path | None:
    """`path` normalized, or None when it leaves the tenant's models root --
    lexically or through a symlink. Returns the lexical path so a file keeps
    its own name. The lexical check compares two abspath()s sharing the root
    prefix, so case and separators cannot drift; the resolved check is a
    part-wise ancestor test (case-insensitive on Windows).

    Strict child: the tenant root itself is refused. Every caller addresses a
    model dir or a file in one; letting the root through would point
    delete/revert of an empty id at every model in the tenant."""
    root = os.path.abspath(_tenant_models_root(tenant_id))
    target = os.path.abspath(path)
    # Keep this exact shape: CodeQL's path-injection query only treats `target`
    # as sanitized when the startswith receiver is the abspath'd variable itself.
    if not target.startswith(root + os.sep):
        return None
    real_root = Path(os.path.realpath(root))
    real = Path(os.path.realpath(target))
    if real == real_root or not real.is_relative_to(real_root):
        return None
    return Path(target)


def _exchange_dirs(a: Path, b: Path) -> bool:
    """Atomically swap two directories (Linux renameat2 RENAME_EXCHANGE), so
    neither path is ever missing. False when unsupported: caller falls back.
    Raises OSError on any other failure."""
    if sys.platform != "linux":
        return False
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        return False
    at_fdcwd, rename_exchange = -100, 2
    if renameat2(at_fdcwd, os.fsencode(a), at_fdcwd, os.fsencode(b), rename_exchange) == 0:
        return True
    err = ctypes.get_errno()
    if err in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):  # kernel or filesystem lacks RENAME_EXCHANGE
        LOGGER.debug("renameat2 RENAME_EXCHANGE unsupported (%s); using rename fallback", os.strerror(err))
        return False
    raise OSError(err, os.strerror(err), str(a))


def _restore_file(path: Path, previous: bytes | None, cause: BaseException) -> None:
    """Put back a file a failed request overwrote (`previous` None: it was new).
    A failed put-back is a clear 500, not the original error over a half-applied edit."""
    try:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(previous)
    except OSError:
        LOGGER.critical(
            "Could not restore %s after a failed write",
            str(path).replace("\r", "").replace("\n", ""),
            exc_info=True,
        )
        raise ApiError(
            "restore_failed",
            "The change failed and the file could not be restored; an administrator must restore it",
            500,
        ) from cause


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
