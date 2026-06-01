"""Controller for soft-deleted process model and group admin operations."""
from __future__ import annotations

from flask import g, jsonify, request

from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.services.soft_delete_service import (
    OriginalIdentifierUnavailableError,
    SoftDeleteService,
)


def list_deleted_process_models():
    tenant_id = getattr(g, "m8flow_tenant_id", None)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("per_page", 20)), 100))
    except (ValueError, TypeError):
        per_page = 20

    items, pagination = SoftDeleteService.list_deleted_process_models(
        tenant_id=tenant_id, page=page, per_page=per_page
    )
    return jsonify({"results": [item.serialized() for item in items], "pagination": pagination})


def restore_process_model(deletion_id: int):
    user = getattr(g, "user", None)
    body = request.get_json(force=True, silent=True) or {}
    new_identifier = body.get("new_identifier")
    new_display_name = body.get("new_display_name")

    try:
        process_model = SoftDeleteService.restore_process_model(
            deletion_id,
            new_identifier=new_identifier,
            new_display_name=new_display_name,
            user=user,
        )
    except OriginalIdentifierUnavailableError as exc:
        raise ApiError(
            "original_name_in_use",
            str(exc),
            status_code=409,
        ) from exc

    return jsonify(process_model.to_dict())


def purge_process_model(deletion_id: int):
    user = getattr(g, "user", None)
    deletion = SoftDeleteService.purge_single_process_model(deletion_id, user=user)
    return jsonify(deletion.serialized())


def list_deleted_process_groups():
    tenant_id = getattr(g, "m8flow_tenant_id", None)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("per_page", 20)), 100))
    except (ValueError, TypeError):
        per_page = 20

    items, pagination = SoftDeleteService.list_deleted_process_groups(
        tenant_id=tenant_id, page=page, per_page=per_page
    )
    return jsonify({"results": [item.serialized() for item in items], "pagination": pagination})


def restore_process_group(deletion_id: int):
    user = getattr(g, "user", None)
    body = request.get_json(force=True, silent=True) or {}
    new_identifier = body.get("new_identifier")

    try:
        process_group = SoftDeleteService.restore_process_group(
            deletion_id,
            new_identifier=new_identifier,
            user=user,
        )
    except OriginalIdentifierUnavailableError as exc:
        raise ApiError(
            "original_name_in_use",
            str(exc),
            status_code=409,
        ) from exc

    return jsonify(process_group.serialized())
