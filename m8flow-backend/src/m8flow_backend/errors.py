from __future__ import annotations

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
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        # Request field -> message, so forms can show the error inline.
        self.field_errors = field_errors

    def to_body(self) -> dict[str, object]:
        body: dict[str, object] = {"error_code": self.error_code, "message": self.message}
        if self.field_errors:
            body["field_errors"] = self.field_errors
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
