from __future__ import annotations

from typing import Any

from m8flow_bpmn_core.errors import (
    AuthorizationError,
    BpmnCoreError,
    InvalidStateError,
    NotFoundError,
    ServiceTaskExecutionError,
    ValidationError,
)


class ApiError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 400,
        errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        # api.yml ErrorData.errors is `additionalProperties: string`; checked here
        # so no endpoint can return a shape the contract doesn't allow.
        if errors is not None and not (
            isinstance(errors, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in errors.items())
        ):
            raise TypeError("ApiError.errors must map field names to message strings.")
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        # Optional per-field messages, keyed by request body field name.
        self.errors = dict(errors) if errors else None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error_code": self.error_code, "message": self.message}
        if self.errors:
            body["errors"] = self.errors
        return body


def map_bpmn_error(exc: BpmnCoreError) -> ApiError:
    if isinstance(exc, AuthorizationError):
        return ApiError("permission_denied", str(exc), 403)
    if isinstance(exc, NotFoundError):
        return ApiError("not_found", str(exc), 404)
    if isinstance(exc, InvalidStateError):
        return ApiError("invalid_state", str(exc), 409)
    if isinstance(exc, ValidationError):
        return ApiError("validation_error", str(exc), 400)
    if isinstance(exc, ServiceTaskExecutionError):
        return ApiError("service_task_error", str(exc), 500)
    return ApiError("bpmn_core_error", str(exc), 500)
