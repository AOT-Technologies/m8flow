from __future__ import annotations

import json
from urllib.parse import quote

from flask import Response, jsonify, request, g

from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.models.template import TemplateModel
from m8flow_backend.services.template_service import TemplateService


def _safe_content_disposition(filename: str) -> dict[str, str]:
    """Build Content-Disposition header safe from injection (RFC 5987)."""
    safe = quote(filename, safe="")
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{safe}"}


def _serialize_template(template: TemplateModel, include_bpmn: bool = True) -> dict:
    """Serialize template with optional BPMN content. Includes files list from template.files."""
    files_list = template.files or []
    result = {
        "id": template.id,
        "templateKey": template.template_key,
        "version": template.version,
        "name": template.name,
        "description": template.description,
        "tags": template.tags,
        "category": template.category,
        "tenantId": template.m8f_tenant_id,
        "visibility": template.visibility,
        "files": [
            {"fileType": e.get("file_type", "bpmn"), "fileName": e.get("file_name", "")}
            for e in files_list
        ],
        "isPublished": template.is_published,
        "status": "published" if template.is_published else (template.status or "draft"),
        "createdBy": template.created_by,
        "modifiedBy": template.modified_by,
        "createdAtInSeconds": template.created_at_in_seconds,
        "updatedAtInSeconds": template.updated_at_in_seconds,
    }

    if include_bpmn:
        try:
            bpmn_bytes = TemplateService.get_first_bpmn_content(template)
            result["bpmnContent"] = bpmn_bytes.decode("utf-8") if bpmn_bytes else None
        except Exception:
            result["bpmnContent"] = None
    return result


def template_list():
    latest_only = request.args.get("latest_only", "true").lower() != "false"
    category = request.args.get("category")
    tag = request.args.get("tag")  # Single tag or comma-separated
    owner = request.args.get("owner")  # created_by username
    visibility = request.args.get("visibility")  # PRIVATE, TENANT, PUBLIC
    search = request.args.get("search")  # Text search in name/description
    template_key = request.args.get("template_key")
    published_only = request.args.get("published_only", "false").lower() == "true"
    sort_by = request.args.get("sort_by")  # created, name
    order = request.args.get("order", "desc").lower()
    if order not in ("asc", "desc"):
        order = "desc"

    # Pagination params
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("per_page", 10)), 100))
    except (ValueError, TypeError):
        per_page = 10

    user = getattr(g, "user", None)
    templates, pagination = TemplateService.list_templates(
        user=user,
        tenant_id=getattr(g, "m8flow_tenant_id", None),
        latest_only=latest_only,
        category=category,
        tag=tag,
        owner=owner,
        visibility=visibility,
        search=search,
        template_key=template_key,
        published_only=published_only,
        sort_by=sort_by,
        order=order,
        page=page,
        per_page=per_page,
    )
    # For list responses, omit BPMN content for performance
    return jsonify({
        "results": [_serialize_template(t, include_bpmn=False) for t in templates],
        "pagination": pagination,
    })


def _metadata_from_headers() -> dict:
    tags_raw = request.headers.get("X-Template-Tags")
    tags = None
    if tags_raw:
        try:
            tags = json.loads(tags_raw)
        except json.JSONDecodeError:
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    return {
        "template_key": request.headers.get("X-Template-Key"),
        "name": request.headers.get("X-Template-Name"),
        "description": request.headers.get("X-Template-Description"),
        "category": request.headers.get("X-Template-Category"),
        "tags": tags,
        "visibility": request.headers.get("X-Template-Visibility", "PRIVATE"),
        "status": request.headers.get("X-Template-Status", "draft"),
        "is_published": request.headers.get("X-Template-Is-Published", "false").lower() == "true",
        "version": request.headers.get("X-Template-Version"),
    }


