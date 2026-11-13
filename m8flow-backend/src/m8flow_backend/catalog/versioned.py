"""Catalog mutations for versioned process models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from sqlalchemy.orm import Session

from m8flow_backend import catalog, workflow
from m8flow_backend.catalog import versions
from m8flow_backend.errors import ApiError
from m8flow_backend.models.process_model_version import ProcessModelState


def read_state(tenant_id: str, model_id: str) -> ProcessModelState | None:
    return versions.state(versions.request_session(), tenant_id, model_id)


def version_fields(tenant_id: str, model_id: str, status: str) -> dict[str, Any]:
    session = versions.request_session()
    model = versions.state(session, tenant_id, model_id)
    if model is not None:
        return versions.fields(session, model)
    legacy = versions.legacy_model(tenant_id, model_id)
    return {
        "published_version": None if status == "draft" else 1,
        "draft_version": 1 if status == "draft" else None,
        "has_unpublished_changes": False,
        "working_revision": versions.legacy_revision(legacy[1]) if legacy else None,
    }


def decode_xml(body: bytes, kind: str) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError("invalid_file_content", f"{kind} file is not valid UTF-8", 400) from exc


def bpmn_xml(contents: dict[str, Any], name: str) -> str:
    body = versions.read_file(contents, name)
    if body is None:
        raise ApiError("invalid_process_model", "The BPMN file is missing from this version.", 400)
    xml = decode_xml(body, "BPMN")
    return xml


def validate_bpmn(xml: str) -> Element:
    try:
        root = catalog._reject_unsupported_constructs(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise ApiError("invalid_process_model", "BPMN XML is malformed", 400) from exc
    if not any(catalog._xml_local_name(node.tag) == "process" and node.get("id") for node in root):
        raise ApiError("invalid_process_model", "BPMN must declare a process", 400)
    return root


def selected_process_id(contents: dict[str, Any], model_id: str, *, validate_start: bool = False) -> str | None:
    primary = versions.primary_bpmn(contents, model_id)
    if primary is None:
        raise ApiError("invalid_process_model", "Select a primary BPMN file.", 400)
    xml = bpmn_xml(contents, primary)
    root = validate_bpmn(xml)
    processes = [
        node for node in root
        if catalog._xml_local_name(node.tag) == "process" and node.get("id")
        and node.get("isExecutable", "true").lower() == "true"
    ]
    preferred = contents["primary_process_id"]
    selected = next((node for node in processes if node.get("id") == preferred), None)
    if selected is None and len(processes) == 1:
        selected = processes[0]
    if selected is None or (validate_start and not any(
        catalog._xml_local_name(node.tag) == "startEvent" for node in selected
    )):
        raise ApiError("invalid_process_model", "The primary BPMN must select an executable process with a start event.", 422)
    return selected.get("id")


def dmn_xml(contents: dict[str, Any], xml: str) -> str | None:
    sources = {
        name: decode_xml(versions.read_file(contents, name), "DMN")
        for name in sorted(contents["files"]) if name.lower().endswith(".dmn")
    }
    return catalog.select_dmn_xml(sources, xml)


def for_write(
    session: Session, tenant_id: str, model_id: str, *, expected: str | None = None,
) -> ProcessModelState:
    versions.lock_tenant(session, tenant_id)
    model = versions.write_state(session, tenant_id, model_id)
    if model is None:
        model = versions.import_legacy(session, tenant_id, model_id)
    if model is None or model.deleted:
        raise ApiError("not_found", "Process model not found", 404)
    versions.check_revision(model, expected)
    return model


def create(
    session: Session, tenant_id: str, model_id: str, *, files: dict[str, bytes],
    name: str, description: str = "", primary: str | None = None, process_id: str | None = None,
) -> ProcessModelState:
    versions.lock_tenant(session, tenant_id)
    catalog._resolved_inside_tenant(tenant_id, model_id, **catalog._MODEL_PATH_ERROR)
    if catalog.model_exists(tenant_id=tenant_id, process_model_identifier=model_id, session=session):
        raise ApiError("process_model_exists", "Process model already exists", 409)
    if catalog.process_group_exists(tenant_id=tenant_id, group_id=model_id):
        raise ApiError("process_group_exists", "A process group already uses this id", 409)
    for file_name, body in files.items():
        _validate_file(file_name, body)
    contents = versions.snapshot(files, primary, process_id)
    if not versions.bpmn_names(contents):
        raise ApiError("invalid_process_model", "A process model requires a BPMN file", 400)
    return versions.initialize(session, tenant_id, model_id, contents, display_name=name, description=description)


def _validate_file(name: str, content: bytes) -> None:
    catalog.validate_leaf_file_name(name)
    if name.lower() in catalog._RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    if name.lower().endswith(".bpmn"):
        validate_bpmn(decode_xml(content, "BPMN"))
    elif name.lower().endswith(".dmn"):
        try:
            decision = catalog._dmn_decision_id(decode_xml(content, "DMN"))
        except DefusedXmlException as exc:
            raise ApiError("invalid_file_content", "DMN XML is malformed", 400) from exc
        if decision is None:
            raise ApiError("invalid_file_content", "DMN file must be DMN XML with a decision", 400)


def file_row(model: ProcessModelState, name: str) -> dict[str, Any]:
    raw = versions.read_file(model.working, name)
    row = {
        "name": name,
        "size_bytes": len(raw),
        "updated_at": model.updated_at.isoformat(),
        "primary": name == versions.primary_bpmn(model.working, model.model_id),
    }
    if name.lower().endswith(".dmn"):
        try:
            row["decision_id"] = catalog._dmn_decision_id(raw.decode("utf-8", errors="replace"))
        except DefusedXmlException:
            row["decision_id"] = None
    return row


def write_file(
    model: ProcessModelState, name: str, content: bytes, *, create_only: bool = False,
) -> dict[str, Any]:
    _validate_file(name, content)
    files = model.working["files"]
    if create_only and name in files:
        raise ApiError("file_exists", "A file with this name already exists", 409)
    versions.replace_working(model, {**model.working, "files": {**files, name: versions.encode_file(content)}})
    return file_row(model, name)


def create_file(model: ProcessModelState, name: str, content: bytes | None) -> dict[str, Any]:
    catalog.validate_leaf_file_name(name)
    if name.lower() in catalog._RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    allowed = catalog._DEFAULT_CREATE_SUFFIXES if content is None else catalog._UPLOAD_SUFFIXES
    if catalog._file_suffix(name) not in allowed:
        raise ApiError("unsupported_file_type", "That file type is not allowed.", 400)
    if content == b"":
        raise ApiError("missing_content", "Request body is required", 400)
    return write_file(model, name, catalog._default_file_bytes(name) if content is None else content, create_only=True)


def remove_file(model: ProcessModelState, name: str) -> None:
    catalog.validate_leaf_file_name(name)
    if name.lower() in catalog._RESERVED_MODEL_FILE_NAMES:
        raise ApiError("reserved_file_name", "That file name is reserved", 400)
    files = dict(model.working["files"])
    if name not in files:
        raise ApiError("not_found", f"File not found: {name}", 404)
    if name == versions.primary_bpmn(model.working, model.model_id):
        raise ApiError("cannot_delete_primary", "Set another file as primary before deleting this one.", 409)
    del files[name]
    versions.replace_working(model, {**model.working, "files": files})


def set_primary(model: ProcessModelState, file_name: str, process_id: str | None = None) -> None:
    if file_name not in versions.bpmn_names(model.working):
        raise ApiError("invalid_primary_file", "Primary file must be a BPMN file in this model", 400)
    if process_id is None and file_name == model.working["primary_file_name"]:
        return
    versions.replace_working(model, {
        **model.working, "primary_file_name": file_name, "primary_process_id": process_id,
    })


def publish(session: Session, model: ProcessModelState, *, user_id: int, username: str) -> None:
    if model.status == "paused":
        raise ApiError("process_model_paused", "Resume the process before publishing changes.", 409)
    draft = versions.draft_number(session, model)
    if draft is None and model.status == "published":
        return
    if draft is not None:
        selected_process_id(model.working, model.model_id, validate_start=True)
        entry = versions.add_release(session, model, published_by=username, published_at=datetime.now(UTC))
        workflow.deploy_release(session, entry=entry, user_id=user_id)
    else:
        entry = versions.release(session, model, model.latest_version)
        workflow.deploy_release(session, entry=entry, user_id=user_id, resume=True)
    model.status = "published"
    versions.touch(model)
    session.flush()


def set_status(session: Session, model: ProcessModelState, status: str, *, user_id: int, username: str) -> None:
    status = catalog._validated_status_transition(current=model.status, requested=status)
    if status == model.status:
        return
    if status == "published":
        if model.status == "paused":
            entry = versions.release(session, model, model.latest_version)
            workflow.deploy_release(session, entry=entry, user_id=user_id, resume=True, bootstrap=entry.published_at is None)
            model.status = status
            versions.touch(model)
        else:
            publish(session, model, user_id=user_id, username=username)
        return
    workflow.disable_model_timers(session, tenant_id=model.m8f_tenant_id, model_id=model.model_id)
    model.status = status
    versions.touch(model)


def restore(session: Session, model: ProcessModelState, number: int | None) -> None:
    entry = versions.release(session, model, number if number is not None else model.latest_version)
    if entry is None:
        raise ApiError("not_found", "Published version not found", 404)
    versions.replace_working(model, entry.contents)


def history(session: Session, tenant_id: str, model_id: str) -> dict[str, Any]:
    model = versions.state(session, tenant_id, model_id)
    if model is not None and model.deleted:
        raise ApiError("not_found", "Process model not found", 404)
    if model is None:
        legacy = versions.legacy_model(tenant_id, model_id)
        if legacy is None:
            raise ApiError("not_found", "Process model not found", 404)
        status = catalog.process_model_status(tenant_id=tenant_id, process_model_identifier=model_id)
        fields = version_fields(tenant_id, model_id, status)
        entries = [] if status == "draft" else [{"version": 1, "published_at": None, "published_by": None}]
    else:
        status = model.status
        fields = versions.fields(session, model)
        entries = [{
            "version": entry.version,
            "published_at": entry.published_at.isoformat() if entry.published_at else None,
            "published_by": entry.published_by,
        } for entry in versions.model_releases(session, model)]
    return {**fields, "status": status, "versions": entries}


def delete_model(session: Session, model: ProcessModelState) -> None:
    workflow.disable_model_timers(session, tenant_id=model.m8f_tenant_id, model_id=model.model_id)
    model.deleted = True
    model.working = versions.snapshot({})


def identity(session: Session, model: ProcessModelState) -> dict[str, Any]:
    group = catalog.process_group_id_for_model(model.model_id)
    return {
        "id": model.model_id, "tenant_id": model.m8f_tenant_id,
        "display_name": model.display_name, "description": model.description, "status": model.status,
        "group_id": group,
        "group_display_name": catalog.process_group_display_name(tenant_id=model.m8f_tenant_id, group_id=group),
        **versions.fields(session, model),
    }


def update_metadata(
    session: Session, model: ProcessModelState, payload: dict[str, Any], *, user_id: int, username: str,
) -> None:
    for field in ("display_name", "description"):
        value = payload.get(field)
        if isinstance(value, str):
            setattr(model, field, value.strip() or (model.model_id.rsplit("/", 1)[-1] if field == "display_name" else ""))
    primary = payload.get("primary_file_name")
    if isinstance(primary, str):
        set_primary(model, primary.strip(), payload.get("primary_process_id"))
    status = payload.get("status")
    if status is not None:
        set_status(session, model, status, user_id=user_id, username=username)
