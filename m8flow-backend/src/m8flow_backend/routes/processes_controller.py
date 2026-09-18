from __future__ import annotations

from urllib.parse import quote, unquote

from flask import Response, g, request
from sqlalchemy import select

from m8flow_backend import catalog, workflow
from m8flow_backend.auth import (
    require_catalog_write_tenant_id,
    require_current_user,
    require_tenant_id,
    resolve_read_tenant_id,
)
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response

_FILE_MIMETYPES = {
    "bpmn": "application/xml",
    "dmn": "application/xml",
    "json": "application/json",
    "md": "text/markdown",
}


def _safe_content_disposition(filename: str) -> dict[str, str]:
    """Build Content-Disposition header safe from injection (RFC 5987)."""
    safe = quote(filename, safe="")
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{safe}"}


def process_model_identifier_from_path_param(modified: str | None) -> str:
    """Colon-encoded nested ids, including a percent-encoded colon from fetch/Vite."""
    value = modified or ""
    previous = None
    while previous != value:
        previous = value
        value = unquote(value)
    return value.replace(":", "/")


def _process_group_permission_uri(*, modified_process_group_identifier: str, **_kwargs) -> str:
    group_id = process_model_identifier_from_path_param(modified_process_group_identifier)
    return f"/v1.0/process-groups/{group_id}"


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    on_deny="empty",
    empty_response=[],
)
def list_process_models():
    """Designer Processes models list. New endpoint rather than widening
    GET /v1.0/process-models (path-only JSON used by thin/MCP clients).

    Auth mirrors Home: GET /v1.0/process-models; denied
    callers get [] (200), not 403. A super-admin on All Tenants gets the
    merged cross-tenant catalog, each row tagged with its own tenant.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    group = request.args.get("group") or None
    if group is not None:
        group = group.strip() or None

    run_stats = workflow.process_model_run_stats(session, tenant_id=tenant_id)
    rows = catalog.list_model_rows(tenant_id=tenant_id, group=group)
    if tenant_id is None:
        _attach_tenant_names(session, rows)
    return success_response(
        [
            {
                **row,
                # run_stats is keyed by (tenant, identifier): identifiers
                # collide across tenants.
                "last_run_in_seconds": run_stats.get(
                    (row["tenant_id"], row["id"]), {}
                ).get("last_run_in_seconds"),
                "runs_30d": run_stats.get((row["tenant_id"], row["id"]), {}).get("runs_30d", 0),
            }
            for row in rows
        ],
        200,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/process-groups",
    on_deny="empty",
    empty_response=[],
)
def list_process_groups():
    """Designer Process groups picker. All Tenants merges every tenant's
    groups (each row tagged with its tenant); deny → []."""
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    run_stats = workflow.process_model_run_stats(session, tenant_id=tenant_id)
    rows = catalog.list_group_rows(tenant_id=tenant_id)
    if tenant_id is None:
        _attach_tenant_names(session, rows)
    result = []
    for row in rows:
        row_tenant_id = row["tenant_id"]
        model_ids = catalog.list_models(row["id"], tenant_id=row_tenant_id)
        last_runs = [
            run_stats[(row_tenant_id, mid)]["last_run_in_seconds"]
            for mid in model_ids
            if (row_tenant_id, mid) in run_stats
            and run_stats[(row_tenant_id, mid)]["last_run_in_seconds"] is not None
        ]
        result.append(
            {
                **row,
                "last_run_in_seconds": max(last_runs) if last_runs else None,
            }
        )
    return success_response(result, 200)


def _group_write_payload(body: dict | None) -> dict:
    if isinstance(body, dict):
        return body
    return request.get_json(silent=True) or {}


def _attach_tenant_names(session, rows) -> None:
    """Add `tenant_name` to cross-tenant catalog rows (all-tenants reads only).

    Same lookup as home_controller's recent-instances list; skipped entirely
    on the normal tenant-scoped path.
    """
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    tenant_ids = {row.get("tenant_id") for row in rows if row.get("tenant_id")}
    if not tenant_ids:
        return
    name_by_id = {
        tenant.id: tenant.name
        for tenant in session.scalars(
            select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))
        )
    }
    for row in rows:
        tid = row.get("tenant_id")
        if tid:
            row["tenant_name"] = name_by_id.get(tid) or tid


def _explicit_body_tenant(payload: dict) -> str | None:
    raw = payload.get("m8f_tenant_id")
    return raw if isinstance(raw, str) else None


@handle_api_errors
@require_permission(
    uri="/v1.0/process-groups",
    forbidden_message="Not permitted to create a process group",
)
def create_process_group(body: dict | None = None):
    """Create a process group (id, display_name, description). Nested ids
    (`parent/child`) create the leaf directory. Write op: denied → 403.
    Super-admin may write when bound to a concrete tenant (M8F-479).
    """
    user = require_current_user()
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    row = catalog.create_process_group(
        tenant_id=tenant_id,
        group_id=payload.get("id") or "",
        display_name=payload.get("display_name"),
        description=payload.get("description"),
    )
    return success_response({**row, "last_run_in_seconds": None}, 201)


@handle_api_errors
@require_permission(
    uri=_process_group_permission_uri,
    forbidden_message="Not permitted to update this process group",
)
def update_process_group(modified_process_group_identifier: str, body: dict | None = None):
    """Update process-group metadata only. Id / path does not change."""
    user = require_current_user()
    session = g.db_session
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    group_id = process_model_identifier_from_path_param(modified_process_group_identifier)
    row = catalog.update_process_group(
        tenant_id=tenant_id,
        group_id=group_id,
        display_name=payload.get("display_name") if "display_name" in payload else None,
        description=payload.get("description") if "description" in payload else None,
    )
    run_stats = workflow.process_model_run_stats(session, tenant_id=tenant_id)
    model_ids = catalog.list_models(row["id"], tenant_id=tenant_id)
    last_runs = [
        run_stats[(tenant_id, mid)]["last_run_in_seconds"]
        for mid in model_ids
        if (tenant_id, mid) in run_stats
        and run_stats[(tenant_id, mid)]["last_run_in_seconds"] is not None
    ]
    return success_response(
        {**row, "last_run_in_seconds": max(last_runs) if last_runs else None},
        200,
    )


@handle_api_errors
@require_permission(
    uri=_process_group_permission_uri,
    forbidden_message="Not permitted to delete this process group",
)
def delete_process_group(modified_process_group_identifier: str):
    """Delete a process group directory. Blocked (409) while any process
    instance still references a model in this group or nested under it.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_catalog_write_tenant_id(user)

    group_id = process_model_identifier_from_path_param(modified_process_group_identifier)
    if not catalog.process_group_exists(tenant_id=tenant_id, group_id=group_id):
        raise ApiError("not_found", "Process group not found", 404)

    instance_count = workflow.count_instances_for_process_group(
        session, tenant_id=tenant_id, group_id=group_id
    )
    if instance_count > 0:
        raise ApiError(
            "process_group_has_instances",
            f"This process group has {instance_count} process instance(s) and cannot be deleted.",
            409,
        )

    catalog.delete_process_group(tenant_id=tenant_id, group_id=group_id)
    return success_response({"deleted": True, "id": group_id}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to create a process model",
)
def create_process_model(body: dict | None = None):
    """Create a process model under an existing group, with a default BPMN.
    Super-admin may write when bound to a concrete tenant (M8F-479). Distinct
    from thin POST /v1.0/process-models ({path, xml}).
    """
    user = require_current_user()
    session = g.db_session
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    identity = catalog.create_process_model(
        session,
        tenant_id=tenant_id,
        group_id=payload.get("group_id") or "",
        leaf_id=payload.get("id") or "",
        display_name=payload.get("display_name"),
        description=payload.get("description"),
        user_id=user.id,
    )
    session.flush()
    return success_response(identity, 201)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to update this process model",
)
def update_process_model(modified_process_model_identifier: str, body: dict | None = None):
    """Update process-model metadata (display_name, description, primary_file_name)."""
    user = require_current_user()
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    identity = catalog.update_process_model_metadata(
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        display_name=payload.get("display_name") if "display_name" in payload else None,
        description=payload.get("description") if "description" in payload else None,
        primary_file_name=payload.get("primary_file_name") if "primary_file_name" in payload else None,
    )
    return success_response(identity, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to copy this process model",
)
def copy_process_model(modified_process_model_identifier: str, body: dict | None = None):
    """Duplicate a process model under the same group (new leaf id + display
    name). Copies files; does not copy process instances. Super-admin may write
    when bound to a concrete tenant (M8F-479). No git.
    """
    user = require_current_user()
    session = g.db_session
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    identity = catalog.copy_process_model(
        session,
        tenant_id=tenant_id,
        source_identifier=process_model_identifier,
        leaf_id=payload.get("id") or "",
        display_name=payload.get("display_name"),
        user_id=user.id,
    )
    session.flush()
    return success_response(identity, 201)