def template_create():
    user = getattr(g, "user", None)
    tenant_id = getattr(g, "m8flow_tenant_id", None)

    if request.content_type and "multipart/form-data" in (request.content_type or "").lower():
        metadata = _metadata_from_headers()
        if not metadata["template_key"] or not metadata["name"]:
            raise ApiError(
                "missing_fields",
                "X-Template-Key and X-Template-Name headers are required",
                status_code=400,
            )
        files_list = []
        for f in request.files.getlist("files"):
            if f and f.filename:
                content = f.read()
                if content:
                    files_list.append((f.filename, content))
        if not files_list:
            raise ApiError("missing_content", "At least one file is required", status_code=400)
        template = TemplateService.create_template_with_files(
            metadata=metadata,
            files=files_list,
            user=user,
            tenant_id=tenant_id,
        )
        return jsonify(_serialize_template(template)), 201

    if request.content_type != "application/xml":
        raise ApiError(
            "unsupported_media_type",
            "Use application/xml (single BPMN) or multipart/form-data (multiple files) with X-Template-* headers.",
            status_code=415,
        )

    metadata = _metadata_from_headers()
    if not metadata["template_key"] or not metadata["name"]:
        raise ApiError(
            "missing_fields",
            "X-Template-Key and X-Template-Name headers are required",
            status_code=400,
        )
    bpmn_bytes = request.get_data()
    if not bpmn_bytes:
        raise ApiError("missing_content", "BPMN XML content is required in request body", status_code=400)

    template = TemplateService.create_template(
        bpmn_bytes=bpmn_bytes,
        metadata=metadata,
        user=user,
        tenant_id=tenant_id,
    )
    return jsonify(_serialize_template(template)), 201


def template_get_by_id(id: int):
    user = getattr(g, "user", None)
    include_contents = request.args.get("include_contents", "true").lower() == "true"
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    return jsonify(_serialize_template(template, include_bpmn=include_contents))


