from __future__ import annotations

from flask import g, request
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_backend.services.named_value_service import NamedValueService
from m8flow_backend.tenancy import get_tenant_id


def _tenant_id() -> str:
    try:
        tenant_id = get_tenant_id()
    except RuntimeError as exc:
        raise ApiError(
            error_code="tenant_context_required",
            message="An active tenant is required.",
            status_code=400,
        ) from exc
    if not tenant_id:
        raise ApiError(
            error_code="tenant_context_required",
            message="An active tenant is required.",
            status_code=400,
        )
    return tenant_id


def _body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("missing_content", "A JSON request body is required.", status_code=400)
    name = body.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
        raise ApiError("invalid_name", "name must be 1-255 characters.", status_code=400)
    if "value" not in body:
        raise ApiError("invalid_value", "value is required.", status_code=400)
    is_sensitive = body.get("is_sensitive", body.get("isSensitive", False))
    if not isinstance(is_sensitive, bool):
        raise ApiError("invalid_sensitivity", "is_sensitive must be boolean.", status_code=400)
    return {
        "name": name.strip(),
        "value": body["value"],
        "description": body.get("description"),
        "is_sensitive": is_sensitive,
    }


def _user_id() -> int | None:
    user = getattr(g, "user", None)
    return getattr(user, "id", None) if user is not None else None


@handle_api_errors
def list_named_values():
    tenant_id = _tenant_id()
    return success_response({"values": [v.to_dict() for v in NamedValueService.list_values(tenant_id)]})


@handle_api_errors
def create_named_value():
    data = _body()
    row = NamedValueService.create_value(_tenant_id(), _user_id(), **data)
    return success_response(row.to_dict(), 201)


@handle_api_errors
def get_named_value(value_id: str):
    row = NamedValueService.get_value(_tenant_id(), value_id)
    if row is None:
        raise ApiError("not_found", "Named value not found.", status_code=404)
    return success_response(row.to_dict())


@handle_api_errors
def update_named_value(value_id: str):
    row = NamedValueService.get_value(_tenant_id(), value_id)
    if row is None:
        raise ApiError("not_found", "Named value not found.", status_code=404)
    return success_response(NamedValueService.update_value(row, **_body()).to_dict())


@handle_api_errors
def delete_named_value(value_id: str):
    row = NamedValueService.get_value(_tenant_id(), value_id)
    if row is None:
        raise ApiError("not_found", "Named value not found.", status_code=404)
    NamedValueService.delete_value(row)
    return success_response({"deleted": True, "id": value_id})