def _model_file_bytes(*, tenant_id: str, process_model_identifier: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for row in catalog.list_model_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        body = catalog.read_model_file(
            tenant_id=tenant_id,
            process_model_identifier=process_model_identifier,
            file_name=row["name"],
        )
        if body is not None:
            files[row["name"]] = body
    return files


def _primary_bpmn_name(*, tenant_id: str, process_model_identifier: str) -> str:
    rows = catalog.list_model_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    for row in rows:
        if row.get("primary") and str(row["name"]).lower().endswith(".bpmn"):
            return row["name"]
    bpmn = [row["name"] for row in rows if str(row["name"]).lower().endswith(".bpmn")]
    if not bpmn:
        raise ApiError("process_model_primary_file_not_set", "The primary file is not set for the given process model.", 400)
    return bpmn[0]


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to run process model tests",
)
def run_process_model_tests(modified_process_model_identifier: str):
    """Run BPMN unit tests (`test_*.json`) for a process model."""
    user = require_current_user()
    tenant_id = require_catalog_write_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)

    files = _model_file_bytes(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    result = workflow.run_process_model_tests(
        files,
        test_case_file=request.args.get("test_case_file") or None,
        test_case_identifier=request.args.get("test_case_identifier") or None,
    )
    return success_response(result, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    on_deny="404",
    forbidden_message="Process model not found",
)
def list_script_unit_tests(modified_process_model_identifier: str):
    """List script-task unit tests stored on the primary BPMN."""
    user = require_current_user()
    tenant_id = resolve_read_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    identity = catalog.get_model_identity(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    tenant_id = identity["tenant_id"]

    primary = _primary_bpmn_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    body = catalog.read_model_file(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=primary
    )
    if body is None:
        raise ApiError("not_found", "Primary BPMN not found", 404)
    return success_response({"tests": workflow.list_script_unit_tests(body.decode("utf-8"))}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to create a script unit test",
)
def create_script_unit_test(modified_process_model_identifier: str, body: dict | None = None):
    """Store a script unit test on the primary BPMN. No git."""
    user = require_current_user()
    session = g.db_session
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    primary = _primary_bpmn_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    xml_bytes = catalog.read_model_file(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=primary
    )
    if xml_bytes is None:
        raise ApiError("not_found", "Primary BPMN not found", 404)
    xml, unit_id = workflow.add_script_unit_test(
        xml_bytes.decode("utf-8"),
        bpmn_task_identifier=str(payload.get("bpmn_task_identifier") or ""),
        input_json=payload.get("input_json") if isinstance(payload.get("input_json"), dict) else {},
        expected_output_json=(
            payload.get("expected_output_json") if isinstance(payload.get("expected_output_json"), dict) else {}
        ),
    )
    workflow.import_definition(
        session,
        tenant_id=tenant_id,
        user_id=user.id,
        bpmn_identifier=process_model_identifier,
        source_bpmn_xml=xml,
        bpmn_name=primary,
    )
    catalog.write_spec_file(
        tenant_id=tenant_id, path=process_model_identifier, file_name=primary, content=xml.encode("utf-8")
    )
    session.flush()
    return success_response({"ok": True, "id": unit_id}, 201)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to run a script unit test",
)
def run_script_unit_test(modified_process_model_identifier: str, body: dict | None = None):
    """Run a script unit test (ad-hoc body or stored unit_test_id)."""
    user = require_current_user()
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    unit_test_id = payload.get("unit_test_id")
    if isinstance(unit_test_id, str) and unit_test_id.strip():
        primary = _primary_bpmn_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
        xml_bytes = catalog.read_model_file(
            tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=primary
        )
        if xml_bytes is None:
            raise ApiError("not_found", "Primary BPMN not found", 404)
        result = workflow.run_stored_script_unit_test(xml=xml_bytes.decode("utf-8"), unit_test_id=unit_test_id.strip())
        return success_response(result, 200)

    result = workflow.run_script_unit_test(
        python_script=str(payload.get("python_script") or ""),
        input_json=payload.get("input_json") if isinstance(payload.get("input_json"), dict) else {},
        expected_output_json=(
            payload.get("expected_output_json") if isinstance(payload.get("expected_output_json"), dict) else {}
        ),
    )
    return success_response(result, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    on_deny="404",
    forbidden_message="Process model not found",
)
def get_process_model(modified_process_model_identifier: str):
    """Combined process-model detail for the designer detail page."""
    user = require_current_user()
    session = g.db_session
    tenant_id = resolve_read_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    identity = catalog.get_model_identity(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    # Every read below runs against the model's own tenant, so an all-tenants
    # lookup still reads exactly one tenant's data.
    tenant_id = identity["tenant_id"]

    limit_raw = request.args.get("recent_limit")
    try:
        recent_limit = int(limit_raw) if limit_raw is not None else 10
    except (TypeError, ValueError):
        recent_limit = 10

    stats = workflow.process_model_detail_stats(
        session, tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    recent = workflow.list_recent_instances_for_process_model(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        limit=recent_limit,
    )
    files = catalog.list_model_files(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    return success_response(
        {
            **identity,
            **stats,
            "recent_instances": recent,
            "files": files,
        },
        200,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    on_deny="404",
    forbidden_message="Process model not found",
)
def get_process_model_file(modified_process_model_identifier: str, file_name: str):
    """Raw content of one named file (.bpmn/.dmn/etc.) inside a process model.

    Auth/tenant gating mirrors get_process_model: denied or missing model ->
    404 (no distinction, same as the detail endpoint — avoids confirming a
    tenant-scoped model's existence to a caller who can't read it).
    """
    user = require_current_user()
    tenant_id = resolve_read_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    identity = catalog.get_model_identity(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if identity is None:
        raise ApiError("not_found", "Process model not found", 404)
    tenant_id = identity["tenant_id"]

    catalog.validate_leaf_file_name(file_name)
    content = catalog.read_model_file(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=file_name
    )
    if content is None:
        raise ApiError("not_found", f"File not found: {file_name}", 404)

    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    mime = _FILE_MIMETYPES.get(extension, "application/octet-stream")
    return Response(content, mimetype=mime, headers=_safe_content_disposition(file_name))


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to modify this process model",
)
def put_process_model_file(modified_process_model_identifier: str, file_name: str):
    """Save one named file's bytes into an existing process model directory.

    .bpmn content is re-imported (same as catalog.save) so the process
    definition stays in sync; every file type is git-committed. Denied ->
    403 (a write op, unlike the read endpoints' 404-for-denied — there is
    nothing tenant-identity-revealing to protect by hiding the model here).
    """
    user = require_current_user()
    tenant_id = require_catalog_write_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)

    catalog.validate_leaf_file_name(file_name)
    content = request.get_data()
    if not content:
        raise ApiError("missing_content", "Request body is required", 400)

    path = catalog.update_file(
        {"id": process_model_identifier}, file_name, content, tenant_id=tenant_id
    )
    stat = path.stat()
    return success_response(
        {
            "name": file_name,
            "size_bytes": int(stat.st_size),
            "updated_at_in_seconds": int(stat.st_mtime),
        },
        200,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to modify this process model",
)
def create_process_model_file(modified_process_model_identifier: str, body: dict | None = None):
    """Create one file in an existing process model (default contents or upload).
    Super-admin may write when bound to a concrete tenant (M8F-479). No git.
    """
    user = require_current_user()
    session = g.db_session
    payload = _group_write_payload(body)
    tenant_id = require_catalog_write_tenant_id(user, explicit_tenant_id=_explicit_body_tenant(payload))

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    file_name = payload.get("file_name") or ""
    content: bytes | None
    if "content" in payload:
        raw = payload.get("content")
        if not isinstance(raw, str):
            raise ApiError("missing_content", "content must be a string", 400)
        content = raw.encode("utf-8")
    else:
        content = None

    row = catalog.create_model_file(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        file_name=file_name,
        content=content,
        user_id=user.id,
    )
    session.flush()
    return success_response(row, 201)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to modify this process model",
)
def delete_process_model_file(modified_process_model_identifier: str, file_name: str):
    """Delete one named file. Primary file is 409."""
    user = require_current_user()
    tenant_id = require_catalog_write_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    catalog.delete_model_file(
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        file_name=file_name,
    )
    return success_response({"deleted": True, "name": file_name}, 200)


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances",
    forbidden_message="Not permitted to start this process model",
)
def start_process_instance(modified_process_model_identifier: str):
    """Start (create + initialize) a process instance from a model's latest
    definition — the Processes list/detail "Start" action. Write op: denied →
    403 (nothing tenant-identity-revealing to hide, same as
    put_process_model_file). Started with no submission variables; models that
    need a start form are launched empty here, same as workflow.start's own
    default.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)

    instance = workflow.start(
        session,
        tenant_id=tenant_id,
        user_id=user.id,
        process_model_identifier=process_model_identifier,
    )
    session.flush()
    return success_response(
        {
            "id": instance.id,
            "status": instance.status,
            "process_model_identifier": process_model_identifier,
        },
        201,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/process-models",
    forbidden_message="Not permitted to delete this process model",
)
def delete_process_model(modified_process_model_identifier: str):
    """Delete a process model's on-disk BPMN spec (git-committed removal).
    Blocked (409) while any process instance still references the model, so
    its run history/audit rows are never orphaned — callers must remove or
    let those complete first. Write op: denied → 403.
    """
    user = require_current_user()
    session = g.db_session
    tenant_id = require_catalog_write_tenant_id(user)

    process_model_identifier = process_model_identifier_from_path_param(
        modified_process_model_identifier
    )
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)

    instance_count = workflow.count_instances_for_process_model(
        session, tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    if instance_count > 0:
        raise ApiError(
            "process_model_has_instances",
            f"This process model has {instance_count} process instance(s) and cannot be deleted.",
            409,
        )

    catalog.delete_process_model(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    )
    return success_response({"deleted": True, "id": process_model_identifier}, 200)