def template_update_by_id(id: int):
    user = getattr(g, "user", None)
    
    # Check if this is XML body request (new format) or JSON body (legacy format)
    if request.content_type == "application/xml":
        # New format: XML body with metadata in headers
        # Extract metadata from headers (all optional for updates)
        updates = {}
        if request.headers.get("X-Template-Name"):
            updates["name"] = request.headers.get("X-Template-Name")
        if request.headers.get("X-Template-Description"):
            updates["description"] = request.headers.get("X-Template-Description")
        if request.headers.get("X-Template-Category"):
            updates["category"] = request.headers.get("X-Template-Category")
        if request.headers.get("X-Template-Tags"):
            tags = request.headers.get("X-Template-Tags")
            try:
                updates["tags"] = json.loads(tags)
            except json.JSONDecodeError:
                updates["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if request.headers.get("X-Template-Visibility"):
            updates["visibility"] = request.headers.get("X-Template-Visibility")
        if request.headers.get("X-Template-Status"):
            updates["status"] = request.headers.get("X-Template-Status")
        
        # Get BPMN content from request body if provided
        bpmn_bytes = request.get_data() if request.get_data() else None
        bpmn_file_name = request.headers.get("X-Template-File-Name") or None
        if bpmn_file_name:
            bpmn_file_name = bpmn_file_name.strip() or None

        template = TemplateService.update_template_by_id(
            id,
            updates=updates,
            bpmn_bytes=bpmn_bytes,
            bpmn_file_name=bpmn_file_name,
            user=user
        )
    else:
        # Legacy format: JSON body
        body = request.get_json(force=True, silent=True) or {}
        template = TemplateService.update_template_by_id(id, updates=body, user=user)
    
    return jsonify(_serialize_template(template))


def template_get_bpmn(id: int):
    """Retrieve first BPMN file for a template."""
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    bpmn_bytes = TemplateService.get_first_bpmn_content(template)
    if not bpmn_bytes:
        raise ApiError("not_found", "BPMN file not found for this template", status_code=404)
    bpmn_name = "diagram.bpmn"
    for e in template.files or []:
        if e.get("file_type") == "bpmn":
            bpmn_name = e.get("file_name", bpmn_name)
            break
    return Response(
        bpmn_bytes,
        mimetype="application/xml",
        headers=_safe_content_disposition(bpmn_name),
    )


def template_get_file(id: int, file_name: str):
    """Download a single file by name."""
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    found = None
    for e in template.files or []:
        if e.get("file_name") == file_name:
            found = e
            break
    if not found:
        raise ApiError("not_found", f"File not found: {file_name}", status_code=404)
    try:
        content = TemplateService.get_file_content(template, file_name)
    except ApiError:
        raise ApiError("not_found", f"File not found: {file_name}", status_code=404)
    mimetypes = {"bpmn": "application/xml", "json": "application/json", "dmn": "application/xml", "md": "text/markdown"}
    mime = mimetypes.get(found.get("file_type", ""), "application/octet-stream")
    return Response(
        content,
        mimetype=mime,
        headers=_safe_content_disposition(file_name),
    )


def template_put_file(id: int, file_name: str):
    """Update a single file by name.

    If the template is published, a draft version is created/reused and the file is updated there.
    Returns the template that was actually updated (may be different from the requested ID if published).
    """
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    content = request.get_data()
    if not content:
        raise ApiError("missing_content", "Request body is required", status_code=400)
    updated_template = TemplateService.update_file_content(template, file_name, content, user=user)
    return jsonify(_serialize_template(updated_template)), 200


def template_delete_file(id: int, file_name: str):
    """Delete a single file from the template.

    If the template is published, a draft version is created/reused and the file is deleted there.
    """
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    TemplateService.delete_file_from_template(template, file_name, user=user)
    return "", 204


def template_export(id: int):
    """Export template as zip."""
    user = getattr(g, "user", None)
    zip_bytes, filename = TemplateService.export_template_zip(id, user=user)
    return Response(
        zip_bytes,
        mimetype="application/zip",
        headers=_safe_content_disposition(filename),
    )


def template_import():
    """Import template from zip. Send zip as body or multipart file; metadata in X-Template-* headers."""
    user = getattr(g, "user", None)
    if request.content_type and "multipart/form-data" in (request.content_type or "").lower():
        f = request.files.get("file") or request.files.get("zip")
        if not f or not f.filename:
            raise ApiError("missing_content", "Upload a zip file (field 'file' or 'zip')", status_code=400)
        zip_bytes = f.read()
    else:
        zip_bytes = request.get_data()
    if not zip_bytes:
        raise ApiError("missing_content", "Zip file content is required", status_code=400)
    metadata = _metadata_from_headers()
    template = TemplateService.import_template_from_zip(
        zip_bytes=zip_bytes,
        metadata=metadata,
        user=user,
        tenant_id=getattr(g, "m8flow_tenant_id", None),
    )
    return jsonify(_serialize_template(template)), 201


def template_delete_by_id(id: int):
    user = getattr(g, "user", None)
    TemplateService.delete_template_by_id(id, user=user)
    return jsonify({"status": "success", "message": "Template deleted successfully"}), 200


def template_create_process_model(id: int):
    """Create a new process model from a template.

    Request body should contain:
    - process_group_id: The process group where the model will be created
    - process_model_id: The ID for the new process model (just the model name)
    - display_name: Display name for the new process model
    - description: Optional description for the new process model
    """
    user = getattr(g, "user", None)
    tenant_id = getattr(g, "m8flow_tenant_id", None)

    body = request.get_json(force=True, silent=True) or {}

    process_group_id = body.get("process_group_id")
    process_model_id = body.get("process_model_id")
    display_name = body.get("display_name")
    description = body.get("description")

    if not process_group_id:
        raise ApiError("missing_fields", "process_group_id is required", status_code=400)
    if not process_model_id:
        raise ApiError("missing_fields", "process_model_id is required", status_code=400)
    if not display_name:
        raise ApiError("missing_fields", "display_name is required", status_code=400)

    result = TemplateService.create_process_model_from_template(
        template_id=id,
        process_group_id=process_group_id,
        process_model_id=process_model_id,
        display_name=display_name,
        description=description,
        user=user,
        tenant_id=tenant_id,
    )

    return jsonify(result), 201


def get_process_model_template_info(modified_process_model_identifier: str):
    """Get the template provenance info for a process model.

    Returns the template info if the process model was created from a template,
    or 404 if no template info exists for this process model.
    """
    # Convert modified identifier (colons) back to standard format (slashes)
    process_model_identifier = modified_process_model_identifier.replace(":", "/")

    tenant_id = getattr(g, "m8flow_tenant_id", None)

    provenance = TemplateService.get_process_model_template_info(
        process_model_identifier=process_model_identifier,
        tenant_id=tenant_id,
    )

    if provenance is None:
        raise ApiError(
            "not_found",
            f"No template info found for process model '{process_model_identifier}'",
            status_code=404,
        )

    return jsonify(provenance.serialized())
