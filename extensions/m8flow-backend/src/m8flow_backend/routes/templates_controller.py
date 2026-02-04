from __future__ import annotations

import json

from flask import Response, jsonify, request, g

from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.models.template import TemplateModel
from m8flow_backend.services.template_service import TemplateService


def _serialize_template(template: TemplateModel, include_bpmn: bool = True) -> dict:
    """Serialize template with optional BPMN content."""
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
        "bpmnObjectKey": template.bpmn_object_key,
        "isPublished": template.is_published,
        "status": template.status,
        "createdBy": template.created_by,
        "modifiedBy": template.modified_by,
        "createdAtInSeconds": template.created_at_in_seconds,
        "updatedAtInSeconds": template.updated_at_in_seconds,
    }
    
    # Include BPMN content if requested and available
    if include_bpmn and template.bpmn_object_key and template.m8f_tenant_id:
        try:
            bpmn_bytes = TemplateService.storage.get_bpmn(template.bpmn_object_key, template.m8f_tenant_id)
            result["bpmnContent"] = bpmn_bytes.decode("utf-8")
        except Exception:
            # If BPMN file can't be loaded, just omit it
            result["bpmnContent"] = None
    
    return result


def template_list():
    latest_only = request.args.get("latest_only", "true").lower() != "false"
    category = request.args.get("category")
    tag = request.args.get("tag")  # Single tag or comma-separated
    owner = request.args.get("owner")  # created_by username
    visibility = request.args.get("visibility")  # PRIVATE, TENANT, PUBLIC
    search = request.args.get("search")  # Text search in name/description
    user = getattr(g, "user", None)
    templates = TemplateService.list_templates(
        user=user,
        tenant_id=getattr(g, "m8flow_tenant_id", None),
        latest_only=latest_only,
        category=category,
        tag=tag,
        owner=owner,
        visibility=visibility,
        search=search,
    )
    # For list responses, omit BPMN content for performance
    return jsonify([_serialize_template(t, include_bpmn=False) for t in templates])


def template_create():
    user = getattr(g, "user", None)

    # Require XML body (new format) with metadata in headers
    if request.content_type != "application/xml":
        raise ApiError(
            "unsupported_media_type",
            "Only application/xml is supported for template creation. "
            "Send BPMN XML in the body and metadata via X-Template-* headers.",
            status_code=415,
        )

    # Extract metadata from headers
    metadata = {
        "template_key": request.headers.get("X-Template-Key"),
        "name": request.headers.get("X-Template-Name"),
        "description": request.headers.get("X-Template-Description"),
        "category": request.headers.get("X-Template-Category"),
        "tags": request.headers.get("X-Template-Tags"),
        "visibility": request.headers.get("X-Template-Visibility", "PRIVATE"),
        "status": request.headers.get("X-Template-Status", "draft"),
        "is_published": request.headers.get("X-Template-Is-Published", "false").lower() == "true",
        "version": request.headers.get("X-Template-Version"),
    }

    # Validate required headers
    if not metadata["template_key"] or not metadata["name"]:
        raise ApiError(
            "missing_fields",
            "X-Template-Key and X-Template-Name headers are required",
            status_code=400,
        )

    # Get BPMN content from request body
    bpmn_bytes = request.get_data()
    if not bpmn_bytes:
        raise ApiError(
            "missing_content",
            "BPMN XML content is required in request body",
            status_code=400,
        )

    # Parse tags if provided
    if metadata["tags"]:
        try:
            metadata["tags"] = json.loads(metadata["tags"])
        except json.JSONDecodeError:
            # If not JSON, treat as comma-separated
            metadata["tags"] = [tag.strip() for tag in metadata["tags"].split(",") if tag.strip()]

    template = TemplateService.create_template(
        bpmn_bytes=bpmn_bytes,
        metadata=metadata,
        user=user,
        tenant_id=getattr(g, "m8flow_tenant_id", None),
    )

    return jsonify(_serialize_template(template)), 201


def template_get_by_id(id: int):
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    return jsonify(_serialize_template(template))


def template_show(template_key: str):
    version = request.args.get("version")
    latest = request.args.get("latest", "true").lower() != "false"
    user = getattr(g, "user", None)
    tenant_id = getattr(g, "m8flow_tenant_id", None)
    template = TemplateService.get_template(
        template_key, 
        version=version, 
        latest=latest, 
        user=user,
        tenant_id=tenant_id
    )
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    return jsonify(_serialize_template(template))


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
        
        template = TemplateService.update_template_by_id(
            id,
            updates=updates,
            bpmn_bytes=bpmn_bytes,
            user=user
        )
    else:
        # Legacy format: JSON body
        body = request.get_json(force=True, silent=True) or {}
        template = TemplateService.update_template_by_id(id, updates=body, user=user)
    
    return jsonify(_serialize_template(template))


def template_get_bpmn(id: int):
    """Retrieve BPMN file for a template."""
    user = getattr(g, "user", None)
    template = TemplateService.get_template_by_id(id, user=user)
    if template is None:
        raise ApiError("not_found", "Template not found", status_code=404)
    
    if not template.bpmn_object_key:
        raise ApiError("not_found", "BPMN file not found for this template", status_code=404)
    
    # bpmn_object_key now contains only filename, need tenant_id to retrieve
    bpmn_bytes = TemplateService.storage.get_bpmn(template.bpmn_object_key, template.m8f_tenant_id)
    return Response(
        bpmn_bytes,
        mimetype='application/xml',
        headers={
            'Content-Disposition': f'attachment; filename={template.bpmn_object_key}'
        }
    )


def template_delete_by_id(id: int):
    user = getattr(g, "user", None)
    TemplateService.delete_template_by_id(id, user=user)
    return jsonify({"deleted": True})
